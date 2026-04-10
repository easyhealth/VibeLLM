"""Latency benchmarking for providers to find the fastest one."""

import asyncio
from typing import List, Tuple, Optional
from llm_proxy.models import Config, ProviderConfig, BenchmarkResult
from llm_proxy.proxy import LLMProxy
from llm_proxy.config import load_config, update_provider_latency, save_config, set_default_provider


class BenchmarkRunner:
    """Runs latency benchmarks on configured providers."""

    def __init__(self, config: Config):
        self.config = config
        self.proxy = LLMProxy(config)

    async def benchmark_provider(self, provider: ProviderConfig) -> BenchmarkResult:
        """Benchmark a single provider."""
        if not provider.enabled:
            return BenchmarkResult(
                name=provider.name,
                success=False,
                error="Provider is disabled",
                model=provider.default_model,
            )

        success, error, latency_ms = await self.proxy.test_provider(provider)
        return BenchmarkResult(
            name=provider.name,
            success=success,
            latency_ms=latency_ms if success else None,
            error=error,
            model=provider.default_model,
        )

    async def run_benchmark(self, provider_names: Optional[List[str]] = None) -> List[BenchmarkResult]:
        """Run benchmark on all enabled providers or specific list."""
        if provider_names:
            providers = [p for p in self.config.providers if p.name in provider_names and p.enabled]
        else:
            providers = [p for p in self.config.providers if p.enabled]

        # Run benchmarks sequentially to avoid network contention
        results = []
        for provider in providers:
            result = await self.benchmark_provider(provider)
            results.append(result)
            # Update stored latency in config
            if result.success and result.latency_ms is not None:
                update_provider_latency(provider.name, result.latency_ms)

        # Save updated config
        save_config(self.config)
        return results

    def get_fastest_provider(self, results: List[BenchmarkResult]) -> Optional[BenchmarkResult]:
        """Get the fastest successful provider from benchmark results."""
        successful = [r for r in results if r.success and r.latency_ms is not None]
        if not successful:
            return None
        return min(successful, key=lambda r: r.latency_ms)

    def set_fastest_as_default(self, results: List[BenchmarkResult]) -> Optional[str]:
        """Set the fastest successful provider as default."""
        fastest = self.get_fastest_provider(results)
        if fastest is None:
            return None
        set_default_provider(fastest.name)
        return fastest.name


def run_benchmark_sync(auto_set: bool = False, providers: Optional[List[str]] = None) -> Tuple[List[BenchmarkResult], Optional[str]]:
    """Run benchmark synchronously for CLI."""
    config = load_config()
    runner = BenchmarkRunner(config)
    results = asyncio.run(runner.run_benchmark(runner, providers))

    fastest_name = None
    if auto_set:
        fastest_name = runner.set_fastest_as_default(results)

    return results, fastest_name
