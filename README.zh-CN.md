# MyLLM 轻量级本地 LLM 代理

[English](README.md) | 中文

轻量级本地 LLM 代理，带隐私保护，支持多提供商管理，满足个人使用需求。自动检测个人信息，敏感数据走本地，复杂任务匿名化后走大模型。帮你在碰到速率限制时自动切换线路，自动选择延迟最低的最快线路。

## 功能特性

- ✅ **超轻量**: 安装后仅约 8MB (对比 litellm-proxy 超过 100MB)
- ✅ **隐私保护**: 自动检测 PII (个人可识别信息)
  - PII 数量少 → 直接路由到本地 LLM，数据不出城
  - PII 数量多 → 匿名化替换为占位符，发送给远程大模型，返回后自动还原原始数据
- ✅ 双端点支持: 同时提供 OpenAI 兼容 (`/v1/chat/completions`) 和 Anthropic 兼容 (`/v1/messages`) 本地端点
- ✅ 本地 LLM 支持: 原生支持 Ollama、llama.cpp 以及任意 OpenAI 兼容的本地服务
- ✅ 多提供商管理: 通过 CLI 轻松添加/删除/启用/禁用提供商
- ✅ 自动故障转移: 碰到速率限制时，自动尝试下一个提供商
- ✅ 延迟基准测试: 测试哪个提供商最快并自动选择
- ✅ 格式转换: 配置为 OpenAI 的客户端可以调用 Anthropic/Gemini，反之亦然
- ✅ 模型名称映射: 通用名称映射到不同提供商的特定命名
- ✅ 自动模型选择: `auto` 选简单模型，`auto-complex` 选复杂模型
- ✅ Claude Code 技能集成: Claude 可以自然语言管理提供商

## 支持的格式转换

| 输入格式 \ 目标 | OpenAI | Anthropic | Gemini | 本地 (OpenAI 兼容) |
|----------------|--------|-----------|--------|-------------------|
| OpenAI         | ✅ 直传 | ✅ 转换 | ✅ 转换 | ✅ 直传 |
| Anthropic      | ✅ 转换 | ✅ 直传 | ✅ 转换 | ✅ 转换 |

## 安装

### PyPI 安装 (推荐)

```bash
pip install myllm
```

### 源码安装

```bash
git clone https://github.com/easyhealth/MyLLM.git
cd MyLLM
pip install -e .
```

## 快速开始

1. 添加第一个提供商:
```bash
llm-proxy add \
  --name openai \
  --base-url https://api.openai.com/v1 \
  --api-key sk-xxx \
  --default-model gpt-4o \
  --simple-model gpt-4o-mini \
  --complex-model gpt-4o
```

2. 启动服务器:
```bash
llm-proxy start --port 8080
```

3. 在你的客户端配置:
- OpenAI 端点: `http://localhost:8080/v1/chat/completions`
- Anthropic 端点: `http://localhost:8080/v1/messages`

## CLI 命令

| 命令 | 说明 |
|---------|-------------|
| `llm-proxy start` | 启动代理服务器 |
| `llm-proxy add` | 添加新提供商 |
| `llm-proxy remove` | 删除提供商 |
| `llm-proxy list` | 列出所有提供商 |
| `llm-proxy enable <name>` | 启用提供商 |
| `llm-proxy disable <name>` | 禁用提供商 |
| `llm-proxy default <name>` | 设置默认提供商 |
| `llm-proxy test <name>` | 测试提供商连通性 |
| `llm-proxy benchmark` | 测试所有提供商延迟 |
| `llm-proxy benchmark --auto-set` | 测试并自动设置最快为默认 |
| `llm-proxy status` | 显示当前状态 |

### 添加提供商参数

```bash
llm-proxy add \
  --name NAME \
  --base-url BASE_URL \
  --api-key API_KEY \
  --default-model DEFAULT_MODEL \
  [--simple-model SIMPLE_MODEL] \
  [--complex-model COMPLEX_MODEL] \
  [--enabled/--disabled] \
  [--priority PRIORITY]
```

## 模型自动选择和名称映射

### 自动选择
- 请求 `model=auto` → 使用 `simple_model` (适合简单问答，更快更便宜)
- 请求 `model=auto-complex` → 使用 `complex_model` (适合复杂编码推理)

### 名称映射
不同供应商对同一个模型可能有不同命名，配置 `model_mapping` 解决：
```yaml
providers:
  - name: my-provider
    model_mapping:
      gpt-4o: gpt-4o-20240806
      sonnet: claude-3-5-sonnet-20241022
```
客户端只需要写 `model=gpt-4o` 就会自动映射到目标名称。

## 延迟测试

找到最快的提供商：
```bash
llm-proxy benchmark --auto-set
```

这会：
1. 对所有启用的提供商发送简单测试请求
2. 测量延迟
3. 自动将最快的设置为默认

## Claude Code 技能安装

要作为 Claude Code 技能使用，将技能链接到你的 Claude Code 技能目录：

```bash
ln -s /path/to/MyLLM/myllm-skills/llm_proxy.py ~/.config/claude-code/skills/
```

然后 Claude 就可以理解自然语言命令，比如：
- "list providers" - 列出所有提供商
- "switch default to anthropic" - 切换默认到 anthropic
- "I'm rate limited, find the fastest provider" - 我碰到速率限制了，帮我找最快的
- "benchmark and set fastest as default" - 测试并设置最快
- "test my openai provider" - 测试 openai 提供商连通性

## 配置文件

配置存储在 `~/.config/llm-proxy/config.yaml`:

```yaml
default_provider: openai-main
providers:
  - name: openai-main
    base_url: https://api.openai.com/v1
    api_key: sk-xxx
    default_model: gpt-4o
    enabled: true
    priority: 1          # 优先级，数值越小优先级越高
    simple_model: gpt-4o-mini    # model=auto 使用
    complex_model: gpt-4o        # model=auto-complex 使用
    model_mapping:               # 通用名称 -> 提供商特定名称
      gpt-4o: gpt-4o-20240806
    last_latency_ms: null
```

## 指定特定提供商

你可以在请求头指定特定提供商：

```http
X-LLM-Provider: anthropic
POST /v1/chat/completions
```

这会绕过默认直接使用你指定的提供商。

## 依赖

- Python 3.10+
- fastapi
- uvicorn
- httpx
- click
- pydantic
- pydantic-settings
- pyyaml
- tabulate

总共只有 8 个核心包，非常轻量。

## 和 litellm-proxy 对比

litellm 项目很棒，功能丰富适合生产，但它很重，会拉上来几十个依赖。本项目：
- 专为个人本地使用设计
- 轻量得多 (8 个核心依赖 vs litellm 50+ 依赖)
- 更简单：只使用本地配置文件，不需要数据库
- 专注于特定需求：多 API 密钥/提供商，支持故障转移和延迟选择

## 许可证

MIT License
