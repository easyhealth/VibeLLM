"""Configuration management for LLM Proxy."""

import os
import yaml
from pathlib import Path
from typing import Optional, Dict
from pydantic_settings import BaseSettings
from .models import Config, ProviderConfig

# Default config location
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "llm-proxy"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"


class LLMSettings(BaseSettings):
    """Application settings."""
    config_path: Path = DEFAULT_CONFIG_PATH

    class Config:
        env_prefix = "LLM_PROXY_"
        env_file = ".env"


def ensure_config_dir() -> None:
    """Ensure the config directory exists."""
    config_dir = DEFAULT_CONFIG_DIR
    if not config_dir.exists():
        config_dir.mkdir(parents=True, exist_ok=True)


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH

    if not config_path.exists():
        ensure_config_dir()
        # Return empty config
        return Config(default_provider="", providers=[])

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return Config(**data)


def save_config(config: Config, config_path: Optional[Path] = None) -> None:
    """Save configuration to YAML file."""
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH

    ensure_config_dir()

    # Convert to dict
    data = config.model_dump()

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def add_provider(
    name: str,
    base_url: str,
    api_key: str,
    default_model: str,
    enabled: bool = True,
    priority: int = 1,
    simple_model: Optional[str] = None,
    complex_model: Optional[str] = None,
    model_mapping: Optional[Dict[str, str]] = None,
    config_path: Optional[Path] = None,
) -> ProviderConfig:
    """Add or update a provider in the config."""
    config = load_config(config_path)
    provider = ProviderConfig(
        name=name,
        base_url=base_url,
        api_key=api_key,
        default_model=default_model,
        enabled=enabled,
        priority=priority,
        simple_model=simple_model,
        complex_model=complex_model,
        model_mapping=model_mapping or {},
    )
    config.add_provider(provider)
    save_config(config, config_path)
    return provider


def remove_provider(name: str, config_path: Optional[Path] = None) -> bool:
    """Remove a provider from the config."""
    config = load_config(config_path)
    result = config.remove_provider(name)
    save_config(config, config_path)
    return result


def set_default_provider(name: str, config_path: Optional[Path] = None) -> bool:
    """Set the default provider."""
    config = load_config(config_path)
    if config.get_provider(name) is None:
        return False
    config.default_provider = name
    save_config(config, config_path)
    return True


def update_provider_latency(name: str, latency_ms: float, config_path: Optional[Path] = None) -> bool:
    """Update the last latency measurement for a provider."""
    config = load_config(config_path)
    provider = config.get_provider(name)
    if provider is None:
        return False
    provider.last_latency_ms = latency_ms
    save_config(config, config_path)
    return True


def get_config_path() -> Path:
    """Get the current config path."""
    return DEFAULT_CONFIG_PATH
