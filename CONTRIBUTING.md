# Contributing to Heptapod

Thanks for your interest in improving Heptapod. This guide covers how to set up a development environment, the conventions the code follows, and how to propose a change.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

You need Python 3.12 or newer and Docker with Compose v2.

```bash
git clone https://github.com/swap-mitra/heptapod.git
cd heptapod
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

`pytest` runs the whole suite without Docker or an LLM key: adapter tests start each mock in-process, and agent loop tests replay scripted model responses. To run the agent itself, follow the [Quick start](README.md#quick-start).

## Proposing a change

1. For anything beyond a small fix, open an issue first so the approach can be agreed before you write code.
2. Create a branch from `main`.
3. Make the change with tests. New behavior needs a test; a bug fix starts with a test that reproduces the bug and fails without the fix.
4. Run `pytest` and make sure it passes.
5. Open a pull request and fill in the template.

CI runs the full suite against the three mock backends on every pull request, and a pull request must pass it before merging.

## Conventions

- **Follow the existing code.** When in doubt, match the nearest existing pattern rather than introducing a new one.
- **Dependencies:** prefer the standard library and the dependencies already in `pyproject.toml`. A new dependency needs a stated reason in the pull request.
- **Adapters never raise.** An adapter's `execute()` catches its backend's failures and returns an `AdapterResult` with `success=False` and a readable `error`.
- **Adding a backend** is one adapter class, one `adapters.toml` table, and one test file, with no changes to the registry, auth layer, or agent. See [Adding a backend](README.md#adding-a-backend). If a backend cannot be added that way, open an issue: that is a design question, not a special case.
- **SQL** uses bound parameters only.
- **No real credentials or real customer data**, anywhere, including mocks and tests. Mock credentials are throwaway fixtures.
- **Comments** explain why, not what. Public modules, classes, and functions have docstrings.

## Commit messages

- Imperative subject line under about 72 characters, for example `Add retry to ticketing adapter`.
- A body that explains why the change is needed, not a list of what changed.
- One logical change per commit.

## Reporting bugs and security issues

Report bugs through [GitHub issues](https://github.com/swap-mitra/heptapod/issues/new/choose). Report security vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).
