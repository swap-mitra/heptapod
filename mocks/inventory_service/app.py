"""Inventory mock (SOAP 1.1 over HTTP): parts, stock levels, and warehouse locations.
OAuth2 client-credentials auth, with the service hosting its own token endpoint and issuing
short-lived tokens so clients must refresh. Headline quirk: field names follow this system's
camelCase conventions (`partNumber`, `quantityOnHand`), unlike the CRM and ticketing
systems (HLD: Mock Backends). All data is synthetic.

Operations (SOAP body element -> response element `<Op>Response`):
- ListParts: one `part` per part.
- GetPart(partNumber): the part's fields plus `totalOnHand`.
- GetStock(partNumber): `partNumber` plus one `location` per warehouse holding it.
- AdjustStock(partNumber, warehouseCode, delta): `partNumber` plus the updated `location`.
Errors are SOAP Faults with HTTP 500, per SOAP 1.1; a missing or expired token is HTTP 401."""

import os
import secrets
import time
import urllib.parse
import xml.etree.ElementTree as ET

from fastapi import FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
NS = "urn:heptapod:inventory"

SEED = {
    "BP-310": {"description": "Bilge pump, 12V, 3000 GPH", "unitPriceUsd": "189.00", "locations": [("RTM-01", "A-04-2", 3)]},
    "CB-075": {"description": "Conveyor belt, 750 mm, rubber", "unitPriceUsd": "412.50", "locations": [("RTM-01", "C-11-1", 12), ("SGP-03", "B-02-4", 8)]},
    "FL-120": {"description": "Hydraulic filter cartridge", "unitPriceUsd": "23.75", "locations": [("CHI-02", "D-01-1", 40), ("RTM-01", "D-07-3", 25)]},
    "HX-220": {"description": "Plate heat exchanger, 22 plates", "unitPriceUsd": "1340.00", "locations": [("SGP-03", "E-05-2", 6)]},
    "IV-550": {"description": "Inverter, 5.5 kW", "unitPriceUsd": "865.00", "locations": [("CHI-02", "F-03-1", 2), ("RTM-01", "F-09-2", 1)]},
    "SN-018": {"description": "Inductive proximity sensor, M18", "unitPriceUsd": "54.20", "locations": [("CHI-02", "G-02-3", 0), ("SGP-03", "G-06-1", 4)]},
}


class Fault(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _el(parent: ET.Element | None, tag: str, text: object = None) -> ET.Element:
    element = ET.Element(f"{{{NS}}}{tag}") if parent is None else ET.SubElement(parent, f"{{{NS}}}{tag}")
    if text is not None:
        element.text = str(text)
    return element


def _location(parent: ET.Element, location: dict) -> None:
    item = _el(parent, "location")
    for field in ("warehouseCode", "binLocation", "quantityOnHand"):
        _el(item, field, location[field])


def _part(parts: dict, args: dict) -> tuple[str, dict]:
    number = args.get("partNumber")
    if not number:
        raise Fault("Client", "partNumber is required")
    if number not in parts:
        raise Fault("Client", f"part {number} does not exist")
    return number, parts[number]


def list_parts(parts: dict, args: dict) -> ET.Element:
    response = _el(None, "ListPartsResponse")
    for number, part in sorted(parts.items()):
        item = _el(response, "part")
        _el(item, "partNumber", number)
        _el(item, "description", part["description"])
        _el(item, "unitPriceUsd", part["unitPriceUsd"])
    return response


def get_part(parts: dict, args: dict) -> ET.Element:
    number, part = _part(parts, args)
    response = _el(None, "GetPartResponse")
    _el(response, "partNumber", number)
    _el(response, "description", part["description"])
    _el(response, "unitPriceUsd", part["unitPriceUsd"])
    _el(response, "totalOnHand", sum(loc["quantityOnHand"] for loc in part["locations"]))
    return response


def get_stock(parts: dict, args: dict) -> ET.Element:
    number, part = _part(parts, args)
    response = _el(None, "GetStockResponse")
    _el(response, "partNumber", number)
    for location in part["locations"]:
        _location(response, location)
    return response


def adjust_stock(parts: dict, args: dict) -> ET.Element:
    number, part = _part(parts, args)
    try:
        delta = int(args.get("delta", ""))
    except ValueError:
        raise Fault("Client", "delta must be an integer")
    location = next((loc for loc in part["locations"] if loc["warehouseCode"] == args.get("warehouseCode")), None)
    if location is None:
        raise Fault("Client", f"part {number} is not stocked at warehouse {args.get('warehouseCode')}")
    if location["quantityOnHand"] + delta < 0:
        raise Fault("Client", f"adjustment would leave negative stock ({location['quantityOnHand']} on hand)")
    location["quantityOnHand"] += delta
    response = _el(None, "AdjustStockResponse")
    _el(response, "partNumber", number)
    _location(response, location)
    return response


OPERATIONS = {"ListParts": list_parts, "GetPart": get_part, "GetStock": get_stock, "AdjustStock": adjust_stock}


def _envelope(payload: ET.Element, status: int = 200) -> Response:
    envelope = ET.Element(f"{{{SOAP_NS}}}Envelope")
    ET.SubElement(envelope, f"{{{SOAP_NS}}}Body").append(payload)
    return Response(ET.tostring(envelope, xml_declaration=True, encoding="utf-8"), status, media_type="text/xml; charset=utf-8")


def _fault(fault: Fault) -> Response:
    payload = ET.Element(f"{{{SOAP_NS}}}Fault")
    # SOAP 1.1 faultcode/faultstring are unqualified elements.
    ET.SubElement(payload, "faultcode").text = f"soap:{fault.code}"
    ET.SubElement(payload, "faultstring").text = str(fault)
    return _envelope(payload, 500)


def _parse_call(body: bytes) -> tuple[str, dict]:
    try:
        envelope = ET.fromstring(body)
    except ET.ParseError as exc:
        raise Fault("Client", f"malformed XML: {exc}")
    soap_body = envelope.find(f"{{{SOAP_NS}}}Body")
    if envelope.tag != f"{{{SOAP_NS}}}Envelope" or soap_body is None or len(soap_body) == 0:
        raise Fault("Client", "expected a SOAP 1.1 Envelope with a Body")
    call = soap_body[0]
    operation = call.tag.removeprefix(f"{{{NS}}}")
    if operation not in OPERATIONS:
        raise Fault("Client", f"unknown operation {operation}")
    return operation, {child.tag.removeprefix(f"{{{NS}}}"): (child.text or "").strip() for child in call}


def create_app(client_id: str | None = None, client_secret: str | None = None, token_ttl: int | None = None) -> FastAPI:
    """Fresh app with its own copy of the seed data. Unset arguments come from
    INVENTORY_CLIENT_ID, INVENTORY_CLIENT_SECRET and INVENTORY_TOKEN_TTL (default 60s)."""
    client_id = client_id or os.environ["INVENTORY_CLIENT_ID"]
    client_secret = client_secret or os.environ["INVENTORY_CLIENT_SECRET"]
    token_ttl = token_ttl or int(os.environ.get("INVENTORY_TOKEN_TTL", "60"))
    parts = {
        number: {**part, "locations": [{"warehouseCode": w, "binLocation": b, "quantityOnHand": q} for w, b, q in part["locations"]]}
        for number, part in SEED.items()
    }
    tokens: dict[str, float] = {}  # access token -> monotonic expiry

    app = FastAPI(title="Inventory mock")
    app.state.tokens_issued = 0

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/oauth/token")
    async def token(request: Request):
        # Parsed by hand: FastAPI's Form() would need the python-multipart dependency.
        form = {k: v[0] for k, v in urllib.parse.parse_qs((await request.body()).decode()).items()}
        if form.get("grant_type") != "client_credentials":
            return JSONResponse({"error": "unsupported_grant_type"}, 400)
        id_ok = secrets.compare_digest(form.get("client_id", "").encode(), client_id.encode())
        secret_ok = secrets.compare_digest(form.get("client_secret", "").encode(), client_secret.encode())
        if not (id_ok and secret_ok):
            return JSONResponse({"error": "invalid_client"}, 401)
        access_token = secrets.token_urlsafe(24)
        tokens[access_token] = time.monotonic() + token_ttl
        app.state.tokens_issued += 1
        return {"access_token": access_token, "token_type": "Bearer", "expires_in": token_ttl}

    @app.post("/soap")
    async def soap(request: Request, authorization: str | None = Header(default=None)):
        token = (authorization or "").removeprefix("Bearer ")
        if tokens.get(token, 0.0) < time.monotonic():
            return Response(status_code=401, headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
        try:
            operation, args = _parse_call(await request.body())
            return _envelope(OPERATIONS[operation](parts, args))
        except Fault as fault:
            return _fault(fault)

    return app
