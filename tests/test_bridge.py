# SPDX-FileCopyrightText: 2026 SPECTRE WORKS LLC
# SPDX-License-Identifier: Apache-2.0
import json
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dispatch_sdk.bridge import Bridge, Entity, Reading, SolarReading


class BridgeTest(unittest.TestCase):
    def test_solar_data_bounds(self):
        self.assertEqual(SolarReading("123456789012", 15, 500, 120, 5000, 2, 2).payload()["watts"], 500)
        for reading in (
            SolarReading("123456789012", 31, 500, 120, 5000, 2, 2),
            SolarReading("123456789012", 15, 500, 120, 5000, 1, 2),
            SolarReading("12345678901x", 15, 500, 120, 5000, 2, 2),
        ):
            with self.assertRaises(ValueError):
                reading.payload()

    def test_wire_contract_and_command_reconciliation(self):
        writes = []
        token = "local-test-token-0000000000000000"
        entities = {
            "switch.demo": Entity(lambda: Reading("on" if writes else "off"), writes.append),
            "number.demo": Entity(lambda: Reading("10", {"min": 5, "max": 15, "step": 5}), writes.append),
        }
        with Bridge(("127.0.0.1", 0), token, entities) as server:
            runner = Thread(target=server.serve_forever)
            runner.start()
            try:
                port = server.server_address[1]

                def request(path, value=None, auth=True):
                    headers = {"Authorization": f"Bearer {token}"} if auth else {}
                    body = None
                    if value is not None:
                        headers["Content-Type"] = "application/json"
                        body = json.dumps(value).encode()
                    with urlopen(Request(f"http://127.0.0.1:{port}{path}", body, headers), timeout=2) as response:
                        return json.load(response)

                with self.assertRaises(HTTPError) as err:
                    request("/api/states/switch.demo", auth=False)
                self.assertEqual(err.exception.code, 401)
                err.exception.close()
                self.assertEqual(request("/api/dispatch/v1/capabilities")["version"], 1)
                self.assertEqual(request("/api/states/switch.demo")["state"], "off")
                request("/api/services/switch/turn_on", {"entity_id": "switch.demo"})
                self.assertEqual(request("/api/states/switch.demo")["state"], "on")
                with self.assertRaises(HTTPError) as err:
                    request("/api/services/number/set_value", {"entity_id": "number.demo", "value": 13})
                self.assertEqual(err.exception.code, 409)
                err.exception.close()
                request("/api/services/number/set_value", {"entity_id": "number.demo", "value": 15})
                self.assertEqual(writes, [True, 15])
            finally:
                server.shutdown()
                runner.join()
