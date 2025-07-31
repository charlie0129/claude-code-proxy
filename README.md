# Claude Code Proxy

A proxy server that enables **Claude Code** to work with OpenAI-compatible API providers. Convert Claude API requests to OpenAI API calls, allowing you to use various LLM providers through the Claude Code CLI.

![Claude Code Proxy](demo.png)

## Features

- **Full Claude API Compatibility**: Complete `/v1/messages` endpoint support
- **Multiple Provider Support**: OpenAI, Azure OpenAI, local models (Ollama), and any OpenAI-compatible API
- **Dynamic API Key Support**: Use client's OpenAI keys when no server key is configured
- **Smart Model Mapping**: Configure BIG and SMALL models via environment variables
- **Function Calling**: Complete tool use support with proper conversion
- **Streaming Responses**: Real-time SSE streaming support
- **Image Support**: Base64 encoded image input
- **Error Handling**: Comprehensive error handling and logging

## Quick Start

### 1. Install Dependencies

```bash
# Using UV (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and add your API configuration
```

### 3. Start Server

```bash
# Direct run
python start_proxy.py

# Or with UV
uv run claude-code-proxy
```

### 4. Use with Claude Code

```bash
# If OPENAI_API_KEY is not set (dynamic mode):
ANTHROPIC_BASE_URL=http://localhost:8082 ANTHROPIC_API_KEY="your-openai-key" claude

# If OPENAI_API_KEY is set (static mode):
ANTHROPIC_BASE_URL=http://localhost:8082 ANTHROPIC_API_KEY="any-value" claude
```

## Configuration

### Environment Variables

**API Keys (choose one mode):**

- `OPENAI_API_KEY` - Your API key for the target provider (optional)
  - If set: All requests use this key (static mode)
  - If not set: Client's API key is used for each request (dynamic mode)

**Security:**

- `ANTHROPIC_API_KEY` - Expected API key for client validation
  - In static mode: Validates against this exact value
  - In dynamic mode: Validates OpenAI key format (starts with `sk-`)
  - If not set: Validation is disabled

**Model Configuration:**

- `BIG_MODEL` - Model for Claude opus requests (default: `gpt-4o`)
- `MIDDLE_MODEL` - Model for Claude opus requests (default: `gpt-4o`)
- `SMALL_MODEL` - Model for Claude haiku requests (default: `gpt-4o-mini`)

**API Configuration:**

- `OPENAI_BASE_URL` - API base URL (default: `https://api.openai.com/v1`)

**Server Settings:**

- `HOST` - Server host (default: `0.0.0.0`)
- `PORT` - Server port (default: `8082`)
- `LOG_LEVEL` - Logging level (default: `WARNING`)

**Performance:**

- `MAX_TOKENS_LIMIT` - Token limit (default: `4096`)
- `REQUEST_TIMEOUT` - Request timeout in seconds (default: `90`)

### Model Mapping

The proxy maps Claude model requests to your configured models:

| Claude Request                 | Mapped To     | Environment Variable   |
| ------------------------------ | ------------- | ---------------------- |
| Models with "haiku"            | `SMALL_MODEL` | Default: `gpt-4o-mini` |
| Models with "sonnet"           | `MIDDLE_MODEL`| Default: `BIG_MODEL`   |
| Models with "opus"             | `BIG_MODEL`   | Default: `gpt-4o`      |

### Provider Examples

#### OpenAI (Static Mode)

```bash
OPENAI_API_KEY="sk-your-openai-key"
OPENAI_BASE_URL="https://api.openai.com/v1"
BIG_MODEL="gpt-4o"
MIDDLE_MODEL="gpt-4o"
SMALL_MODEL="gpt-4o-mini"
```

#### OpenAI (Dynamic Mode)

```bash
# Don't set OPENAI_API_KEY
# Each client uses their own API key
OPENAI_BASE_URL="https://api.openai.com/v1"
BIG_MODEL="gpt-4o"
MIDDLE_MODEL="gpt-4o"
SMALL_MODEL="gpt-4o-mini"
```

#### Azure OpenAI

```bash
OPENAI_API_KEY="your-azure-key"
OPENAI_BASE_URL="https://your-resource.openai.azure.com/openai/deployments/your-deployment"
BIG_MODEL="gpt-4"
MIDDLE_MODEL="gpt-4"
SMALL_MODEL="gpt-35-turbo"
```

#### Local Models (Ollama)

```bash
OPENAI_API_KEY="dummy-key"  # Required but can be dummy
OPENAI_BASE_URL="http://localhost:11434/v1"
BIG_MODEL="llama3.1:70b"
MIDDLE_MODEL="llama3.1:70b"
SMALL_MODEL="llama3.1:8b"
```

#### Other Providers

Any OpenAI-compatible API can be used by setting the appropriate `OPENAI_BASE_URL`.

## Usage Examples

### Basic Chat

```python
import httpx

response = httpx.post(
    "http://localhost:8082/v1/messages",
    json={
        "model": "claude-3-5-sonnet-20241022",  # Maps to MIDDLE_MODEL
        "max_tokens": 100,
        "messages": [
            {"role": "user", "content": "Hello!"}
        ]
    }
)
```

## Integration with Claude Code

This proxy is designed to work seamlessly with Claude Code CLI:

### Static Mode (Single API Key)

```bash
# Start the proxy with your OpenAI key
export OPENAI_API_KEY="sk-your-openai-key"
python start_proxy.py

# Use Claude Code with any API key value
ANTHROPIC_BASE_URL=http://localhost:8082 ANTHROPIC_API_KEY="any-value" claude
```

### Dynamic Mode (Multiple Client Keys)

```bash
# Start the proxy without OPENAI_API_KEY
python start_proxy.py

# Each client uses their own OpenAI key
ANTHROPIC_BASE_URL=http://localhost:8082 ANTHROPIC_API_KEY="client-openai-key" claude
```

### Permanent Setup

```bash
# Add to your shell profile
export ANTHROPIC_BASE_URL=http://localhost:8082

# Then simply run
claude
```

## Testing

Test the proxy functionality:

```bash
# Run comprehensive tests
python src/test_claude_to_openai.py
```

## Development

### Using UV

```bash
# Install dependencies
uv sync

# Run server
uv run claude-code-proxy

# Format code
uv run black src/
uv run isort src/

# Type checking
uv run mypy src/
```

### Project Structure

```
claude-code-proxy/
├── src/
│   ├── main.py  # Main server
│   ├── test_claude_to_openai.py    # Tests
│   └── [other modules...]
├── start_proxy.py                  # Startup script
├── .env.example                    # Config template
└── README.md                       # This file
```

## Dynamic API Key Feature

The proxy supports two modes of operation:

### Static Mode (Default)
- Configure `OPENAI_API_KEY` on the server
- All clients share the same API key
- Client keys are validated against `ANTHROPIC_API_KEY` if set

### Dynamic Mode
- Don't configure `OPENAI_API_KEY` on the server
- Each client request uses their own API key
- Client keys are validated to ensure proper OpenAI format
- Supports multiple clients with different API keys

### Benefits of Dynamic Mode
- **Multi-tenant**: Serve multiple users with their own API keys
- **No key sharing**: Clients keep their keys private
- **Usage tracking**: Each client's usage is billed to their own account
- **Flexible**: Works with any OpenAI-compatible provider

### Client Management
The proxy includes intelligent client management:
- **LRU Caching**: Active clients are cached for performance
- **Automatic Cleanup**: Idle clients are cleaned up after 1 hour
- **Resource Limits**: Maximum 50 concurrent clients to prevent resource exhaustion
- **Metrics**: Monitor client usage via `/metrics` endpoint

## Performance

- **Async/await** for high concurrency
- **Connection pooling** per client for efficiency
- **Streaming support** for real-time responses
- **Configurable timeouts** and retries
- **Smart error handling** with detailed logging
- **Efficient client management** with LRU caching

## License

MIT License
