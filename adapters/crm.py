"""CRM adapter (REST + JSON).

Auth: API key sent in the `X-API-Key` header. Secret: env var `CRM_API_KEY`.

Operations, chosen with the `operation` argument:
- `list_customers`: every customer. The CRM paginates; this adapter follows every cursor,
  so the result is always complete.
- `get_customer(customer_id)`: one customer.
- `create_customer(name, email?, phone?)`: returns the new customer with its id.
- `update_customer(customer_id, name?, email?, phone?)`: changes only the fields given.

A customer is `{id, name, email, phone, open_ticket_ids}`; `open_ticket_ids` are ids in the
ticketing system. Backend failures come back as `AdapterResult(success=False)`, never raised.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from core.adapter import AdapterResult
from core.auth import Credentials

CONTACT_FIELDS = ("name", "email", "phone")
REQUIRED = {
    "list_customers": (),
    "get_customer": ("customer_id",),
    "create_customer": ("name",),
    "update_customer": ("customer_id",),
}
TIMEOUT_S = 10


class CrmAdapter:
    name = "crm"
    description = (
        "CRM system: customer records with contact info (name, email, phone) and the ids of "
        "each customer's open support tickets. Look customers up, create them, or update "
        "their contact info."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": list(REQUIRED)},
            "customer_id": {"type": "string", "description": "e.g. C-1001. Required for get_customer and update_customer."},
            "name": {"type": "string", "description": "Required for create_customer; optional for update_customer."},
            "email": {"type": "string"},
            "phone": {"type": "string"},
        },
        "required": ["operation"],
        "additionalProperties": False,
    }

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.auth_config = {"type": "api_key", "header": "X-API-Key", "secret_ref": "CRM_API_KEY"}

    def execute(self, input: dict[str, Any], credentials: Credentials) -> AdapterResult:
        operation = input.get("operation")
        if operation not in REQUIRED:
            return AdapterResult(False, error=f"unknown operation {operation!r}; expected one of {list(REQUIRED)}")
        missing = [arg for arg in REQUIRED[operation] if not input.get(arg)]
        if missing:
            return AdapterResult(False, error=f"{operation} requires {missing}")
        contact = {k: input[k] for k in CONTACT_FIELDS if k in input}
        if operation == "update_customer" and not contact:
            return AdapterResult(False, error=f"update_customer has nothing to update; give any of {list(CONTACT_FIELDS)}")

        try:
            if operation == "list_customers":
                data = {"customers": self._list_all(credentials)}
            elif operation == "get_customer":
                data = self._request("GET", self._customer_path(input), credentials)
            elif operation == "create_customer":
                data = self._request("POST", "/customers", credentials, body=contact)
            else:
                data = self._request("PATCH", self._customer_path(input), credentials, body=contact)
        except urllib.error.HTTPError as exc:
            return AdapterResult(False, error=f"CRM returned HTTP {exc.code}: {_detail(exc)}")
        except (OSError, ValueError) as exc:  # connection failures, timeouts, bad JSON
            return AdapterResult(False, error=f"CRM request failed: {exc}")
        return AdapterResult(True, data=data)

    def _list_all(self, credentials: Credentials) -> list[dict]:
        customers, cursor, seen = [], None, set()
        while True:
            page = self._request("GET", "/customers", credentials, query={"cursor": cursor} if cursor else None)
            customers.extend(page["items"])
            cursor = page.get("next_cursor")
            if not cursor:
                return customers
            if cursor in seen:
                raise ValueError(f"CRM returned cursor {cursor!r} twice")
            seen.add(cursor)

    @staticmethod
    def _customer_path(input: dict[str, Any]) -> str:
        return "/customers/" + urllib.parse.quote(str(input["customer_id"]), safe="")

    def _request(self, method: str, path: str, credentials: Credentials, body: dict | None = None, query: dict | None = None) -> Any:
        url = self.base_url + path + ("?" + urllib.parse.urlencode(query) if query else "")
        headers = {**credentials, "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return json.load(response)


def _detail(exc: urllib.error.HTTPError) -> str:
    try:
        return str(json.load(exc)["detail"])
    except (ValueError, KeyError, TypeError, OSError):
        return str(exc.reason)
