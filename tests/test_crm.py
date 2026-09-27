import pytest

from adapters.crm import CrmAdapter
from core.auth import resolve
from mocks.crm_service.app import SEED, create_app
from tests.conftest import serve

KEY = "test-crm-key"


@pytest.fixture
def crm(monkeypatch):
    monkeypatch.setenv("CRM_API_KEY", KEY)
    with serve(create_app(KEY)) as url:
        adapter = CrmAdapter(base_url=url)
        yield adapter, resolve(adapter.auth_config)


def test_list_follows_every_page(crm):
    adapter, creds = crm
    result = adapter.execute({"operation": "list_customers"}, creds)
    assert result.success
    # The mock pages 2 at a time; the agent must still see every customer.
    assert [c["id"] for c in result.data["customers"]] == [c["id"] for c in SEED]


def test_get_customer_includes_ticket_refs(crm):
    adapter, creds = crm
    result = adapter.execute({"operation": "get_customer", "customer_id": "C-1001"}, creds)
    assert result.success and result.data["open_ticket_ids"] == ["T-9001"]


def test_create_then_get(crm):
    adapter, creds = crm
    created = adapter.execute({"operation": "create_customer", "name": "Iris Okafor", "email": "iris@okafor.example"}, creds)
    assert created.success
    fetched = adapter.execute({"operation": "get_customer", "customer_id": created.data["id"]}, creds)
    assert fetched.data["email"] == "iris@okafor.example" and fetched.data["open_ticket_ids"] == []


def test_update_changes_only_given_fields(crm):
    adapter, creds = crm
    before = adapter.execute({"operation": "get_customer", "customer_id": "C-1002"}, creds).data
    result = adapter.execute({"operation": "update_customer", "customer_id": "C-1002", "phone": "+1-555-0199"}, creds)
    assert result.success
    assert result.data == {**before, "phone": "+1-555-0199"}


def test_unknown_customer_is_structured_error(crm):
    adapter, creds = crm
    result = adapter.execute({"operation": "get_customer", "customer_id": "C-0000"}, creds)
    assert not result.success and "404" in result.error


def test_bad_key_is_structured_error(crm):
    adapter, _ = crm
    result = adapter.execute({"operation": "list_customers"}, {"X-API-Key": "wrong"})
    assert not result.success and "401" in result.error


@pytest.mark.parametrize(
    "input, match",
    [
        ({"operation": "delete_customer"}, "operation"),
        ({"operation": "get_customer"}, "customer_id"),
        ({"operation": "create_customer"}, "name"),
        ({"operation": "update_customer", "customer_id": "C-1001"}, "nothing to update"),
    ],
)
def test_invalid_input_is_structured_error(crm, input, match):
    adapter, creds = crm
    result = adapter.execute(input, creds)
    assert not result.success and match in result.error


def test_unreachable_backend_is_structured_error():
    result = CrmAdapter(base_url="http://127.0.0.1:9").execute({"operation": "list_customers"}, {})
    assert not result.success and "request failed" in result.error
