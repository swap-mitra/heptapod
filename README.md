# heptapod

Heptapod is a Python library giving an LLM agent one uniform tool interface across REST, SOAP, and SQL backends, with authentication translated underneath so agent code never changes per system.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

`pytest` starts each mock backend in-process, so it needs neither Docker nor an API key.

## Running the agent

```bash
cp .env.example .env               # then fill in your LLM key
docker compose up -d --wait        # mock backends
python -m agent "Find customer C-1003 and list their open ticket ids"
```

`python -m agent` reads `.env` (gitignored) for any variable not already set in the shell.

Pick the LLM provider with `HEPTAPOD_PROVIDER`:

| Provider | Set | Default model |
| --- | --- | --- |
| `anthropic` (default) | `ANTHROPIC_API_KEY`, or sign in with `ant auth login` | `claude-opus-5` |
| `openrouter` | `OPENROUTER_API_KEY` (free account at openrouter.ai) | `openrouter/free`, which routes to a free tool-capable model |

`HEPTAPOD_MODEL` overrides the default. `openrouter/free` may pick a different model each turn; pin one (e.g. `HEPTAPOD_MODEL=qwen/qwen3.8-27b:free`) for repeatable runs. Free models are rate limited, and the client retries those responses a few times before failing.

Each tool call is logged with system, operation, latency, and outcome.

## Adding a backend

1. Write one adapter class in `adapters/`, documenting its auth and operations in the module docstring.
2. Add one table to `adapters.toml` with its import path and `base_url`.
3. Add `tests/test_<name>.py` against its mock. The suite fails without it.
