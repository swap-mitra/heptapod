"""Run one task: `python -m agent "find customer C-1001's open tickets"`.

Needs the mocks up (`docker compose up -d`), their secrets in the environment, and Anthropic
credentials (ANTHROPIC_API_KEY or an `ant auth login` profile). HEPTAPOD_MODEL overrides the
model; HEPTAPOD_CONFIG overrides the adapters.toml path."""

import logging
import os
import sys

import anthropic

from agent.runtime import DEFAULT_MODEL, run
from core.registry import Registry


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit('usage: python -m agent "<task>"')
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    registry = Registry.from_config(os.environ.get("HEPTAPOD_CONFIG", "adapters.toml"))
    print(run(sys.argv[1], registry, anthropic.Anthropic(), model=os.environ.get("HEPTAPOD_MODEL", DEFAULT_MODEL)))


if __name__ == "__main__":
    main()
