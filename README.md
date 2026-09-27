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
docker compose up -d --wait        # mock backends
export CRM_API_KEY=crm-dev-key     # throwaway fixture credential from docker-compose.yml
export ANTHROPIC_API_KEY=...       # or sign in with `ant auth login`
python -m agent "Find customer C-1003 and list their open ticket ids"
```

Each tool call is logged with system, operation, latency, and outcome. `HEPTAPOD_MODEL` overrides the model (default `claude-opus-5`).

## Adding a backend

1. Write one adapter class in `adapters/`, documenting its auth and operations in the module docstring.
2. Add one table to `adapters.toml` with its import path and `base_url`.
3. Add `tests/test_<name>.py` against its mock. The suite fails without it.
