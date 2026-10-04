from contextlib import ExitStack

import pytest
from fastapi import FastAPI, Response

from adapters.inventory import InventoryAdapter
from core import auth
from mocks.inventory_service.app import create_app
from tests.conftest import serve

CLIENT_ID, SECRET = "agent", "test-secret"


@pytest.fixture
def inventory(monkeypatch):
    """Start the mock with a given token lifetime; yield (adapter, app)."""
    monkeypatch.setenv("INVENTORY_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("INVENTORY_CLIENT_SECRET", SECRET)
    auth._tokens.clear()  # ports get reused across tests; never reuse a dead server's token
    with ExitStack() as stack:

        def start(token_ttl=3600):
            app = create_app(CLIENT_ID, SECRET, token_ttl)
            return InventoryAdapter(base_url=stack.enter_context(serve(app))), app

        yield start


def call(adapter, **input):
    return adapter.execute(input, auth.resolve(adapter.auth_config))


def test_list_parts_includes_every_ticket_referenced_part(inventory):
    adapter, _ = inventory()
    result = call(adapter, operation="list_parts")
    assert result.success
    assert {"BP-310", "CB-075", "IV-550", "SN-018"} <= {p["partNumber"] for p in result.data["parts"]}


def test_get_part_totals_stock(inventory):
    adapter, _ = inventory()
    result = call(adapter, operation="get_part", partNumber="CB-075")
    assert result.success
    assert result.data["description"] and result.data["totalOnHand"] == "20"


def test_get_stock_lists_each_location(inventory):
    adapter, _ = inventory()
    result = call(adapter, operation="get_stock", partNumber="CB-075")
    assert result.data["partNumber"] == "CB-075"
    assert [(loc["warehouseCode"], loc["quantityOnHand"]) for loc in result.data["locations"]] == [("RTM-01", "12"), ("SGP-03", "8")]


def test_adjust_stock_updates_quantity(inventory):
    adapter, _ = inventory()
    result = call(adapter, operation="adjust_stock", partNumber="CB-075", warehouseCode="RTM-01", delta=-2)
    assert result.success and result.data["locations"] == [{"warehouseCode": "RTM-01", "binLocation": "C-11-1", "quantityOnHand": "10"}]
    assert call(adapter, operation="get_part", partNumber="CB-075").data["totalOnHand"] == "18"


@pytest.mark.parametrize(
    "input, match",
    [
        ({"operation": "get_part", "partNumber": "XX-000"}, "XX-000"),
        ({"operation": "adjust_stock", "partNumber": "SN-018", "warehouseCode": "CHI-02", "delta": -1}, "negative"),
    ],
)
def test_soap_fault_is_structured_error(inventory, input, match):
    adapter, _ = inventory()
    result = call(adapter, **input)
    assert not result.success and "SOAP fault" in result.error and match in result.error


def test_token_is_cached_across_calls(inventory):
    adapter, app = inventory(token_ttl=3600)
    call(adapter, operation="list_parts")
    call(adapter, operation="list_parts")
    assert app.state.tokens_issued == 1


def test_token_is_refreshed_when_it_expires(inventory):
    # A 1s lifetime is inside the refresh margin, so every resolve fetches a new token.
    adapter, app = inventory(token_ttl=1)
    assert call(adapter, operation="list_parts").success
    assert call(adapter, operation="list_parts").success
    assert app.state.tokens_issued == 2


def test_bad_client_secret_fails_token_request(inventory, monkeypatch):
    adapter, _ = inventory()
    monkeypatch.setenv("INVENTORY_CLIENT_SECRET", "wrong")
    with pytest.raises(auth.AuthError, match="401"):
        auth.resolve(adapter.auth_config)


def test_invalid_token_is_structured_error(inventory):
    adapter, _ = inventory()
    result = adapter.execute({"operation": "list_parts"}, {"Authorization": "Bearer forged"})
    assert not result.success and "401" in result.error


def test_malformed_xml_is_structured_error():
    app = FastAPI()
    app.post("/soap")(lambda: Response("<soap:Envelope><unclosed", media_type="text/xml"))
    with serve(app) as url:
        result = InventoryAdapter(base_url=url).execute({"operation": "list_parts"}, {})
    assert not result.success and "malformed" in result.error


@pytest.mark.parametrize(
    "input, match",
    [
        ({"operation": "scrap_part"}, "operation"),
        ({"operation": "get_stock"}, "partNumber"),
        ({"operation": "adjust_stock", "partNumber": "CB-075", "warehouseCode": "RTM-01"}, "delta"),
    ],
)
def test_invalid_input_is_structured_error(inventory, input, match):
    adapter, _ = inventory()
    result = adapter.execute(input, {})
    assert not result.success and match in result.error
