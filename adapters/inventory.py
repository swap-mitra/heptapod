"""Inventory adapter (SOAP 1.1 + XML).

Auth: OAuth2 client credentials against the service's own `/oauth/token`. Secrets: env vars
`INVENTORY_CLIENT_ID` and `INVENTORY_CLIENT_SECRET`. The Auth Layer caches and refreshes
the bearer token.

Operations, chosen with the `operation` argument:
- `list_parts`: every part with `partNumber`, `description`, `unitPriceUsd`.
- `get_part(partNumber)`: one part plus `totalOnHand` across warehouses.
- `get_stock(partNumber)`: `partNumber` plus `locations`, each with `warehouseCode`,
  `binLocation`, `quantityOnHand`.
- `adjust_stock(partNumber, warehouseCode, delta)`: adds `delta` (negative to remove) at one
  warehouse; returns `partNumber` and that warehouse as the only `locations` entry. The
  service refuses to go below zero.

Field names are the inventory system's own camelCase (`partNumber` is what ticketing calls
`part_ref`). SOAP values are untyped, so numbers arrive as strings. SOAP faults, HTTP errors
and malformed XML come back as `AdapterResult(success=False)`, never raised.
"""

import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from core.adapter import AdapterResult
from core.auth import Credentials

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
NS = "urn:heptapod:inventory"
# operation -> (SOAP operation, required arguments, in the order the service expects them)
OPERATIONS = {
    "list_parts": ("ListParts", ()),
    "get_part": ("GetPart", ("partNumber",)),
    "get_stock": ("GetStock", ("partNumber",)),
    "adjust_stock": ("AdjustStock", ("partNumber", "warehouseCode", "delta")),
}
# Elements that repeat; always returned as a list under the plural key, even with one item.
LIST_TAGS = {"part": "parts", "location": "locations"}
TIMEOUT_S = 10


class InventoryAdapter:
    name = "inventory"
    description = (
        "Inventory system (SOAP): parts, their stock levels, and the warehouse locations "
        "holding them. Part numbers here are what ticketing calls part_ref. Look up parts and "
        "stock, or adjust stock at a warehouse."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": list(OPERATIONS)},
            "partNumber": {"type": "string", "description": "e.g. CB-075. Required for every operation except list_parts."},
            "warehouseCode": {"type": "string", "description": "e.g. RTM-01. Required for adjust_stock."},
            "delta": {"type": "integer", "description": "Units to add (negative to remove). Required for adjust_stock."},
        },
        "required": ["operation"],
        "additionalProperties": False,
    }

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.auth_config = {
            "type": "oauth2_cc",
            "token_url": self.base_url + "/oauth/token",
            "client_id_ref": "INVENTORY_CLIENT_ID",
            "client_secret_ref": "INVENTORY_CLIENT_SECRET",
        }

    def execute(self, input: dict[str, Any], credentials: Credentials) -> AdapterResult:
        operation = input.get("operation")
        if operation not in OPERATIONS:
            return AdapterResult(False, error=f"unknown operation {operation!r}; expected one of {list(OPERATIONS)}")
        soap_operation, required = OPERATIONS[operation]
        missing = [arg for arg in required if input.get(arg) in (None, "")]
        if missing:
            return AdapterResult(False, error=f"{operation} requires {missing}")

        try:
            response = self._call(soap_operation, {arg: input[arg] for arg in required}, credentials)
        except urllib.error.HTTPError as exc:
            return AdapterResult(False, error=f"inventory returned HTTP {exc.code}: {_fault(exc)}")
        except ET.ParseError as exc:
            return AdapterResult(False, error=f"inventory sent malformed XML: {exc}")
        except (OSError, ValueError) as exc:  # connection failures, timeouts, unexpected envelope
            return AdapterResult(False, error=f"inventory request failed: {exc}")
        return AdapterResult(True, data=_to_dict(response))

    def _call(self, operation: str, args: dict[str, Any], credentials: Credentials) -> ET.Element:
        envelope = ET.Element(f"{{{SOAP_NS}}}Envelope")
        call = ET.SubElement(ET.SubElement(envelope, f"{{{SOAP_NS}}}Body"), f"{{{NS}}}{operation}")
        for name, value in args.items():
            ET.SubElement(call, f"{{{NS}}}{name}").text = str(value)
        request = urllib.request.Request(
            self.base_url + "/soap",
            data=ET.tostring(envelope, xml_declaration=True, encoding="utf-8"),
            method="POST",
            headers={**credentials, "Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{NS}#{operation}"'},
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as http_response:
            root = ET.fromstring(http_response.read())
        response = root.find(f"{{{SOAP_NS}}}Body/{{{NS}}}{operation}Response")
        if response is None:
            raise ValueError(f"no {operation}Response in the SOAP Body")
        return response


def _to_dict(element: ET.Element) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for child in element:
        key = child.tag.rpartition("}")[2]
        value = _to_dict(child) if len(child) else (child.text or "")
        if key in LIST_TAGS:
            result.setdefault(LIST_TAGS[key], []).append(value)
        else:
            result[key] = value
    return result


def _fault(exc: urllib.error.HTTPError) -> str:
    """The SOAP Fault's code and message when the body carries one, else the HTTP reason."""
    try:
        fault = ET.fromstring(exc.read()).find(f"{{{SOAP_NS}}}Body/{{{SOAP_NS}}}Fault")
    except (ET.ParseError, OSError):
        fault = None
    if fault is None:
        return str(exc.reason)
    return f"SOAP fault {fault.findtext('faultcode')}: {fault.findtext('faultstring')}"
