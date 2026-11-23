# SPDX-FileCopyrightText: 2026 SPECTRE WORKS LLC
# SPDX-License-Identifier: Apache-2.0
"""Bounded register reads for Modbus TCP and Solarman V5."""

from dataclasses import dataclass
from ipaddress import IPv4Address
from secrets import randbits
import socket
import struct
from time import monotonic, time


class ProtocolError(Exception):
    """Device replied with unavailable data or an unexpected frame."""


def integer(value, low, high):
    return type(value) is int and low <= value <= high


@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int
    unit: int

    def __post_init__(self):
        if not isinstance(self.host, str):
            raise ValueError("Enter a device IPv4 address.")
        IPv4Address(self.host)
        if not integer(self.port, 1, 65535) or not integer(self.unit, 1, 247):
            raise ValueError("Invalid device port or Modbus unit ID.")


class Connection:
    def __init__(self, endpoint, budget=0.40):
        self.endpoint = endpoint
        self.budget = budget

    def __enter__(self):
        self.expires = monotonic() + self.budget
        self.socket = socket.create_connection((self.endpoint.host, self.endpoint.port), self.remaining())
        return self

    def __exit__(self, *_):
        self.socket.close()

    def remaining(self):
        seconds = self.expires - monotonic()
        if seconds <= 0:
            raise TimeoutError("Register read deadline exceeded.")
        return seconds

    def send(self, message):
        self.socket.settimeout(self.remaining())
        self.socket.sendall(message)

    def receive(self, count):
        data = bytearray()
        while len(data) < count:
            self.socket.settimeout(self.remaining())
            part = self.socket.recv(count - len(data))
            if not part:
                raise ProtocolError("Truncated register reply.")
            data.extend(part)
        return bytes(data)


def read_pdu(function, address, count):
    if (function not in (3, 4) or not integer(count, 1, 125)
            or not integer(address, 0, 65536 - count)):
        raise ValueError("Invalid Modbus register read.")
    return struct.pack(">BHH", function, address, count)


def registers(pdu, function, count):
    if len(pdu) == 2 and pdu[0] == (function | 0x80):
        raise ProtocolError(f"Modbus exception {pdu[1]}.")
    if len(pdu) != 2 + 2 * count or pdu[:2] != bytes((function, 2 * count)):
        raise ProtocolError("Unexpected Modbus read reply.")
    return struct.unpack(f">{count}H", pdu[2:])


class ModbusTCP(Connection):
    def __enter__(self):
        self.transaction = randbits(16)
        return super().__enter__()

    def read(self, address, count):
        function = 3
        request = read_pdu(function, address, count)
        self.transaction = (self.transaction + 1) & 0xFFFF
        self.send(struct.pack(">HHHB", self.transaction, 0, len(request) + 1, self.endpoint.unit) + request)
        transaction, protocol, length, unit = struct.unpack(">HHHB", self.receive(7))
        if (transaction != self.transaction or protocol or unit != self.endpoint.unit
                or length not in (3, 3 + 2 * count)):
            raise ProtocolError("Unexpected Modbus TCP header.")
        return registers(self.receive(length - 1), function, count)


def rtu_crc(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc.to_bytes(2, "little")


class SolarmanV5(Connection):
    def __init__(self, endpoint, serial, function):
        super().__init__(endpoint)
        if not integer(serial, 1, 0xFFFFFFFF) or type(function) is not int or function not in (3, 4):
            raise ValueError("Set the logger serial and its documented read function (3 or 4).")
        self.serial = serial
        self.function = function

    def read(self, address, count):
        pdu = read_pdu(self.function, address, count)
        rtu = bytes((self.endpoint.unit,)) + pdu
        payload = b"\x02" + bytes(14) + rtu + rtu_crc(rtu)
        sequence = randbits(8)
        frame = struct.pack("<BHHBBI", 0xA5, len(payload), 0x4510, sequence, 0, self.serial) + payload
        self.send(frame + bytes((sum(frame[1:]) & 0xFF, 0x15)))

        reply = self.receive(11)
        marker, length, control, echoed, _, serial = struct.unpack("<BHHBBI", reply)
        if (marker != 0xA5 or control != 0x1510 or sequence != echoed or serial != self.serial
                or length not in (19, 19 + 2 * count)):
            raise ProtocolError("Unexpected Solarman V5 header.")
        payload = self.receive(length)
        checksum, end = self.receive(2)
        if end != 0x15 or checksum != (sum(reply[1:] + payload) & 0xFF) or payload[:2] != b"\x02\x01":
            raise ProtocolError("Invalid Solarman V5 reply.")
        working, _, clock_offset = struct.unpack_from("<III", payload, 2)
        age = time() - (working + clock_offset)
        if not -5 <= age <= 10:
            raise ProtocolError("Solarman observation timestamp is stale or invalid.")
        rtu = payload[14:]
        if rtu[0] != self.endpoint.unit or rtu[-2:] != rtu_crc(rtu[:-2]):
            raise ProtocolError("Invalid Solarman RTU reply.")
        return registers(rtu[1:-2], self.function, count)
