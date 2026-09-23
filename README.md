# heptapod

Universal System-Adapter Kit: a Python library giving an LLM agent one uniform tool interface across REST, SOAP, and SQL backends, with authentication translated underneath so agent code never changes per system.

- Requirements: [specs/PRD.md](specs/PRD.md)
- Design: [specs/HLD.md](specs/HLD.md)
- Contributor workflow: [AGENTS.md](AGENTS.md)

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
