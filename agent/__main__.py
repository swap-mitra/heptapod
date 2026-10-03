"""Run one task: `python -m agent "find customer C-1001's open tickets"`.

Needs the mocks up (`docker compose up -d`) and their secrets in the environment.

HEPTAPOD_PROVIDER picks the LLM provider:
- `anthropic` (default): Anthropic credentials (ANTHROPIC_API_KEY or an `ant auth login` profile).
- `openrouter`: OPENROUTER_API_KEY; defaults to free models.
HEPTAPOD_MODEL overrides the provider's default model; HEPTAPOD_CONFIG the adapters.toml path."""

import logging
import os
import sys

import anthropic

from agent.openrouter import OpenRouterClient
from agent.runtime import ANTHROPIC_DEFAULT_MODEL, OPENROUTER_DEFAULT_MODEL, run_anthropic, run_openrouter
from core.registry import Registry


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit('usage: python -m agent "<task>"')
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
