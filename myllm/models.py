"""Pydantic models for LLM Proxy configuration and API types."""

from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import Enum


class ProviderType(str, Enum):
    """Types of supported provider formats."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class ProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""
    name: str
    base_url: str
    api_key: str
    default_model: str
    enabled: bool = True
    priority: int = 1
    last_latency_ms: Optional[float] = None
    type: Optional[ProviderType] = None
    consecutive_failures: int = 0
    model_mapping: Dict[str, str] = Field(default_factory=dict, description="Map generic model names to provider-specific names")
    simple_model: Optional[str] = Field(None, description="Model to use for simple tasks when model=auto")
    complex_model: Optional[str] = Field(None, description="Model to use for complex tasks when model=auto-complex")
    is_local: bool = Field(False, description="Whether this is a local LLM provider (for privacy routing)")

    def resolve_model(self, requested_model: Optional[str]) -> str:
        """
        Resolve the requested model name to the actual model name for this provider.
        Handles:
        - None/empty → default_model
        - "auto" → simple_model if configured, else default_model
        - "auto-complex" → complex_model if configured, else default_model
        - model in model_mapping → mapped name
        - otherwise → requested_model
        """
        if requested_model is None or requested_model == "":
            return self.default_model

        # Handle auto selection
        if requested_model == "auto":
            return self.simple_model or self.default_model
        if requested_model == "auto-complex" or requested_model == "complex":
            return self.complex_model or self.default_model

        # Check model mapping
        if requested_model in self.model_mapping:
            return self.model_mapping[requested_model]

        # No mapping, use as-is
        return requested_model

    @property
    def provider_type(self) -> ProviderType:
        """Detect provider type from base_url if not explicitly set."""
        if self.type:
            return self.type
        url_lower = self.base_url.lower()
        if "openai" in url_lower or "openai.com" in url_lower:
            return ProviderType.OPENAI
        elif "anthropic" in url_lower or "anthropic.com" in url_lower:
            return ProviderType.ANTHROPIC
        elif "google" in url_lower or "gemini" in url_lower or "generativelanguage" in url_lower:
            return ProviderType.GEMINI
        else:
            # Default to OpenAI format for custom reverse proxies
            return ProviderType.OPENAI


class Config(BaseModel):
    """Root configuration for LLM Proxy."""
    default_provider: str
    providers: List[ProviderConfig] = Field(default_factory=list)
    privacy_enabled: bool = Field(False, description="Enable privacy detection and routing")
    privacy_local_provider: Optional[str] = Field(None, description="Name of the local provider to use for privacy tasks")
    privacy_pii_count_threshold: int = Field(3, description="PII count threshold: below this → local, above this → anonymize + remote")
    privacy_allow_remote_with_anonymization: bool = Field(True, description="Allow sending anonymized requests to remote providers")

    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        """Get a provider by name."""
        return next((p for p in self.providers if p.name == name), None)

    def add_provider(self, provider: ProviderConfig) -> None:
        """Add a new provider."""
        # Remove existing with same name if any
        self.providers = [p for p in self.providers if p.name != provider.name]
        self.providers.append(provider)

    def remove_provider(self, name: str) -> bool:
        """Remove a provider by name."""
        original_len = len(self.providers)
        self.providers = [p for p in self.providers if p.name != name]
        return len(self.providers) < original_len

    def get_enabled_providers(self) -> List[ProviderConfig]:
        """Get all enabled providers sorted by priority (and latency if available)."""
        enabled = [p for p in self.providers if p.enabled]
        # Sort by priority first (lower = higher priority), then by latency (lower = faster)
        return sorted(enabled, key=lambda p: (p.priority, p.last_latency_ms or float('inf')))

    def get_default_provider(self) -> Optional[ProviderConfig]:
        """Get the default provider."""
        return self.get_provider(self.default_provider)


# OpenAI format models
class OpenAIMessage(BaseModel):
    """OpenAI chat message format."""
    role: str
    content: Union[str, List[Dict[str, Any]]]


class OpenAIChatCompletionRequest(BaseModel):
    """OpenAI chat completion request format."""
    model: Optional[str] = None
    messages: List[OpenAIMessage]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    stop: Optional[Union[str, List[str]]] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None


class OpenAIChoice(BaseModel):
    """OpenAI completion choice."""
    index: int
    message: Dict[str, Any]
    finish_reason: Optional[str]


class OpenAIUsage(BaseModel):
    """OpenAI token usage."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class OpenAIChatCompletionResponse(BaseModel):
    """OpenAI chat completion response format."""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[OpenAIChoice]
    usage: OpenAIUsage


# Anthropic format models
class AnthropicMessage(BaseModel):
    """Anthropic message format."""
    role: str
    content: Union[str, List[Dict[str, Any]]]


class AnthropicMessagesRequest(BaseModel):
    """Anthropic messages request format."""
    model: Optional[str] = None
    messages: List[AnthropicMessage]
    system: Optional[str] = None
    max_tokens: int
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    stream: Optional[bool] = False
    stop_sequences: Optional[List[str]] = None


class AnthropicContentBlock(BaseModel):
    """Anthropic content block."""
    type: str
    text: str


class AnthropicUsage(BaseModel):
    """Anthropic token usage."""
    input_tokens: int
    output_tokens: int


class AnthropicMessagesResponse(BaseModel):
    """Anthropic messages response format."""
    id: str
    type: str
    role: str = "assistant"
    content: List[AnthropicContentBlock]
    model: str
    stop_reason: Optional[str]
    usage: AnthropicUsage


# Gemini format models
class GeminiContent(BaseModel):
    """Gemini content format."""
    role: str
    parts: List[Dict[str, Any]]


class GeminiGenerateContentRequest(BaseModel):
    """Gemini generate content request."""
    contents: List[GeminiContent]
    generationConfig: Optional[Dict[str, Any]] = None


class GeminiCandidate(BaseModel):
    """Gemini candidate response."""
    content: GeminiContent
    finishReason: Optional[str]
    index: int


class GeminiUsage(BaseModel):
    """Gemini token usage."""
    promptTokenCount: int
    candidatesTokenCount: int
    totalTokenCount: int


class GeminiGenerateContentResponse(BaseModel):
    """Gemini generate content response."""
    candidates: List[GeminiCandidate]
    usageMetadata: GeminiUsage


# Benchmark results
class BenchmarkResult(BaseModel):
    """Result of a single provider benchmark."""
    name: str
    success: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    model: str


# Privacy detection models
class PIIMatch(BaseModel):
    """A detected PII entity."""
    entity_type: str
    original_text: str
    placeholder: str
    start: int
    end: int


class AnonymizationResult(BaseModel):
    """Result of request anonymization."""
    anonymized_messages: List[Dict[str, Any]]
    pii_mapping: Dict[str, PIIMatch]
    pii_count: int
    has_complex_pii: bool
    should_route_local: bool
    should_anonymize: bool
