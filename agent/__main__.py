"""Run one task: `python -m agent "find customer C-1001's open tickets"`.

Needs the mocks up (`docker compose up -d`) and their secrets in the environment.

HEPTAPOD_PROVIDER picks the LLM provider:
- `anthropic` (default): Anthropic credentials (ANTHROPIC_API_KEY or an `ant auth login` profile).
- `openrouter`: OPENROUTER_API_KEY; defaults to free models.
HEPTAPOD_MODEL overrides the provider's default model; HEPTAPOD_CONFIG the adapters.toml path.
Any of these can live in a local `.env` file (see `.env.example`); the shell's values win."""

import logging
import os
import sys
from pathlib import Path

import anthropic

from agent.openrouter import OpenRouterClient
from agent.runtime import ANTHROPIC_DEFAULT_MODEL, OPENROUTER_DEFAULT_MODEL, run_anthropic, run_openrouter
from core.registry import Registry


def load_dotenv(path: str | Path = ".env") -> None:
    """Set env vars from `KEY=value` lines in `path`, if it exists. Vars already set in the
    shell are kept; blank values are skipped."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            # The line itself is not echoed: it may be a pasted secret.
            sys.exit(f"{path} line {number}: expected KEY=value")
        value = value.strip().strip("\"'")
        if value:
            os.environ.setdefault(key.strip(), value)


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit('usage: python -m agent "<task>"')
    load_dotenv()
    provider = os.environ.get("HEPTAPOD_PROVIDER", "anthropic")
    model = os.environ.get("HEPTAPOD_MODEL")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    registry = Registry.from_config(os.environ.get("HEPTAPOD_CONFIG", "adapters.toml"))

    if provider == "anthropic":
        answer = run_anthropic(sys.argv[1], registry, anthropic.Anthropic(), model=model or ANTHROPIC_DEFAULT_MODEL)
    elif provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            sys.exit("HEPTAPOD_PROVIDER=openrouter needs OPENROUTER_API_KEY")
        answer = run_openrouter(sys.argv[1], registry, OpenRouterClient(api_key), model=model or OPENROUTER_DEFAULT_MODEL)
    else:
        sys.exit(f"unknown HEPTAPOD_PROVIDER {provider!r}; expected 'anthropic' or 'openrouter'")
    print(answer)


if __name__ == "__main__":
    main()
