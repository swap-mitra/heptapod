"""Agent runtime: one plain tool-calling loop over the registry's tools (HLD: Core Components;
PRD: FR5). It knows tools only by name and schema, never which backend is behind one.

There is one loop per LLM provider because their message formats differ; both hand every
tool call to the same registry the same way."""

import json
import logging
from typing import Any

from core.registry import Registry

log = logging.getLogger(__name__)

ANTHROPIC_DEFAULT_MODEL = "claude-opus-5"
# A router that picks among OpenRouter's free tool-capable models, so it keeps working as
# individual free models come, go, or hit rate limits. Pin one with HEPTAPOD_MODEL.
OPENROUTER_DEFAULT_MODEL = "openrouter/free"
MAX_TOKENS = 16000
SYSTEM = (
    "You operate business systems through tools. Each tool is one system; choose what it does "
    "with the `operation` argument. Rely on tool results, not assumptions. When a tool returns "
    "an error, decide whether to correct the call, try another route, or report the problem. "
    "Finish with a short summary of what you found and what you changed."
)


def run_anthropic(task: str, registry: Registry, client: Any, model: str = ANTHROPIC_DEFAULT_MODEL, max_turns: int = 20) -> str:
    """Drive a Claude model until it answers without calling a tool; return that answer.

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
        results = []
        for block in response.content:
            if block.type == "tool_use":
                content, is_error = _call_tool(registry, block.name, block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error})
        # All results for one turn go back in a single message, as the API expects.
        messages.append({"role": "user", "content": results})
    raise RuntimeError(f"no final answer after {max_turns} turns")


def run_openrouter(task: str, registry: Registry, client: Any, model: str = OPENROUTER_DEFAULT_MODEL, max_turns: int = 20) -> str:
    """Drive an OpenRouter model until it answers without calling a tool; return that answer.

    `client` is an `agent.openrouter.OpenRouterClient` (tests pass a scripted stand-in).
    Raises RuntimeError if the reply is truncated or the loop runs past `max_turns`."""
    tools = [
        {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
        for t in registry.tools()
    ]
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]
    for _ in range(max_turns):
        choice = client.complete({"model": model, "messages": messages, "tools": tools})["choices"][0]
        message = choice["message"]
        # Sent back as received so reasoning fields some models return are preserved.
        messages.append(message)
        calls = message.get("tool_calls") or []
        if not calls:
            if choice.get("finish_reason") == "length":
                raise RuntimeError("model reply was cut off (finish_reason='length')")
            return message.get("content") or ""
        for call in calls:
            try:
                arguments = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError as exc:
                # Smaller models sometimes emit malformed arguments; let the model retry.
                content = json.dumps({"error": f"invalid JSON in tool arguments: {exc}"})
            else:
                content, _ = _call_tool(registry, call["function"]["name"], arguments)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    raise RuntimeError(f"no final answer after {max_turns} turns")


def _call_tool(registry: Registry, name: str, input: dict[str, Any]) -> tuple[str, bool]:
    """Run one tool call through the registry; return (JSON result for the model, is_error)."""
    result = registry.call(name, input)
    payload = result.data if result.success else {"error": result.error}
    log.info("tool %s input=%s -> %s", name, json.dumps(input), json.dumps(payload))
    return json.dumps(payload), not result.success
