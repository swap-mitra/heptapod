"""CRM mock (REST + JSON): customer records, contact info, and references to each customer's
open support tickets. Headline quirk: list results are cursor-paginated with a small page
size (HLD: Mock Backends). All data is synthetic."""

import base64
import copy
import os
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

PAGE_SIZE = 2

SEED = [
    {"id": "C-1001", "name": "Ada Lindqvist", "email": "ada@lindqvist-marine.example", "phone": "+1-555-0101", "open_ticket_ids": ["T-9001"]},
    {"id": "C-1002", "name": "Bruno Tavares", "email": "bruno@tavares-foods.example", "phone": "+1-555-0102", "open_ticket_ids": []},
    {"id": "C-1003", "name": "Chen Wei", "email": "chen@wei-logistics.example", "phone": "+1-555-0103", "open_ticket_ids": ["T-9002", "T-9004"]},
    {"id": "C-1004", "name": "Dana Moreau", "email": "dana@moreau-studio.example", "phone": "+1-555-0104", "open_ticket_ids": []},
    {"id": "C-1005", "name": "Emeka Obi", "email": "emeka@obi-energy.example", "phone": "+1-555-0105", "open_ticket_ids": ["T-9003"]},
]


class NewCustomer(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None


class ContactUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"offset:{offset}".encode()).decode()


def _decode_cursor(cursor: str) -> int:
    try:
        prefix, _, offset = base64.urlsafe_b64decode(cursor).decode().partition(":")
        if prefix != "offset":
            raise ValueError(prefix)
        return int(offset)
    except ValueError:
        raise HTTPException(400, "invalid cursor")


def create_app(api_key: str | None = None) -> FastAPI:
    """Fresh app with its own copy of the seed data. Reads CRM_API_KEY when no key is given."""
    api_key = api_key or os.environ["CRM_API_KEY"]
    customers = {c["id"]: c for c in copy.deepcopy(SEED)}

    def require_key(x_api_key: str | None = Header(default=None)):
        if x_api_key is None or not secrets.compare_digest(x_api_key, api_key):
            raise HTTPException(401, "invalid or missing X-API-Key")

    app = FastAPI(title="CRM mock", dependencies=[Depends(require_key)])

    def lookup(customer_id: str) -> dict:
        if customer_id not in customers:
            raise HTTPException(404, f"customer {customer_id} not found")
        return customers[customer_id]

    @app.get("/customers")
    def list_customers(cursor: str | None = None):
        start = _decode_cursor(cursor) if cursor else 0
        ids = sorted(customers)
        end = start + PAGE_SIZE
        return {
            "items": [customers[i] for i in ids[start:end]],
            "next_cursor": _encode_cursor(end) if end < len(ids) else None,
        }

    @app.get("/customers/{customer_id}")
    def get_customer(customer_id: str):
        return lookup(customer_id)

    @app.post("/customers", status_code=201)
    def create_customer(body: NewCustomer):
        customer_id = f"C-{1001 + len(customers)}"
        customers[customer_id] = {"id": customer_id, **body.model_dump(), "open_ticket_ids": []}
        return customers[customer_id]

    @app.patch("/customers/{customer_id}")
    def update_customer(customer_id: str, body: ContactUpdate):
        customer = lookup(customer_id)
        customer.update(body.model_dump(exclude_unset=True))
        return customer

    return app
