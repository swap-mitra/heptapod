# AGENTS.md

## Project

Heptapod, a Python library giving an LLM agent one uniform tool interface across REST, SOAP, and SQL backends, with authentication translated underneath so agent code never changes per system.

Full requirements: `specs/PRD.md`. Full design: `specs/HLD.md`. `specs/` is local only (gitignored), never committed. This file is workflow and conventions only, it is not a source of truth for what to build.

## Spec-driven development

This repo is spec-driven. `specs/PRD.md` and `specs/HLD.md` are the source of truth, not this file, and not any one conversation.

Before implementing anything:

1. Read `specs/PRD.md` for what's in scope and what "done" means, the numbered FRs, the NFRs, and the goals' success metrics.
2. Read `specs/HLD.md` for the architecture, the Adapter contract, and where a change belongs.
3. If a task isn't covered by either spec, or contradicts one, stop and flag it rather than improvising. Specs get updated deliberately, never silently overridden by code.
4. When a spec and the code disagree after a change, update the spec in the same change. Don't let them drift apart.

Adding a new backend: follow "Extensibility" in `specs/HLD.md` exactly, one adapter class plus one config entry, no changes to `registry.py`, `auth.py`, or `runtime.py`. If a backend can't be added that way, that's a spec problem to raise, not a reason to special-case it in code.

## Repo layout

Mirrors `specs/HLD.md` → Repo Layout & Tech Stack:

```
heptapod/
  core/            # Adapter protocol, Tool Registry, Auth Layer
  adapters/        # one file per backend
  mocks/           # the three standalone mock services (REST, SOAP, SQL)
  agent/           # the tool-calling loop
  tests/
  specs/           # PRD.md, HLD.md, PLAN.md; local only, read these first
  docker-compose.yml
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d        # brings up the three mock backends
```

## Testing

```bash
pytest                        # adapter + registry tests; no LLM calls, mocks don't need to be running
pytest tests/integration      # requires docker compose up first; runs the full agent demo task
```

Every new adapter needs unit tests against its own mock, independent of the LLM, per Testing & CI Strategy in `specs/HLD.md`. A PR that adds an adapter without its own test file should fail CI, not just review.

## Code style

- Follow existing conventions in this repo over generic ones. If something isn't already established here, match the nearest existing pattern rather than inventing a new one.
- Prefer the stdlib and the dependencies already in `pyproject.toml` over adding new ones. A new dependency needs a one-line reason in the PR description.
- No speculative abstractions: build the interface the current three backends need, not one sized for backends that don't exist yet.
- Handle errors at trust boundaries: every adapter's `execute()` catches its own backend's failures and returns a structured `AdapterResult`. A raw exception never crosses from an adapter into the registry or the agent.

## Commits & PRs

- No `Co-Authored-By` trailer and no "Generated with Claude Code" (or any tool) footer in commits or PR bodies.
- Reference the FR or NFR id a change addresses in the PR description, e.g. "Implements FR4".
- CI gate: `docker compose up` for the three mocks, then the full test suite, on every PR, per `specs/HLD.md` Testing & CI Strategy.

## Security

- No real credentials in the repo, ever. `SecretResolver` reads from env vars in v1; mocks use throwaway fixture credentials only.
- Never commit anything resembling real client or customer data, even in the mocks, per the Demo Plan in `specs/PRD.md`.
