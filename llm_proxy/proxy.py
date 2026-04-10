"""Core reverse proxy handling."""

import httpx
from typing import Dict, Any, Optional, AsyncGenerator, Tuple
from fastapi import Request
from .models import Config, ProviderConfig, ProviderType
from .router import ProviderRouter
from .translators import RequestTranslator, ResponseTranslator, StreamTranslator
from .config import load_config


class LLMProxy:
    """Core LLM Proxy that handles request routing and format translation."""

    def __init__(self, config: Config):
        self.config = config
        self.router = ProviderRouter(config)
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))

    async def handle_openai_request(
        self,
        request: Request,
        body: Dict[str, Any],
        requested_provider: Optional[str] = None,
    ) -> Tuple[Any, bool, Optional[ProviderConfig]]:
        """Handle an incoming OpenAI-format request."""
        requested_model = body.get("model")
        stream = body.get("stream", False)

        for provider in self.router.iterate_available(requested_provider):
            try:
                # Resolve model name (handles auto, mapping, etc)
                resolved_model = provider.resolve_model(requested_model)
                # Update the body with resolved model
                body["model"] = resolved_model

                # Translate request to target format
                target_body, headers = RequestTranslator.translate_openai_to_target(body, provider)

                # Build full URL
                url = self._build_url(provider, body, resolved_model)

                # Copy headers from original request (excluding host and auth)
                request_headers = self._prepare_headers(dict(request.headers), headers, provider)

                if stream:
                    # Return a streaming response generator
                    return self._stream_response(
                        provider, target_body, url, request_headers, "openai", resolved_model
                    ), True, provider
                else:
                    # Non-streaming request
                    response = await self.client.post(
                        url,
                        json=target_body,
                        headers=request_headers,
                        timeout=httpx.Timeout(300.0),
                    )

                    if response.status_code == 429:
                        # Rate limit hit, try next provider
                        self.router.record_failure(provider)
                        continue

                    response.raise_for_status()
                    response_json = response.json()

                    # Translate back to OpenAI format
                    final_response = ResponseTranslator.translate_to_openai(
                        response_json, provider, resolved_model
                    )

                    self.router.record_success(provider)
                    return final_response, False, provider

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    # Rate limit hit, try next
                    self.router.record_failure(provider)
                    continue
                raise
            except Exception:
                # Other error, try next provider
                self.router.record_failure(provider)
                continue

        # All providers exhausted
        raise RuntimeError("All enabled providers failed or are rate limited")

    async def handle_anthropic_request(
        self,
        request: Request,
        body: Dict[str, Any],
        requested_provider: Optional[str] = None,
    ) -> Tuple[Any, bool, Optional[ProviderConfig]]:
        """Handle an incoming Anthropic-format request."""
        requested_model = body.get("model")
        stream = body.get("stream", False)

        for provider in self.router.iterate_available(requested_provider):
            try:
                # Resolve model name (handles auto, mapping, etc)
                resolved_model = provider.resolve_model(requested_model)
                # Update the body with resolved model
                body["model"] = resolved_model

                # Translate request to target format
                target_body, headers = RequestTranslator.translate_anthropic_to_target(body, provider)

                # Build full URL
                url = self._build_url(provider, body, resolved_model)

                # Copy headers from original request
                request_headers = self._prepare_headers(dict(request.headers), headers, provider)

                if stream:
                    return self._stream_response(
                        provider, target_body, url, request_headers, "anthropic", resolved_model
                    ), True, provider
                else:
                    response = await self.client.post(
                        url,
                        json=target_body,
                        headers=request_headers,
                        timeout=httpx.Timeout(300.0),
                    )

                    if response.status_code == 429:
                        self.router.record_failure(provider)
                        continue

                    response.raise_for_status()
                    response_json = response.json()

                    final_response = ResponseTranslator.translate_to_anthropic(
                        response_json, provider, resolved_model
                    )

                    self.router.record_success(provider)
                    return final_response, False, provider

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    self.router.record_failure(provider)
                    continue
                raise
            except Exception:
                self.router.record_failure(provider)
                continue

        raise RuntimeError("All enabled providers failed or are rate limited")

    def _build_url(self, provider: ProviderConfig, body: Dict[str, Any], model: Optional[str]) -> str:
        """Build the full URL for the request based on provider type."""
        base_url = provider.base_url.rstrip("/")
        provider_type = provider.provider_type

        if provider_type == ProviderType.GEMINI:
            # Gemini format: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}
            model_name = model or provider.default_model
            api_key = provider.api_key
            return f"{base_url}/models/{model_name}:generateContent?key={api_key}"

        # For OpenAI and Anthropic, just use the base URL as given
        # Users are expected to provide the full base URL including /v1
        return base_url + self._get_endpoint_suffix(provider_type)

    def _get_endpoint_suffix(self, provider_type: ProviderType) -> str:
        """Get the endpoint suffix based on provider type."""
        if provider_type == ProviderType.OPENAI:
            return "/chat/completions"
        elif provider_type == ProviderType.ANTHROPIC:
            return "/messages"
        return ""

    def _prepare_headers(
        self,
        original_headers: Dict[str, str],
        translated_headers: Dict[str, str],
        provider: ProviderConfig,
    ) -> Dict[str, str]:
        """Prepare headers for the proxied request."""
        # Start with translated headers (contains the auth)
        result = translated_headers.copy()

        # Copy accept-encoding, content-type, accept from original
        for key in ["content-type", "accept", "accept-encoding", "user-agent"]:
            if key in original_headers:
                result[key] = original_headers[key]

        return result

    async def _stream_response(
        self,
        provider: ProviderConfig,
        body: Dict[str, Any],
        url: str,
        headers: Dict[str, str],
        output_format: str,
        request_model: Optional[str],
    ) -> AsyncGenerator[bytes, None]:
        """Stream response from target provider back to client."""
        model = request_model or provider.default_model

        async with self.client.stream(
            "POST",
            url,
            json=body,
            headers=headers,
            timeout=httpx.Timeout(300.0),
        ) as response:
            if response.status_code == 429:
                # Rate limit - we can't failover mid-stream, so just let it error
                self.router.record_failure(provider)
                yield b""
                return

            response.raise_for_status()

            if provider.provider_type == ProviderType.OPENAI and output_format == "openai":
                # Direct pass-through
                async for chunk in response.aiter_bytes():
                    yield chunk
            else:
                # Need to translate each SSE chunk
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue

                    if line.startswith("data: "):
                        line = line[6:]

                    if line == "[DONE]":
                        if output_format == "openai":
                            yield b"data: [DONE]\n\n"
                        continue

                    try:
                        chunk = eval(line) if '{' in line else None  # noqa: P101
                        if not isinstance(chunk, dict):
                            chunk = {}
                    except Exception:
                        continue

                    if output_format == "openai":
                        translated = StreamTranslator.translate_chunk_to_openai(chunk, provider)
                        if translated:
                            yield f"data: {translated}\n\n".encode("utf-8")

            self.router.record_success(provider)

    async def test_provider(self, provider: ProviderConfig) -> Tuple[bool, Optional[str], float]:
        """Test connectivity to a provider. Returns (success, error message, latency_ms)."""
        import time

        start_time = time.time()

        # Simple test request
        test_body = {
            "model": provider.default_model,
            "messages": [{"role": "user", "content": "Say hello"}],
            "max_tokens": 10,
        }

        try:
            target_body, headers = RequestTranslator.translate_openai_to_target(test_body, provider)
            url = self._build_url(provider, test_body, provider.default_model)
            headers["Accept"] = "application/json"

            response = await self.client.post(
                url,
                json=target_body,
                headers=headers,
                timeout=httpx.Timeout(60.0),
            )

            latency_ms = (time.time() - start_time) * 1000
            response.raise_for_status()

            return True, None, latency_ms

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return False, str(e), latency_ms


def create_proxy_from_config() -> LLMProxy:
    """Create an LLMProxy instance from the loaded config."""
    config = load_config()
    return LLMProxy(config)
