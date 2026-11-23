# SPDX-FileCopyrightText: 2026 SPECTRE WORKS LLC
# SPDX-License-Identifier: Apache-2.0
"""Version 1 LAN bridge for the DISPATCH Home Assistant REST connection."""

from collections.abc import Callable
from dataclasses import dataclass, field
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import re
from typing import Any

VERSION = 1
MAX_REQUEST = 512
MAX_RESPONSE = 3072
ENTITY_ID = re.compile(r"(switch|sensor|number|select|button)\.[a-z0-9_]{1,73}")
TOKEN = re.compile(r"[A-Za-z0-9_.-]{32,255}")
SERVICES = {
    "switch/turn_on": ("switch", None, True),
    "switch/turn_off": ("switch", None, False),
    "number/set_value": ("number", "value", None),
    "select/select_option": ("select", "option", None),
    "button/press": ("button", None, None),
}


@dataclass(frozen=True)
class Reading:
    state: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Entity:
    # Return live device state, or Reading("unavailable").
    read: Callable[[], Reading]
    # Return once a request was sent. Observation is a separate read.
    write: Callable[[bool | float | str | None], None] | None = None


@dataclass(frozen=True)
class SolarReading:
    """A fresh generation observation from a bound inverter or gateway."""

    gateway_id: str
    age_seconds: int
    watts: int
    today_centi_kwh: int
    lifetime_deci_kwh: int
    inverter_count: int
    online_inverters: int

    def payload(self):
        if not isinstance(self.gateway_id, str) or not re.fullmatch(r"[0-9]{12}", self.gateway_id):
            raise ValueError("Solar gateway IDs contain exactly 12 digits.")
        readings = {
            "ageSeconds": (self.age_seconds, 30),
            "watts": (self.watts, 1_000_000),
            "todayCentiKWh": (self.today_centi_kwh, 2**32 - 1),
            "lifetimeDeciKWh": (self.lifetime_deci_kwh, 2**32 - 1),
            "inverterCount": (self.inverter_count, 2**16 - 1),
            "onlineInverters": (self.online_inverters, 2**16 - 1),
        }
        if any(type(value) is not int or not 0 <= value <= maximum for value, maximum in readings.values()):
            raise ValueError("Solar readings must be current and within range.")
        if self.online_inverters > self.inverter_count:
            raise ValueError("Online inverter count exceeds the installed count.")
        return {"version": VERSION, "id": self.gateway_id,
                **{key: value for key, (value, _) in readings.items()}}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result


def _number(value):
    return type(value) in (int, float) and -1e9 <= value <= 1e9 and math.isfinite(value)


def _command_valid(domain, value, reading):
    if reading.state in {"unavailable", "unknown"} and domain != "button":
        return False
    if domain == "switch":
        return type(value) is bool and reading.state in {"on", "off"}
    if domain == "button":
        return value is None and reading.state != "unavailable" and reading.attributes.get("device_class") == "restart"
    if domain == "select":
        options = reading.attributes.get("options", ())
        return isinstance(value, str) and value in options and reading.state in options
    low, high, step = (reading.attributes.get(key) for key in ("min", "max", "step"))
    if not all(_number(item) for item in (value, low, high, step)) or not low <= value <= high or step < 1e-9:
        return False
    steps = (value - low) / step
    return step <= high - low and abs(steps - round(steps)) <= 1e-6


class Bridge(HTTPServer):
    """Serve a fixed set of entities from a trusted LAN address.

    Callbacks run one at a time. Give every callback a short device I/O timeout.
    """

    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], token: str, entities: dict[str, Entity],
                 *, solar: Callable[[], SolarReading | None] | None = None):
        if not TOKEN.fullmatch(token):
            raise ValueError("Set a 32–255 character bearer token.")
        if len(entities) > 32 or (not entities and solar is None):
            raise ValueError("Register up to 32 entities and at least one data source.")
        if any(not ENTITY_ID.fullmatch(name) or len(name) > 80 for name in entities):
            raise ValueError("Invalid entity ID.")
        if any(name.startswith("sensor.") and entity.write for name, entity in entities.items()):
            raise ValueError("Sensor entities are read-only.")
        self.authorization = ("Bearer " + token).encode("ascii")
        self.entities = dict(entities)
        self.solar = solar
        super().__init__(address, _Handler)


class _Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(1)
        super().setup()

    def log_message(self, *_):
        # Entity IDs, credentials, and equipment responses stay local.
        pass

    def _reply(self, status, value):
        try:
            body = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError, RecursionError):
            body = b""
        if not body or len(body) > MAX_RESPONSE:
            status, body = 503, b'{"error":"Reading unavailable"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        values = self.headers.get_all("Authorization", ())
        if len(values) == 1 and compare_digest(values[0].encode("utf-8"), self.server.authorization):
            return True
        self._reply(401, {"error": "Authorization required"})
        return False

    def do_GET(self):
        if not self._authorized():
            return
        if self.path == "/api/dispatch/v1/capabilities":
            self._reply(200, {"version": VERSION, "transport": "ha-rest", "entities": list(self.server.entities),
                              "solar": self.server.solar is not None})
            return
        if self.path == "/api/dispatch/v1/solar":
            if self.server.solar is None:
                self._reply(404, {"error": "Solar source is not configured"})
                return
            try:
                reading = self.server.solar()
                if not isinstance(reading, SolarReading):
                    raise ValueError("Missing reading.")
                payload = reading.payload()
            except Exception:
                self._reply(503, {"error": "Solar reading unavailable"})
                return
            self._reply(200, payload)
            return
        prefix = "/api/states/"
        entity_id = self.path.removeprefix(prefix)
        entity = self.server.entities.get(entity_id) if self.path.startswith(prefix) else None
        if entity is None:
            self._reply(404, {"error": "Unknown entity"})
            return
        try:
            reading = entity.read()
            if not isinstance(reading, Reading) or not isinstance(reading.state, str):
                raise ValueError("Invalid reading.")
        except Exception:
            self._reply(503, {"error": "Reading unavailable"})
            return
        self._reply(200, {"entity_id": entity_id, "state": reading.state, "attributes": reading.attributes})

    def do_POST(self):
        if not self._authorized():
            return
        prefix = "/api/services/"
        service = SERVICES.get(self.path.removeprefix(prefix)) if self.path.startswith(prefix) else None
        if service is None:
            self._reply(404, {"error": "Unknown operation"})
            return
        try:
            lengths = self.headers.get_all("Content-Length", ())
            if len(lengths) != 1 or self.headers.get("Transfer-Encoding") or self.headers.get_content_type() != "application/json":
                raise ValueError("Invalid framing.")
            length = int(lengths[0])
            if not 0 < length <= MAX_REQUEST:
                raise ValueError("Invalid request size.")
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Incomplete request.")
            params = json.loads(body, object_pairs_hook=_unique_object)
            domain, argument, implied = service
            expected = {"entity_id", argument} if argument else {"entity_id"}
            if not isinstance(params, dict) or set(params) != expected or not isinstance(params["entity_id"], str):
                raise ValueError("Invalid request fields.")
            entity_id = params["entity_id"]
            entity = self.server.entities.get(entity_id)
            if not entity or not entity_id.startswith(domain + ".") or not entity.write:
                self._reply(404, {"error": "Unknown or read-only entity"})
                return
        except (ValueError, OSError, RecursionError):
            self._reply(400, {"error": "Invalid request"})
            return
        try:
            value = params[argument] if argument else implied
            if not _command_valid(domain, value, entity.read()):
                self._reply(409, {"error": "Operation rejected by current device state"})
                return
            entity.write(value)
        except Exception:
            self._reply(503, {"error": "Operation could not be confirmed"})
            return
        self._reply(200, [])
