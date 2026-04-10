"""Format translation between different LLM API formats."""

import time
from typing import Dict, Any, Tuple, Optional
from .models import (
    ProviderType,
    OpenAIChatCompletionRequest,
    AnthropicMessagesRequest,
    OpenAIChatCompletionResponse,
    AnthropicMessagesResponse,
    GeminiGenerateContentResponse,
    ProviderConfig,
)


class RequestTranslator:
    """Translate incoming request to target provider format."""

    @staticmethod
    def translate_openai_to_target(
        request: Dict[str, Any],
        provider: ProviderConfig,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Translate incoming OpenAI request to target provider format."""
        provider_type = provider.provider_type
        if provider_type == ProviderType.OPENAI:
            # Already OpenAI format, just use it as-is but inject model if needed
            result = request.copy()
            if "model" not in result or result["model"] is None:
                result["model"] = provider.default_model
            return result, RequestTranslator._get_headers(provider)

        elif provider_type == ProviderType.ANTHROPIC:
            return RequestTranslator._openai_to_anthropic(request, provider), RequestTranslator._get_headers(provider)

        elif provider_type == ProviderType.GEMINI:
            return RequestTranslator._openai_to_gemini(request, provider), RequestTranslator._get_headers(provider)

        return request, RequestTranslator._get_headers(provider)

    @staticmethod
    def translate_anthropic_to_target(
        request: Dict[str, Any],
        provider: ProviderConfig,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Translate incoming Anthropic request to target provider format."""
        provider_type = provider.provider_type
        if provider_type == ProviderType.ANTHROPIC:
            # Already Anthropic format
            result = request.copy()
            if "model" not in result or result["model"] is None:
                result["model"] = provider.default_model
            return result, RequestTranslator._get_headers(provider)

        elif provider_type == ProviderType.OPENAI:
            return RequestTranslator._anthropic_to_openai(request, provider), RequestTranslator._get_headers(provider)

        elif provider_type == ProviderType.GEMINI:
            # Convert Anthropic -> OpenAI first, then OpenAI -> Gemini
            openai_req = RequestTranslator._anthropic_to_openai(request, provider)
            return RequestTranslator._openai_to_gemini(openai_req, provider), RequestTranslator._get_headers(provider)

        return request, RequestTranslator._get_headers(provider)

    @staticmethod
    def _get_headers(provider: ProviderConfig) -> Dict[str, Any]:
        """Get the correct headers for the provider type."""
        provider_type = provider.provider_type
        headers = {}

        if provider_type == ProviderType.OPENAI:
            headers["Authorization"] = f"Bearer {provider.api_key}"

        elif provider_type == ProviderType.ANTHROPIC:
            headers["x-api-key"] = provider.api_key
            headers["anthropic-version"] = "2023-06-01"

        elif provider_type == ProviderType.GEMINI:
            # Gemini uses API key as query parameter, not header
            pass

        return headers

    @staticmethod
    def _openai_to_anthropic(request: Dict[str, Any], provider: ProviderConfig) -> Dict[str, Any]:
        """Convert OpenAI format to Anthropic format."""
        messages = request.get("messages", [])
        result: Dict[str, Any] = {}

        # Extract system message
        system_messages = [m["content"] for m in messages if m["role"] == "system"]
        if system_messages:
            result["system"] = "\n".join(system_messages)

        # Filter out system messages for the messages array
        user_assistant_messages = [m for m in messages if m["role"] in ("user", "assistant")]

        # Map roles
        anthropic_messages = []
        for msg in user_assistant_messages:
            anthropic_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        result["messages"] = anthropic_messages
        result["model"] = request.get("model", provider.default_model) or provider.default_model

        # Handle max_tokens - Anthropic requires it
        if "max_tokens" in request and request["max_tokens"] is not None:
            result["max_tokens"] = request["max_tokens"]
        else:
            # Default reasonable value
            result["max_tokens"] = 4096

        if "temperature" in request and request["temperature"] is not None:
            result["temperature"] = request["temperature"]
        if "top_p" in request and request["top_p"] is not None:
            result["top_p"] = request["top_p"]
        if "stream" in request:
            result["stream"] = request["stream"]
        if "stop" in request and request["stop"] is not None:
            stop = request["stop"]
            if isinstance(stop, str):
                result["stop_sequences"] = [stop]
            else:
                result["stop_sequences"] = stop

        return result

    @staticmethod
    def _anthropic_to_openai(request: Dict[str, Any], provider: ProviderConfig) -> Dict[str, Any]:
        """Convert Anthropic format to OpenAI format."""
        messages = request.get("messages", [])
        result: Dict[str, Any] = {}

        # Add system message if present
        openai_messages = []
        if "system" in request and request["system"]:
            openai_messages.append({
                "role": "system",
                "content": request["system"],
            })

        # Add the rest
        for msg in messages:
            openai_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        result["messages"] = openai_messages
        result["model"] = request.get("model", provider.default_model) or provider.default_model

        if "max_tokens" in request:
            result["max_tokens"] = request["max_tokens"]
        if "temperature" in request:
            result["temperature"] = request["temperature"]
        if "top_p" in request:
            result["top_p"] = request["top_p"]
        if "stream" in request:
            result["stream"] = request["stream"]
        if "stop_sequences" in request and request["stop_sequences"]:
            if len(request["stop_sequences"]) == 1:
                result["stop"] = request["stop_sequences"][0]
            else:
                result["stop"] = request["stop_sequences"]

        return result

    @staticmethod
    def _openai_to_gemini(request: Dict[str, Any], provider: ProviderConfig) -> Dict[str, Any]:
        """Convert OpenAI format to Gemini format."""
        messages = request.get("messages", [])
        contents = []

        for msg in messages:
            role = "model" if msg["role"] == "assistant" else "user"
            content = msg["content"]

            if isinstance(content, str):
                parts = [{"text": content}]
            else:
                # Handle multi-modal content
                parts = []
                for block in content:
                    if block.get("type") == "text":
                        parts.append({"text": block.get("text", "")})
                    elif block.get("type") == "image_url":
                        parts.append({
                            "inlineData": {
                                "mimeType": "image/jpeg",
                                "data": block.get("image_url", {}).get("url", ""),
                            }
                        })

            contents.append({
                "role": role,
                "parts": parts,
            })

        generation_config = {}
        if "temperature" in request and request["temperature"] is not None:
            generation_config["temperature"] = request["temperature"]
        if "top_p" in request and request["top_p"] is not None:
            generation_config["topP"] = request["top_p"]
        if "max_tokens" in request and request["max_tokens"] is not None:
            generation_config["maxOutputTokens"] = request["max_tokens"]
        if "stop" in request and request["stop"] is not None:
            if isinstance(request["stop"], list):
                generation_config["stopSequences"] = request["stop"]
            else:
                generation_config["stopSequences"] = [request["stop"]]

        result = {
            "contents": contents,
        }

        if generation_config:
            result["generationConfig"] = generation_config

        return result


class ResponseTranslator:
    """Translate target provider response back to incoming format."""

    @staticmethod
    def translate_to_openai(
        response: Dict[str, Any],
        provider: ProviderConfig,
        request_model: str,
    ) -> Dict[str, Any]:
        """Translate any provider response back to OpenAI format."""
        provider_type = provider.provider_type

        if provider_type == ProviderType.OPENAI:
            return response

        elif provider_type == ProviderType.ANTHROPIC:
            return ResponseTranslator._anthropic_to_openai(response, request_model)

        elif provider_type == ProviderType.GEMINI:
            return ResponseTranslator._gemini_to_openai(response, request_model)

        return response

    @staticmethod
    def translate_to_anthropic(
        response: Dict[str, Any],
        provider: ProviderConfig,
        request_model: str,
    ) -> Dict[str, Any]:
        """Translate any provider response back to Anthropic format."""
        provider_type = provider.provider_type

        if provider_type == ProviderType.ANTHROPIC:
            return response

        elif provider_type == ProviderType.OPENAI:
            return ResponseTranslator._openai_to_anthropic(response, request_model)

        elif provider_type == ProviderType.GEMINI:
            # Gemini -> OpenAI -> Anthropic
            openai_resp = ResponseTranslator._gemini_to_openai(response, request_model)
            return ResponseTranslator._openai_to_anthropic(openai_resp, request_model)

        return response

    @staticmethod
    def _anthropic_to_openai(response: Dict[str, Any], model: str) -> Dict[str, Any]:
        """Convert Anthropic response to OpenAI format."""
        # Get the text from the first content block
        content = ""
        if "content" in response and response["content"]:
            first_block = response["content"][0]
            if isinstance(first_block, dict) and "text" in first_block:
                content = first_block["text"]
            elif isinstance(first_block, str):
                content = first_block

        # Map stop_reason to finish_reason
        finish_reason = response.get("stop_reason", "stop")
        if finish_reason == "end_turn":
            finish_reason = "stop"

        # Get usage
        usage = response.get("usage", {})
        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)

        return {
            "id": response.get("id", f"cmpl-{int(time.time())}"),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": finish_reason,
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    @staticmethod
    def _openai_to_anthropic(response: Dict[str, Any], model: str) -> Dict[str, Any]:
        """Convert OpenAI response to Anthropic format."""
        choices = response.get("choices", [{}])
        first_choice = choices[0] if choices else {}
        message = first_choice.get("message", {})
        content = message.get("content", "")

        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        finish_reason = first_choice.get("finish_reason", "stop")
        if finish_reason == "stop":
            finish_reason = "end_turn"

        return {
            "id": response.get("id", f"msg_{int(time.time())}"),
            "type": "message",
            "role": "assistant",
            "content": [{
                "type": "text",
                "text": content,
            }],
            "model": model,
            "stop_reason": finish_reason,
            "usage": {
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
            },
        }

    @staticmethod
    def _gemini_to_openai(response: Dict[str, Any], model: str) -> Dict[str, Any]:
        """Convert Gemini response to OpenAI format."""
        candidates = response.get("candidates", [])
        first_candidate = candidates[0] if candidates else {}
        content = first_candidate.get("content", {})
        parts = content.get("parts", [{}])

        text = ""
        if parts:
            first_part = parts[0]
            text = first_part.get("text", "")

        finish_reason = first_candidate.get("finishReason", "STOP")
        if finish_reason == "STOP":
            finish_reason = "stop"
        elif finish_reason == "MAX_TOKENS":
            finish_reason = "length"

        usage = response.get("usageMetadata", {})
        prompt_tokens = usage.get("promptTokenCount", 0)
        completion_tokens = usage.get("candidatesTokenCount", 0)

        return {
            "id": f"cmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text,
                },
                "finish_reason": finish_reason,
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }


class StreamTranslator:
    """Translate streaming responses."""

    @staticmethod
    def translate_chunk_to_openai(chunk: Dict[str, Any], provider: ProviderConfig) -> Optional[Dict[str, Any]]:
        """Translate a streaming chunk to OpenAI SSE format."""
        provider_type = provider.provider_type

        if provider_type == ProviderType.OPENAI:
            return chunk

        elif provider_type == ProviderType.ANTHROPIC:
            return StreamTranslator._anthropic_chunk_to_openai(chunk)

        elif provider_type == ProviderType.GEMINI:
            return StreamTranslator._gemini_chunk_to_openai(chunk)

        return chunk

    @staticmethod
    def _anthropic_chunk_to_openai(chunk: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert Anthropic streaming chunk to OpenAI format."""
        chunk_type = chunk.get("type")

        if chunk_type == "content_block_delta":
            delta = chunk.get("delta", {})
            text = delta.get("text", "")
            return {
                "id": chunk.get("message_id", ""),
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "",
                "choices": [{
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "content": text,
                    },
                    "finish_reason": None,
                }],
            }

        elif chunk_type == "message_stop":
            return {
                "id": "",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "",
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }],
            }

        return None

    @staticmethod
    def _gemini_chunk_to_openai(chunk: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert Gemini streaming chunk to OpenAI format."""
        candidates = chunk.get("candidates", [])
        if not candidates:
            return None

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        if not parts:
            return None

        text = parts[0].get("text", "")
        finish_reason = candidate.get("finishReason", None)

        if finish_reason == "STOP":
            finish_reason = "stop"

        return {
            "id": f"cmpl-{int(time.time())}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "",
            "choices": [{
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "content": text,
                },
                "finish_reason": finish_reason if finish_reason else None,
            }],
        }
