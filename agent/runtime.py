"""Agent runtime: one plain tool-calling loop over the registry's tools (HLD: Core Components;
PRD: FR5). It knows tools only by name and schema, never which backend is behind one."""

import json
import logging
from typing import Any

from core.registry import Registry

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5"
MAX_TOKENS = 16000
SYSTEM = (
    "You operate business systems through tools. Each tool is one system; choose what it does "
    "with the `operation` argument. Rely on tool results, not assumptions. When a tool returns "
    "an error, decide whether to correct the call, try another route, or report the problem. "
    "Finish with a short summary of what you found and what you changed."
)


def run(task: str, registry: Registry, client: Any, model: str = DEFAULT_MODEL, max_turns: int = 20) -> str:
    """Drive the model until it answers without calling a tool; return that answer.

    `client` is an `anthropic.Anthropic` (tests pass a scripted stand-in). Raises RuntimeError
    if the model stops for any other reason or runs past `max_turns`."""
    tools = registry.tools()
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    for _ in range(max_turns):
        response = client.beta.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            tools=tools,
            messages=messages,
            # On a safety decline, the API reruns the request on a fallback model it picks.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        # Full content, not just text: thinking and tool_use blocks must be sent back as-is.
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason == "end_turn":
            return "".join(block.text for block in response.content if block.type == "text")
        if response.stop_reason != "tool_use":
            raise RuntimeError(f"model stopped with stop_reason={response.stop_reason!r}")
        # All results for one turn go back in a single message, as the API expects.
        messages.append({
            "role": "user",
            "content": [_run_tool(registry, block) for block in response.content if block.type == "tool_use"],
        })
    raise RuntimeError(f"no final answer after {max_turns} turns")


def _run_tool(registry: Registry, block: Any) -> dict[str, Any]:
    result = registry.call(block.name, block.input)
    payload = result.data if result.success else {"error": result.error}
    log.info("tool %s input=%s -> %s", block.name, json.dumps(block.input), json.dumps(payload))
    return {
        "type": "tool_result",
        "tool_use_id": block.id,
        "content": json.dumps(payload),
        "is_error": not result.success,
    }
