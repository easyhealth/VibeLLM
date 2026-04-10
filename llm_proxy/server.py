"""FastAPI server implementation for LLM Proxy."""

import asyncio
from typing import Optional, AsyncGenerator
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from .proxy import LLMProxy
from .config import load_config
from .models import Config


def create_app(config: Optional[Config] = None) -> FastAPI:
    """Create the FastAPI application."""
    if config is None:
        config = load_config()

    app = FastAPI(
        title="LLM Proxy",
        description="Lightweight local LLM proxy with multiple provider management",
        version="0.1.0",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    proxy = LLMProxy(config)

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        enabled_count = sum(1 for p in config.providers if p.enabled)
        return {
            "status": "ok",
            "default_provider": config.default_provider,
            "enabled_providers": enabled_count,
            "total_providers": len(config.providers),
        }

    @app.get("/providers")
    async def list_providers():
        """List all configured providers (without sensitive data)."""
        return {
            "default_provider": config.default_provider,
            "providers": [
                {
                    "name": p.name,
                    "enabled": p.enabled,
                    "priority": p.priority,
                    "default_model": p.default_model,
                    "last_latency_ms": p.last_latency_ms,
                    "type": p.provider_type,
                }
                for p in config.providers
            ],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        """OpenAI-compatible chat completions endpoint."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        # Check for explicit provider in header
        requested_provider = request.headers.get("X-LLM-Provider")

        try:
            result, is_stream, provider = proxy.handle_openai_request(
                request, body, requested_provider
            )
        except RuntimeError as e:
            raise HTTPException(status_code=429, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        if is_stream:
            # Streaming response
            async def wrap_stream() -> AsyncGenerator[bytes, None]:
                async for chunk in result:
                    yield chunk

            return StreamingResponse(
                wrap_stream(),
                media_type="text/event-stream",
            )
        else:
            return result

    @app.post("/v1/messages")
    async def messages(request: Request):
        """Anthropic-compatible messages endpoint."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        requested_provider = request.headers.get("X-LLM-Provider")

        try:
            result, is_stream, provider = proxy.handle_anthropic_request(
                request, body, requested_provider
            )
        except RuntimeError as e:
            raise HTTPException(status_code=429, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        if is_stream:
            async def wrap_stream() -> AsyncGenerator[bytes, None]:
                async for chunk in result:
                    yield chunk

            return StreamingResponse(
                wrap_stream(),
                media_type="text/event-stream",
            )
        else:
            return result

    return app


def run_server(host: str = "127.0.0.1", port: int = 8080):
    """Run the uvicorn server."""
    import uvicorn
    app = create_app()
    uvicorn.run(app, host=host, port=port)
