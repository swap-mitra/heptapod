import base64
from contextlib import ExitStack

import pytest

from adapters import ticketing
from adapters.ticketing import TicketingAdapter
from core.auth import resolve
from mocks.ticketing_service.app import create_app
from tests.conftest import serve

USER, PASSWORD = "support", "test-pass"


@pytest.fixture
def connect(monkeypatch):
    """Start the mock with a given rate-limit schedule; return (adapter, credentials)."""
    monkeypatch.setenv("TICKETING_USER", USER)
    monkeypatch.setenv("TICKETING_PASSWORD", PASSWORD)
    monkeypatch.setattr(ticketing, "MAX_WAIT_S", 0)  # honour Retry-After without slowing tests
    with ExitStack() as stack:

        def _connect(rate_limit_every=1000):
            adapter = TicketingAdapter(base_url=stack.enter_context(serve(create_app(USER, PASSWORD, rate_limit_every))))
            return adapter, resolve(adapter.auth_config)

        yield _connect


def test_list_filters_by_customer_and_state(connect):
    adapter, creds = connect()
    result = adapter.execute({"operation": "list_tickets", "cust_ref": "C-1003", "state": "open"}, creds)
    assert result.success
    assert [t["ticket_no"] for t in result.data["tickets"]] == ["T-9002", "T-9004"]


def test_get_ticket_includes_part_ref(connect):
    adapter, creds = connect()
    result = adapter.execute({"operation": "get_ticket", "ticket_no": "T-9001"}, creds)
    assert result.success and result.data["cust_ref"] == "C-1001" and result.data["part_ref"]


def test_create_assigns_next_number_and_opens(connect):
    adapter, creds = connect()
    result = adapter.execute({"operation": "create_ticket", "cust_ref": "C-1002", "summary": "Pump noise"}, creds)
    assert result.success
    assert (result.data["ticket_no"], result.data["state"]) == ("T-9005", "open")


def test_update_changes_only_given_fields(connect):
    adapter, creds = connect()
    before = adapter.execute({"operation": "get_ticket", "ticket_no": "T-9002"}, creds).data
    result = adapter.execute({"operation": "update_ticket", "ticket_no": "T-9002", "assigned_to": "r.ito"}, creds)
    assert result.data == {**before, "assigned_to": "r.ito"}


def test_invalid_state_is_rejected_by_the_database(connect):
    adapter, creds = connect()
    result = adapter.execute({"operation": "update_ticket", "ticket_no": "T-9002", "state": "lost"}, creds)
    assert not result.success and "400" in result.error


def test_unknown_ticket_is_structured_error(connect):
    adapter, creds = connect()
    for op in ("get_ticket", "update_ticket"):
        result = adapter.execute({"operation": op, "ticket_no": "T-0000", "state": "closed"}, creds)
        assert not result.success and "not found" in result.error


def test_injection_shaped_input_is_data(connect):
    adapter, creds = connect()
    attack = "C-1003' OR '1'='1"
    result = adapter.execute({"operation": "list_tickets", "cust_ref": attack}, creds)
    assert result.success and result.data["tickets"] == []
    created = adapter.execute({"operation": "create_ticket", "cust_ref": "C-1001", "summary": "x'); DROP TABLE tickets; --"}, creds)
    assert created.data["summary"] == "x'); DROP TABLE tickets; --"
    assert adapter.execute({"operation": "list_tickets"}, creds).success


def test_wrong_password_is_structured_error(connect):
    adapter, _ = connect()
    wrong = {"Authorization": "Basic " + base64.b64encode(f"{USER}:wrong".encode()).decode()}
    result = adapter.execute({"operation": "list_tickets"}, wrong)
    assert not result.success and "401" in result.error


def test_rate_limit_is_retried(connect):
    adapter, creds = connect(rate_limit_every=2)
    assert adapter.execute({"operation": "list_tickets"}, creds).success  # request 1
    assert adapter.execute({"operation": "list_tickets"}, creds).success  # request 2 is a 429, retry is 3


def test_persistent_rate_limit_is_structured_error(connect):
    adapter, creds = connect(rate_limit_every=1)
    result = adapter.execute({"operation": "list_tickets"}, creds)
    assert not result.success and "429" in result.error


@pytest.mark.parametrize(
    "input, match",
    [
        ({"operation": "delete_ticket"}, "operation"),
        ({"operation": "get_ticket"}, "ticket_no"),
        ({"operation": "create_ticket", "cust_ref": "C-1001"}, "summary"),
        ({"operation": "update_ticket", "ticket_no": "T-9001"}, "nothing to update"),
    ],
)
def test_invalid_input_is_structured_error(connect, input, match):
    adapter, creds = connect()
    result = adapter.execute(input, creds)
    assert not result.success and match in result.error
