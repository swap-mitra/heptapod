"""The full demo task (PRD: FR5, Goal 1) against the three compose mocks, with a scripted model
in place of the LLM. Needs `docker compose up -d --wait`; run with `pytest tests/integration`."""

import json
import logging
import uuid
from types import SimpleNamespace as NS

from agent.__main__ import load_dotenv
from agent.runtime import run_anthropic
from core.registry import Registry
from tests.test_runtime import ScriptedClient, text, tool_use


def test_demo_task_across_all_three_backends(caplog):
    # The mocks' throwaway credentials; values already in the environment win.
    load_dotenv(".env.example")
    registry = Registry.from_config("adapters.toml")
    # The mocks keep writes in memory across runs, so a fresh value proves this run's update.
    phone = f"+1-555-{uuid.uuid4().int % 10000:04d}"
    client = ScriptedClient([
        NS(stop_reason="tool_use", content=[tool_use("t1", "crm", {"operation": "list_customers"})]),
        NS(stop_reason="tool_use", content=[tool_use("t2", "ticketing", {"operation": "get_ticket", "ticket_no": "T-9001"})]),
        NS(stop_reason="tool_use", content=[tool_use("t3", "inventory", {"operation": "get_stock", "partNumber": "BP-310"})]),
        NS(stop_reason="tool_use", content=[tool_use("t4", "crm", {"operation": "update_customer", "customer_id": "C-1001", "phone": phone})]),
        NS(stop_reason="end_turn", content=[text("done")]),
    ])
    with caplog.at_level(logging.INFO):
        assert run_anthropic("Ada called: find her ticket, check the part, update her phone.", registry, client) == "done"
        stored = registry.call("crm", {"operation": "get_customer", "customer_id": "C-1001"})

    # What the model was shown links up across systems: customer -> ticket -> stocked part.
    results = [json.loads(r["messages"][-1]["content"][0]["content"]) for r in client.requests[1:]]
    customers, ticket, stock, updated = results
    ada = next(c for c in customers["customers"] if c["name"] == "Ada Lindqvist")
    assert "T-9001" in ada["open_ticket_ids"]
    assert (ticket["cust_ref"], ticket["state"], ticket["part_ref"]) == ("C-1001", "open", "BP-310")
    assert sum(int(loc["quantityOnHand"]) for loc in stock["locations"]) > 0
    assert updated["phone"] == phone
    assert stored.data["phone"] == phone

    # One registry log line per tool call, in order (NFR Observability); the check call is last.
    lines = [r.getMessage().split(" ")[0:2] for r in caplog.records if r.name == "core.registry"]
    assert lines == [
        ["crm.list_customers", "ok"],
        ["ticketing.get_ticket", "ok"],
        ["inventory.get_stock", "ok"],
        ["crm.update_customer", "ok"],
        ["crm.get_customer", "ok"],
    ]
