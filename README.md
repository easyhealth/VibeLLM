# VibeLLM

English | [中文](README.zh-CN.md)

Lightweight local LLM proxy with multiple provider management, privacy protection, and automatic failover for personal use.

## Features

- ✅ **Lightweight**: Only ~8MB install size (vs 100MB+ for litellm-proxy)
- ✅ **Privacy Protection**: Automatically detect PII (personal identifiable information), route simple PII to local LLM, anonymize complex PII for remote LLM and restore automatically
- ✅ Dual endpoints: Provides both OpenAI-compatible (`/v1/chat/completions`) and Anthropic-compatible (`/v1/messages`) localhost endpoints
- ✅ Multiple provider management: Add/remove/enable/disable providers with CLI
- ✅ Support local LLMs: Native support for Ollama, llama.cpp, and any OpenAI-compatible local servers
- ✅ Automatic failover: When you hit rate limit, automatically try the next provider
- ✅ Latency benchmarking: Test which provider is fastest and auto-select
- ✅ Format translation: A client configured for OpenAI can call Anthropic/Gemini, and vice versa
- ✅ Claude Code skill integration: Claude can manage providers for you

## Supported Providers

| Incoming \ Target | OpenAI | Anthropic | Gemini | Local (OpenAI-compatible) |
|-------------------|--------|-----------|--------|---------------------------|
| OpenAI            | ✅ Direct | ✅ Translate | ✅ Translate | ✅ Direct |
| Anthropic         | ✅ Translate | ✅ Direct | ✅ Translate | ✅ Translate |

## Installation

### Install from PyPI (recommended)

```bash
pip install vibellm
```

### Install from source

```bash
git clone https://github.com/easyhealth/VibeLLM.git
cd VibeLLM
pip install -e .
```

## Quick Start

1. Add your first provider:
```bash
llm-proxy add \
  --name openai \
  --base-url https://api.openai.com/v1 \
  --api-key sk-xxx \
  --default-model gpt-4o
```

2. Start the server:
```bash
llm-proxy start --port 8080
```

3. Configure your client to use:
- OpenAI endpoint: `http://localhost:8080/v1/chat/completions`
- Anthropic endpoint: `http://localhost:8080/v1/messages`

## CLI Commands

| Command | Description |
|---------|-------------|
| `llm-proxy start` | Start the proxy server |
| `llm-proxy add` | Add a new provider |
| `llm-proxy remove` | Remove a provider |
| `llm-proxy list` | List all providers |
| `llm-proxy enable <name>` | Enable a provider |
| `llm-proxy disable <name>` | Disable a provider |
| `llm-proxy default <name>` | Set default provider |
| `llm-proxy test <name>` | Test connectivity to a provider |
| `llm-proxy benchmark` | Test latency for all providers |
| `llm-proxy benchmark --auto-set` | Test and set fastest as default |
| `llm-proxy status` | Show server status |

## Benchmarking

Find your fastest provider:
```bash
llm-proxy benchmark --auto-set
```

This will:
1. Test all enabled providers with a simple request
2. Measure latency
3. Automatically set the fastest as the default

## Claude Code Skill Installation

To use as a Claude Code skill, add this to your Claude Code skills directory:

```
ln -s D:/VibeLLM/vibellm-skills/llm_proxy.py ~/.config/claude-code/skills/
```

Then Claude can respond to natural language commands like:
- "list providers"
- "switch default to anthropic"
- "I'm rate limited, find the fastest provider"
- "benchmark and set fastest as default"
- "test my openai provider"

## Configuration

Configuration is stored at `~/.config/vibellm/config.yaml`:

```yaml
default_provider: openai-main
providers:
  - name: openai-main
    base_url: https://api.openai.com/v1
    api_key: sk-xxx
    default_model: gpt-4o
    enabled: true
    priority: 1  # lower = higher priority for failover
    last_latency_ms: null
```

## Selecting Specific Provider

You can select a specific provider per request using the `X-LLM-Provider` header:

```http
X-LLM-Provider: anthropic
POST /v1/chat/completions
```

This will bypass the default and use the explicitly requested provider.

## Dependencies

- Python 3.10+
- fastapi
- uvicorn
- httpx
- click
- pydantic
- pydantic-settings
- pyyaml
- tabulate

Total of 8 packages, all minimal.

## Why this vs litellm-proxy?

litellm-proxy is great for production with many features, but it's heavy and pulls in dozens of dependencies. This project is:
- For personal use on your local machine
- Much lighter weight (only 8 core dependencies vs 50+ for litellm)
- Simpler: just local config file, no database
- Focused on the specific use case: multiple API keys/providers with failover and latency selection
