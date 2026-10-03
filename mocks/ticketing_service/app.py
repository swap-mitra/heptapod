"""Ticketing mock (SQL-backed): support tickets in SQLite, reached over HTTP by posting one
SQL statement with bound parameters. Headline quirk: every Nth query is rate limited with
HTTP 429 and a Retry-After header, on a fixed schedule so tests are reproducible
(HLD: Mock Backends). Column names follow this system's own conventions (`cust_ref`,
`part_ref`, `state`), not the CRM's. All data is synthetic."""

import os
import secrets
import sqlite3
import threading
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

SCHEMA = """
CREATE TABLE tickets (
    ticket_no   TEXT PRIMARY KEY,
    cust_ref    TEXT NOT NULL,
    summary     TEXT NOT NULL,
    part_ref    TEXT,
    state       TEXT NOT NULL CHECK (state IN ('open', 'in_progress', 'closed')),
    assigned_to TEXT,
    opened_at   TEXT NOT NULL
);
INSERT INTO tickets VALUES
    ('T-8999', 'C-1002', 'Invoice copy requested',          NULL,     'closed',      'm.haas', '2026-08-30'),
    ('T-9001', 'C-1001', 'Bilge pump cycling continuously', 'BP-310', 'open',        NULL,     '2026-09-12'),
    ('T-9002', 'C-1003', 'Conveyor belt slipping',          'CB-075', 'open',        'r.ito',  '2026-09-18'),
    ('T-9003', 'C-1005', 'Inverter fault code E42',         'IV-550', 'in_progress', 'm.haas', '2026-09-20'),
    ('T-9004', 'C-1003', 'Replacement sensor arrived bent', 'SN-018', 'open',        NULL,     '2026-09-25');
"""


class Query(BaseModel):
    sql: str
    params: list[Any] = []


def create_app(username: str | None = None, password: str | None = None, rate_limit_every: int | None = None) -> FastAPI:
    """Fresh app with its own seeded in-memory database. Unset arguments come from
    TICKETING_USER, TICKETING_PASSWORD and TICKETING_RATE_LIMIT_EVERY (default 5)."""
    username = username or os.environ["TICKETING_USER"]
    password = password or os.environ["TICKETING_PASSWORD"]
    rate_limit_every = rate_limit_every or int(os.environ.get("TICKETING_RATE_LIMIT_EVERY", "5"))

    # ponytail: one connection behind a lock; fine for a mock, not for real load.
    db = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    lock = threading.Lock()
    count = 0
    basic = HTTPBasic()

    def require_login(given: HTTPBasicCredentials = Depends(basic)):
        ok_user = secrets.compare_digest(given.username.encode(), username.encode())
        ok_pass = secrets.compare_digest(given.password.encode(), password.encode())
        if not (ok_user and ok_pass):
            raise HTTPException(401, "invalid username or password", headers={"WWW-Authenticate": "Basic"})

    def rate_limit():
        nonlocal count
        with lock:
            count += 1
            limited = count % rate_limit_every == 0
        if limited:
            raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": "1"})

    app = FastAPI(title="Ticketing mock")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/query", dependencies=[Depends(require_login), Depends(rate_limit)])
    def query(body: Query):
        # sqlite3 runs one statement per call, so a query cannot smuggle in a second one.
        try:
            with lock:
                rows = [dict(row) for row in db.execute(body.sql, body.params)]
        except sqlite3.Error as exc:
            raise HTTPException(400, f"SQL error: {exc}")
        return {"rows": rows}

    return app
