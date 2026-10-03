"""Ticketing adapter (SQL over HTTP).

Auth: HTTP basic. Secrets: env vars `TICKETING_USER` and `TICKETING_PASSWORD`.

Operations, chosen with the `operation` argument:
- `list_tickets(cust_ref?, state?)`: tickets, optionally filtered by customer and/or state.
- `get_ticket(ticket_no)`: one ticket.
- `create_ticket(cust_ref, summary, part_ref?)`: opens a ticket; returns it with its number.
- `update_ticket(ticket_no, state?, assigned_to?)`: changes only the fields given.

A ticket is `{ticket_no, cust_ref, summary, part_ref, state, assigned_to, opened_at}`.
`cust_ref` is a CRM customer id; `part_ref` is an inventory part number; `state` is one of
open, in_progress, closed. Every value reaches SQL as a bound parameter, never as SQL text.
The backend rate limits with HTTP 429; this adapter waits and retries a few times before
returning the failure. Failures come back as `AdapterResult(success=False)`, never raised.
"""

import json
import time
import urllib.error
import urllib.request
from typing import Any

from core.adapter import AdapterResult
from core.auth import Credentials

COLUMNS = "ticket_no, cust_ref, summary, part_ref, state, assigned_to, opened_at"
SQL = {
    "list_tickets": f"SELECT {COLUMNS} FROM tickets WHERE (?1 IS NULL OR cust_ref = ?1) AND (?2 IS NULL OR state = ?2) ORDER BY ticket_no",
    "get_ticket": f"SELECT {COLUMNS} FROM tickets WHERE ticket_no = ?1",
    # Numbering in the same statement as the insert, so two creates cannot take one number.
    "create_ticket": (
        "INSERT INTO tickets (ticket_no, cust_ref, summary, part_ref, state, opened_at) "
        "SELECT 'T-' || (COALESCE(MAX(CAST(SUBSTR(ticket_no, 3) AS INTEGER)), 9000) + 1), ?1, ?2, ?3, 'open', DATE('now') "
        f"FROM tickets RETURNING {COLUMNS}"
    ),
    "update_ticket": f"UPDATE tickets SET state = COALESCE(?2, state), assigned_to = COALESCE(?3, assigned_to) WHERE ticket_no = ?1 RETURNING {COLUMNS}",
}
REQUIRED = {
    "list_tickets": (),
    "get_ticket": ("ticket_no",),
    "create_ticket": ("cust_ref", "summary"),
    "update_ticket": ("ticket_no",),
}
PARAMS = {
    "list_tickets": ("cust_ref", "state"),
    "get_ticket": ("ticket_no",),
    "create_ticket": ("cust_ref", "summary", "part_ref"),
    "update_ticket": ("ticket_no", "state", "assigned_to"),
}
ATTEMPTS = 3
MAX_WAIT_S = 5.0
TIMEOUT_S = 10


class TicketingAdapter:
    name = "ticketing"
    description = (
        "Support ticketing system: tickets with a customer reference (cust_ref, a CRM customer "
        "id), summary, referenced part (part_ref, an inventory part number), state (open, "
        "in_progress, closed) and assignee. List, read, open, or update tickets."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": list(SQL)},
            "ticket_no": {"type": "string", "description": "e.g. T-9001. Required for get_ticket and update_ticket."},
            "cust_ref": {"type": "string", "description": "CRM customer id, e.g. C-1001. Filter for list_tickets; required for create_ticket."},
            "summary": {"type": "string", "description": "Required for create_ticket."},
            "part_ref": {"type": "string", "description": "Inventory part number, for create_ticket."},
            "state": {"type": "string", "enum": ["open", "in_progress", "closed"]},
            "assigned_to": {"type": "string"},
        },
        "required": ["operation"],
        "additionalProperties": False,
    }

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.auth_config = {"type": "basic", "username_ref": "TICKETING_USER", "password_ref": "TICKETING_PASSWORD"}

    def execute(self, input: dict[str, Any], credentials: Credentials) -> AdapterResult:
        operation = input.get("operation")
        if operation not in SQL:
            return AdapterResult(False, error=f"unknown operation {operation!r}; expected one of {list(SQL)}")
        missing = [arg for arg in REQUIRED[operation] if not input.get(arg)]
        if missing:
            return AdapterResult(False, error=f"{operation} requires {missing}")
        if operation == "update_ticket" and not (input.get("state") or input.get("assigned_to")):
            return AdapterResult(False, error="update_ticket has nothing to update; give state and/or assigned_to")

        try:
            rows = self._query(SQL[operation], [input.get(p) for p in PARAMS[operation]], credentials)
        except urllib.error.HTTPError as exc:
            return AdapterResult(False, error=f"ticketing returned HTTP {exc.code}: {_detail(exc)}")
        except (OSError, ValueError) as exc:  # connection failures, timeouts, bad JSON
            return AdapterResult(False, error=f"ticketing request failed: {exc}")

        if operation == "list_tickets":
            return AdapterResult(True, data={"tickets": rows})
        if not rows:
            return AdapterResult(False, error=f"ticket {input['ticket_no']} not found")
        return AdapterResult(True, data=rows[0])

    def _query(self, sql: str, params: list[Any], credentials: Credentials) -> list[dict]:
        request = urllib.request.Request(
            self.base_url + "/query",
            data=json.dumps({"sql": sql, "params": params}).encode(),
            method="POST",
            headers={**credentials, "Content-Type": "application/json", "Accept": "application/json"},
        )
        for attempt in range(1, ATTEMPTS + 1):
            try:
                with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                    return json.load(response)["rows"]
            except urllib.error.HTTPError as exc:
                if exc.code != 429 or attempt == ATTEMPTS:
                    raise
                time.sleep(_retry_after(exc))
        raise AssertionError("unreachable")


def _retry_after(exc: urllib.error.HTTPError) -> float:
    try:
        return min(float(exc.headers.get("Retry-After")), MAX_WAIT_S)
    except (TypeError, ValueError):
        return min(1.0, MAX_WAIT_S)


def _detail(exc: urllib.error.HTTPError) -> str:
    try:
        return str(json.load(exc)["detail"])
    except (ValueError, KeyError, TypeError, OSError):
        return str(exc.reason)
