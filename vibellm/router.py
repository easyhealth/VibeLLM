"""Provider selection and failover logic."""

from typing import Optional, List, Iterator
from .models import Config, ProviderConfig


class ProviderRouter:
    """Routes requests to providers with automatic failover on rate limits."""

    def __init__(self, config: Config):
        self.config = config

    def get_next_provider(
        self,
        requested_name: Optional[str] = None,
        exclude: Optional[List[str]] = None,
    ) -> Optional[ProviderConfig]:
        """Get the next provider to try based on selection logic."""
        exclude = exclude or []

        # If explicit provider requested, try that first
        if requested_name:
            provider = self.config.get_provider(requested_name)
            if provider and provider.enabled and provider.name not in exclude:
                return provider

        # Try the default provider
        default_name = self.config.default_provider
        if default_name and default_name not in exclude:
            default = self.config.get_provider(default_name)
            if default and default.enabled:
                return default

        # Get all enabled providers sorted by priority
        enabled = self.config.get_enabled_providers()

        # Filter out excluded
        available = [p for p in enabled if p.name not in exclude]

        if not available:
            return None

        # Return the first (highest priority / lowest latency)
        return available[0]

    def iterate_available(
        self,
        requested_name: Optional[str] = None,
    ) -> Iterator[ProviderConfig]:
        """Iterate through all available providers for failover."""
        tried: List[str] = []

        while True:
            provider = self.get_next_provider(requested_name, tried)
            if provider is None:
                break
            yield provider
            tried.append(provider.name)

    def record_failure(self, provider: ProviderConfig) -> None:
        """Record a failure for a provider to help with backoff."""
        provider.consecutive_failures += 1

    def record_success(self, provider: ProviderConfig) -> None:
        """Reset failure counter on success."""
        provider.consecutive_failures = 0

    def get_sorted_by_latency(self) -> List[ProviderConfig]:
        """Get enabled providers sorted by latency (fastest first)."""
        enabled = [p for p in self.config.providers if p.enabled]
        return sorted(enabled, key=lambda p: p.last_latency_ms or float('inf'))
