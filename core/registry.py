"""Tool Registry: loads adapters from adapters.toml, exposes them to the agent as tools, and
routes calls with credentials from the Auth Layer (HLD: Core Components, Registry Config;
PRD: FR2, FR6, FR7, NFR Observability)."""

import importlib
import logging
import time
import tomllib
from pathlib import Path
from typing import Any

from core import auth
from core.adapter import Adapter, AdapterResult

log = logging.getLogger(__name__)


class Registry:
    def __init__(self, adapters: list[Adapter]):
        self.adapters: dict[str, Adapter] = {}
        for adapter in adapters:
            if adapter.name in self.adapters:
                raise auth.ConfigError(f"duplicate adapter name {adapter.name!r}")
            # Resolving once here makes a missing secret or unknown scheme fail at startup,
            # not on the agent's first call.
            auth.resolve(adapter.auth_config)
            self.adapters[adapter.name] = adapter

    @classmethod
    def from_config(cls, path: str | Path) -> "Registry":
        """Build a registry from adapters.toml: one table per adapter, `class = "module:Class"`,
        every other key passed to the class as a constructor kwarg."""
        with open(path, "rb") as f:
            tables = tomllib.load(f)
        return cls([_construct(key, dict(table)) for key, table in tables.items()])

    def tools(self) -> list[dict[str, Any]]:
        """Tool definitions for the LLM, one per adapter."""
        return [
            {"name": a.name, "description": a.description, "input_schema": a.input_schema}
            for a in self.adapters.values()
        ]

    def call(self, name: str, input: dict[str, Any]) -> AdapterResult:
        """Run one tool call. Always returns an AdapterResult; nothing raises to the agent (FR7)."""
        operation = input.get("operation")
        start = time.perf_counter()
        adapter = self.adapters.get(name)
        if adapter is None:
            result = AdapterResult(success=False, error=f"unknown tool {name!r}")
        else:
            try:
                result = adapter.execute(input, auth.resolve(adapter.auth_config))
            except Exception as exc:
                # Adapters must return failures as data; reaching here is a bug in that adapter.
                log.exception("adapter %s raised instead of returning an AdapterResult", name)
                result = AdapterResult(success=False, error=f"internal error in {name}: {exc}")
        latency_ms = (time.perf_counter() - start) * 1000
        log.info(
            "%s.%s %s %.1fms",
            name,
            operation,
            "ok" if result.success else f"failed: {result.error}",
            latency_ms,
            extra={"system": name, "operation": operation, "latency_ms": latency_ms, "success": result.success},
        )
        return result


def _construct(key: str, table: dict[str, Any]) -> Adapter:
    path = table.pop("class", None)
    if not isinstance(path, str) or ":" not in path:
        raise auth.ConfigError(f"[{key}] needs class = \"module:Class\", got {path!r}")
    module_name, _, class_name = path.partition(":")
    try:
        adapter_class = getattr(importlib.import_module(module_name), class_name)
    except (ImportError, AttributeError) as exc:
        raise auth.ConfigError(f"[{key}] cannot import {path!r}: {exc}") from exc
    try:
        return adapter_class(**table)
    except TypeError as exc:
        raise auth.ConfigError(f"[{key}] keys do not match {path!r}'s constructor: {exc}") from exc
