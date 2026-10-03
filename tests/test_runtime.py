import json
from types import SimpleNamespace as NS

import pytest

from agent.runtime import run_anthropic, run_openrouter
from core.adapter import AdapterResult


class FakeRegistry:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def tools(self):
        return [{"name": "crm", "description": "d", "input_schema": {"type": "object"}}]

    def call(self, name, input):
        self.calls.append((name, input))
        return self.results.pop(0)


class ScriptedClient:
    """Stands in for anthropic.Anthropic: replays canned responses and records each request."""

    def __init__(self, responses):
        self.responses = responses
        self.requests = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


def tool_use(id, name, input):
    return NS(type="tool_use", id=id, name=name, input=input)


def text(t):
    return NS(type="text", text=t)


def test_runs_tools_in_order_and_returns_final_text():
    registry = FakeRegistry([AdapterResult(True, data={"id": "C-1"}), AdapterResult(False, error="HTTP 404")])
    client = ScriptedClient([
        NS(stop_reason="tool_use", content=[text("looking"), tool_use("t1", "crm", {"operation": "get_customer"})]),
        NS(stop_reason="tool_use", content=[tool_use("t2", "crm", {"operation": "get_customer", "customer_id": "x"})]),
        NS(stop_reason="end_turn", content=[text("done")]),
    ])
    assert run_anthropic("find C-1", registry, client, model="m") == "done"
    assert [c[1]["operation"] for c in registry.calls] == ["get_customer", "get_customer"]

    # Tools come from the registry; results go back as tool_result blocks, failures flagged.
    assert client.requests[0]["tools"] == registry.tools() and client.requests[0]["model"] == "m"
    ok, failed = client.requests[1]["messages"][-1]["content"][0], client.requests[2]["messages"][-1]["content"][0]
    assert (ok["tool_use_id"], json.loads(ok["content"]), ok["is_error"]) == ("t1", {"id": "C-1"}, False)
    assert (failed["tool_use_id"], json.loads(failed["content"]), failed["is_error"]) == ("t2", {"error": "HTTP 404"}, True)


def test_parallel_tool_calls_return_in_one_message():
    registry = FakeRegistry([AdapterResult(True, data={}), AdapterResult(True, data={})])
    client = ScriptedClient([
        NS(stop_reason="tool_use", content=[tool_use("a", "crm", {}), tool_use("b", "crm", {})]),
        NS(stop_reason="end_turn", content=[text("ok")]),
    ])
    run_anthropic("t", registry, client)
    assert [b["tool_use_id"] for b in client.requests[1]["messages"][-1]["content"]] == ["a", "b"]


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_unexpected_stop_fails_loudly(stop_reason):
    client = ScriptedClient([NS(stop_reason=stop_reason, content=[])])
    with pytest.raises(RuntimeError, match=stop_reason):
        run_anthropic("t", FakeRegistry([]), client)


def test_turn_limit_fails_loudly():
    client = ScriptedClient([NS(stop_reason="tool_use", content=[tool_use("a", "crm", {})])] * 3)
    with pytest.raises(RuntimeError, match="3 turns"):
        run_anthropic("t", FakeRegistry([AdapterResult(True, data={})] * 3), client, max_turns=3)


class ScriptedOpenRouter:
    """Stands in for OpenRouterClient: replays canned chat-completion bodies, records payloads."""

    def __init__(self, responses):
        self.responses = responses
        self.payloads = []

    def complete(self, payload):
        self.payloads.append({**payload, "messages": list(payload["messages"])})
        return self.responses.pop(0)


def or_reply(content=None, tool_calls=None, finish_reason="stop"):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message, "finish_reason": finish_reason}]}


def or_call(id, name, arguments):
    return {"id": id, "type": "function", "function": {"name": name, "arguments": arguments}}


def test_openrouter_runs_tools_and_returns_final_text():
    registry = FakeRegistry([AdapterResult(True, data={"id": "C-1"}), AdapterResult(False, error="HTTP 404")])
    client = ScriptedOpenRouter([
        or_reply(tool_calls=[or_call("c1", "crm", '{"operation": "get_customer"}'), or_call("c2", "crm", "{}")], finish_reason="tool_calls"),
        or_reply("done"),
    ])
    assert run_openrouter("find C-1", registry, client, model="m") == "done"
    assert registry.calls == [("crm", {"operation": "get_customer"}), ("crm", {})]

    first = client.payloads[0]
    assert first["model"] == "m"
    assert first["tools"] == [{"type": "function", "function": {"name": "crm", "description": "d", "parameters": {"type": "object"}}}]
    assert [m["role"] for m in first["messages"]] == ["system", "user"]
    # Each result goes back as its own `tool` message, failures marked in the content.
    ok, failed = client.payloads[1]["messages"][-2:]
    assert (ok["role"], ok["tool_call_id"], json.loads(ok["content"])) == ("tool", "c1", {"id": "C-1"})
    assert (failed["tool_call_id"], json.loads(failed["content"])) == ("c2", {"error": "HTTP 404"})


def test_openrouter_bad_tool_arguments_go_back_to_the_model():
    registry = FakeRegistry([])
    client = ScriptedOpenRouter([
        or_reply(tool_calls=[or_call("c1", "crm", "{not json")]),
        or_reply("gave up"),
    ])
    assert run_openrouter("t", registry, client) == "gave up"
    assert registry.calls == []
    assert "invalid JSON" in json.loads(client.payloads[1]["messages"][-1]["content"])["error"]


def test_openrouter_truncated_reply_fails_loudly():
    client = ScriptedOpenRouter([or_reply("partial", finish_reason="length")])
    with pytest.raises(RuntimeError, match="length"):
        run_openrouter("t", FakeRegistry([]), client)


def test_openrouter_turn_limit_fails_loudly():
    client = ScriptedOpenRouter([or_reply(tool_calls=[or_call("c", "crm", "{}")])] * 2)
    with pytest.raises(RuntimeError, match="2 turns"):
        run_openrouter("t", FakeRegistry([AdapterResult(True, data={})] * 2), client, max_turns=2)
