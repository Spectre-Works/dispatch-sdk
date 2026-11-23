# SPDX-FileCopyrightText: 2026 SPECTRE WORKS LLC
# SPDX-License-Identifier: Apache-2.0
from contextlib import contextmanager
import json
from pathlib import Path
import socketserver
import struct
import tempfile
from threading import Thread
import time
import unittest
from urllib.request import Request, urlopen

from dispatch_sdk.bridge import Bridge
from dispatch_sdk.grid_bridge import grid_entity, load_source
from dispatch_sdk.grid_sources import SolarmanMeter, SunSpecMeter
from dispatch_sdk.modbus import Endpoint, rtu_crc


@contextmanager
def running(server):
    with server:
        worker = Thread(target=lambda: server.serve_forever(poll_interval=0.01))
        worker.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            worker.join()


def fixture_sunspec(model, value, exponent=0, *, solaredge=False):
    words = {40000: 0x5375, 40001: 0x6E53, 40002: 1, 40003: 65 if solaredge else 66}
    for pos, text in ((40004, b"SolarEdge"), (40052, b"FIXTURE123")):
        strings = struct.unpack(">16H", text.ljust(32, b"\0"))
        words.update({pos + index: item for index, item in enumerate(strings)})
    if solaredge:
        words.update({40069: 103, 40070: 50, 40121: 5, 40122: 65})
        start = 40188
    else:
        words.update({40070: 103, 40071: 50})
        start = 40122
    words[start] = model
    if 201 <= model <= 204:
        words[start + 1], words[start + 18], words[start + 22] = 105, value & 0xFFFF, exponent & 0xFFFF
    else:
        words[start + 1] = 124
        words[start + 28], words[start + 29] = struct.unpack(">HH", struct.pack(">f", value))
    return words


def modbus_simulator(words, change_transaction=False):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.request.settimeout(1)
            while request := self.rfile.read(12):
                transaction, protocol, length, unit, function, address, count = struct.unpack(">HHHBBHH", request)
                assert protocol == 0 and length == 6 and unit == 1 and function == 3
                values = [words.get(index, 0) for index in range(address, address + count)]
                data = struct.pack(f">BB{count}H", function, 2 * count, *values)
                reply = struct.pack(">HHHB", transaction ^ change_transaction, 0, len(data) + 1, unit)
                self.wfile.write(reply + data)
                if change_transaction:
                    break
    return socketserver.TCPServer(("127.0.0.1", 0), Handler)


def solarman_simulator(*, stale=False, wrong_serial=False, wrong_crc=False, wrong_sequence=False):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.request.settimeout(1)
            header = self.rfile.read(11)
            marker, length, command, sequence, _, serial = struct.unpack("<BHHBBI", header)
            assert marker == 0xA5 and command == 0x4510 and length == 23 and serial == 123456
            request = self.rfile.read(length + 2)
            assert request[:15] == b"\x02" + bytes(14)
            assert request[-2:] == bytes((sum(header[1:] + request[:-2]) & 0xFF, 0x15))
            assert struct.unpack(">BBHH", request[15:21]) == (1, 3, 88, 1)
            assert request[21:23] == rtu_crc(request[15:21])
            rtu = struct.pack(">BBBh", 1, 3, 2, -2145)
            crc = rtu_crc(rtu)
            if wrong_crc:
                crc = bytes((crc[0] ^ 1, crc[1]))
            acquired = int(time.time()) - (30 if stale else 1)
            payload = b"\x02\x01" + struct.pack("<III", 200, 100, acquired - 200) + rtu + crc
            response = struct.pack("<BHHBBI", 0xA5, len(payload), 0x1510, sequence ^ wrong_sequence, 1, serial + wrong_serial) + payload
            self.wfile.write(response + bytes((sum(response[1:]) & 0xFF, 0x15)))
    return socketserver.TCPServer(("127.0.0.1", 0), Handler)


class GridBridgeTest(unittest.TestCase):
    def test_solaredge_profile_to_http(self):
        template = Path(__file__).resolve().parents[1] / "bridge_profiles" / "solaredge-meter.toml"
        words = fixture_sunspec(203, -245, 1, solaredge=True)
        token = "fixture-grid-bridge-token-00000000"
        with running(modbus_simulator(words)) as meter_port, tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / "fixture.toml"
            profile.write_text(template.read_text().replace('direction = ""', 'direction = "export-positive"')
                               .replace('host = ""', 'host = "127.0.0.1"')
                               .replace('serial = ""', 'serial = "FIXTURE123"')
                               .replace("port = 1502", f"port = {meter_port}"))
            source, polarity, entity = load_source(profile)
            self.assertRegex(entity, r"^sensor\.dispatch_grid_[0-9a-f]{12}$")
            profile.write_text(profile.read_text().replace("export-positive", "import-positive"))
            self.assertNotEqual(load_source(profile)[2], entity)
            with running(Bridge(("127.0.0.1", 0), token, {entity: grid_entity(source, polarity)})) as http_port:
                request = Request(f"http://127.0.0.1:{http_port}/api/states/{entity}",
                                  headers={"Authorization": f"Bearer {token}"})
                with urlopen(request, timeout=2) as response:
                    reading = json.load(response)
                self.assertEqual(reading, {"entity_id": entity, "state": "2450",
                                           "attributes": {"unit_of_measurement": "W", "device_class": "power"}})

    def test_sunspec_float_and_invalid_readings(self):
        for model, value, serial, transaction_changed, expected in (
            (213, -125.5, "FIXTURE123", False, "-125.5"),
            (213, float("nan"), "FIXTURE123", False, "unavailable"),
            (203, -32768, "FIXTURE123", False, "unavailable"),
            (203, 110, "WRONG", False, "unavailable"),
            (203, 110, "FIXTURE123", True, "unavailable"),
        ):
            with self.subTest(model=model, serial=serial, expected=expected):
                with running(modbus_simulator(fixture_sunspec(model, value), transaction_changed)) as port:
                    source = SunSpecMeter(Endpoint("127.0.0.1", port, 1), 40000, serial, model, 1)
                    self.assertEqual(grid_entity(source, 1).read().state, expected)

    def test_solarman_bounds_and_integrity(self):
        self.assertEqual(rtu_crc(bytes.fromhex("010300000001")), bytes.fromhex("840a"))
        for options in ({}, {"stale": True}, {"wrong_serial": True}, {"wrong_crc": True}, {"wrong_sequence": True}):
            with self.subTest(options=options):
                with running(solarman_simulator(**options)) as port:
                    source = SolarmanMeter(Endpoint("127.0.0.1", port, 1), 123456, 3, 88, -1)
                    self.assertEqual(grid_entity(source, 1).read().state,
                                     "unavailable" if options else "-214.5")
