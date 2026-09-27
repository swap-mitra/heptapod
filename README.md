# heptapod

Heptapod is a Python library giving an LLM agent one uniform tool interface across REST, SOAP, and SQL backends, with authentication translated underneath so agent code never changes per system.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
