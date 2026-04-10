"""CLI interface for LLM Proxy."""

import click
import sys
from typing import Optional
from tabulate import tabulate
from . import __version__
from .config import (
    load_config,
    add_provider,
    remove_provider,
    set_default_provider,
    get_config_path,
    save_config,
)
from .models import ProviderConfig
from .benchmark import BenchmarkRunner
from .server import run_server


@click.group()
@click.version_option(version=__version__)
def main():
    """Lightweight local LLM proxy with multiple provider management."""
    pass


@main.command("start")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8080, type=int, help="Port to listen on")
def start_command(host, port):
    """Start the LLM proxy server."""
    config = load_config()
    if not config.providers:
        click.echo("No providers configured. Use 'llm-proxy add' to add a provider.", err=True)
        sys.exit(1)

    if not config.default_provider:
        click.echo("No default provider set. Use 'llm-proxy default <name>' to set one.", err=True)
        sys.exit(1)

    click.echo(f"Starting LLM proxy on http://{host}:{port}")
    click.echo(f"Default provider: {config.default_provider}")
    click.echo(f"Enabled providers: {sum(1 for p in config.providers if p.enabled)} of {len(config.providers)}")
    click.echo()
    click.echo("Endpoints:")
    click.echo(f"  OpenAI: http://{host}:{port}/v1/chat/completions")
    click.echo(f"  Anthropic: http://{host}:{port}/v1/messages")
    click.echo(f"  Health: http://{host}:{port}/health")
    click.echo()

    run_server(host, port)


@main.command("add")
@click.option("--name", required=True, help="Name of the provider")
@click.option("--base-url", required=True, help="Base URL of the provider API")
@click.option("--api-key", required=True, help="API key for the provider")
@click.option("--default-model", required=True, help="Default model to use")
@click.option("--simple-model", help="Model for simple tasks (auto selection)")
@click.option("--complex-model", help="Model for complex tasks (auto selection)")
@click.option("--enabled/--disabled", default=True, help="Whether the provider is enabled")
@click.option("--priority", type=int, default=1, help="Priority for failover (lower = higher priority)")
def add_command(name, base_url, api_key, default_model, simple_model, complex_model, enabled, priority):
    """Add a new provider configuration."""
    from myllm.models import ProviderConfig
    from myllm.config import add_provider

    provider = ProviderConfig(
        name=name,
        base_url=base_url,
        api_key=api_key,
        default_model=default_model,
        enabled=enabled,
        priority=priority,
        simple_model=simple_model,
        complex_model=complex_model,
    )
    add_provider(
        name=name,
        base_url=base_url,
        api_key=api_key,
        default_model=default_model,
        enabled=enabled,
        priority=priority,
        simple_model=simple_model,
        complex_model=complex_model,
    )
    click.echo(f"Added provider '{name}'")
    click.echo(f"Default model: {default_model}")
    if simple_model:
        click.echo(f"Simple model (auto): {simple_model}")
    if complex_model:
        click.echo(f"Complex model (auto-complex): {complex_model}")
    if enabled:
        click.echo(f"Priority: {priority} (lower = higher priority for failover)")


@main.command("remove")
@click.option("--name", required=True, help="Name of the provider to remove")
def remove_command(name):
    """Remove a provider configuration."""
    success = remove_provider(name)
    if success:
        click.echo(f"Removed provider '{name}'")
    else:
        click.echo(f"Provider '{name}' not found", err=True)
        sys.exit(1)


@main.command("list")
def list_command():
    """List all configured providers."""
    config = load_config()

    if not config.providers:
        click.echo("No providers configured. Use 'llm-proxy add' to add one.")
        return

    table = []
    for p in config.providers:
        status = "+" if p.enabled else "-"
        default = "*" if p.name == config.default_provider else ""
        latency = f"{p.last_latency_ms:.0f}ms" if p.last_latency_ms is not None else "-"
        table.append([
            status,
            default,
            p.name,
            p.default_model,
            p.priority,
            latency,
            p.provider_type.value,
        ])

    headers = ["", "Default", "Name", "Model", "Priority", "Latency", "Type"]
    click.echo(tabulate(table, headers=headers, tablefmt="simple"))
    click.echo()
    click.echo(f"Total: {len(config.providers)} providers, {sum(1 for p in config.providers if p.enabled)} enabled")
    click.echo(f"Config stored at: {get_config_path()}")


@main.command("enable")
@click.option("--name", required=True, help="Name of the provider to enable")
def enable_command(name):
    """Enable a provider."""
    config = load_config()
    provider = config.get_provider(name)
    if not provider:
        click.echo(f"Provider '{name}' not found", err=True)
        sys.exit(1)
    provider.enabled = True
    save_config(config)
    click.echo(f"Enabled provider '{name}'")


@main.command("disable")
@click.option("--name", required=True, help="Name of the provider to disable")
def disable_command(name):
    """Disable a provider."""
    config = load_config()
    provider = config.get_provider(name)
    if not provider:
        click.echo(f"Provider '{name}' not found", err=True)
        sys.exit(1)
    provider.enabled = False
    save_config(config)
    click.echo(f"Disabled provider '{name}'")


@main.command("default")
@click.option("--name", required=True, help="Name of the provider to set as default")
def default_command(name):
    """Set the default provider."""
    success = set_default_provider(name)
    if success:
        click.echo(f"Set '{name}' as default provider")
    else:
        click.echo(f"Provider '{name}' not found", err=True)
        sys.exit(1)


@main.command("test")
@click.option("--name", required=True, help="Name of the provider to test")
def test_command(name):
    """Test connectivity to a provider."""
    import asyncio
    from myllm.proxy import LLMProxy

    config = load_config()
    provider = config.get_provider(name)
    if not provider:
        click.echo(f"Provider '{name}' not found", err=True)
        sys.exit(1)

    click.echo(f"Testing connectivity to '{name}'...")
    click.echo(f"Model: {provider.default_model}")
    click.echo(f"Base URL: {provider.base_url}")
    click.echo()

    proxy = LLMProxy(config)
    success, error, latency = asyncio.run(proxy.test_provider(provider))

    if success:
        click.echo(click.style(f"OK Test passed in {latency:.0f}ms", fg="green"))
    else:
        click.echo(click.style(f"FAILED Test failed: {error}", fg="red"))
        sys.exit(1)


@main.command("benchmark")
@click.option("--auto-set/--no-auto-set", default=False, help="Automatically set fastest provider as default")
@click.argument("providers", nargs=-1)
def benchmark_command(auto_set, providers):
    """Run latency benchmark on all enabled providers."""
    import asyncio

    config = load_config()
    runner = BenchmarkRunner(config)

    provider_list = list(providers) if providers else None
    click.echo("Running latency benchmark...")
    click.echo()

    results = asyncio.run(runner.run_benchmark(provider_list))

    # Sort by latency
    successful = [r for r in results if r.success and r.latency_ms is not None]
    failed = [r for r in results if not r.success]

    if successful:
        successful.sort(key=lambda r: r.latency_ms)

        table = []
        for i, r in enumerate(successful, 1):
            table.append([
                i,
                r.name,
                r.model,
                f"{r.latency_ms:.0f}ms",
            ])

        click.echo(click.style("Results (fastest first):", bold=True))
        click.echo(tabulate(table, ["Rank", "Provider", "Model", "Latency"], tablefmt="simple"))
        click.echo()

        fastest = successful[0]
        click.echo(click.style(f"* Fastest: {fastest.name} ({fastest.latency_ms:.0f}ms)", fg="green"))

        if auto_set:
            from myllm.config import set_default_provider
            set_default_provider(fastest.name)
            click.echo(click.style(f"* Set '{fastest.name}' as default provider", fg="green"))

    if failed:
        click.echo()
        click.echo(click.style("Failed benchmarks:", fg="red"))
        for r in failed:
            click.echo(f"  {r.name}: {r.error}")

    if not successful and failed:
        sys.exit(1)


@main.command("status")
def status_command():
    """Show current status and configuration."""
    import socket
    from urllib.request import Request, urlopen
    from urllib.error import URLError

    config = load_config()
    config_path = get_config_path()

    click.echo(f"Config file: {config_path}")
    click.echo(f"Config exists: {click.style('Yes' if config_path.exists() else 'No', fg='green' if config_path.exists() else 'red')}")
    click.echo()
    click.echo(f"Default provider: {config.default_provider}")
    click.echo(f"Total providers: {len(config.providers)}")
    click.echo(f"Enabled providers: {sum(1 for p in config.providers if p.enabled)}")
    click.echo()

    # Check if server is running
    try:
        req = Request("http://127.0.0.1:8080/health")
        with urlopen(req, timeout=2) as f:
            import json
            data = json.loads(f.read())
            click.echo(click.style("OK Server is running on port 8080", fg="green"))
            click.echo(f"  Default provider: {data.get('default_provider')}")
            click.echo(f"  Enabled providers: {data.get('enabled_providers')}")
    except (URLError, socket.timeout):
        click.echo(click.style("NOT RUNNING Server is not running on port 8080", fg="yellow"))
        click.echo("  Start it with: llm-proxy start")


if __name__ == "__main__":
    main()
