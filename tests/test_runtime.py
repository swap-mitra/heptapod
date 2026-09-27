import json
from types import SimpleNamespace as NS

import pytest

from agent.runtime import run
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
    assert run("find C-1", registry, client, model="m") == "done"
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
    run("t", registry, client)
    assert [b["tool_use_id"] for b in client.requests[1]["messages"][-1]["content"]] == ["a", "b"]


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_unexpected_stop_fails_loudly(stop_reason):
    client = ScriptedClient([NS(stop_reason=stop_reason, content=[])])
    with pytest.raises(RuntimeError, match=stop_reason):
        run("t", FakeRegistry([]), client)


def test_turn_limit_fails_loudly():
    client = ScriptedClient([NS(stop_reason="tool_use", content=[tool_use("a", "crm", {})])] * 3)
    with pytest.raises(RuntimeError, match="3 turns"):
        run("t", FakeRegistry([AdapterResult(True, data={})] * 3), client, max_turns=3)
