# SPDX-FileCopyrightText: 2026 SPECTRE WORKS LLC
# SPDX-License-Identifier: Apache-2.0
"""Read signed whole-site grid power for the DISPATCH LAN bridge."""

from dataclasses import dataclass
import math
import struct

from .modbus import Endpoint, ModbusTCP, ProtocolError, SolarmanV5, integer

SCALED_METERS = range(201, 205)
FLOAT_METERS = range(211, 215)


def signed16(word):
    return word - 65536 if word & 0x8000 else word


def string_registers(words):
    value = struct.pack(f">{len(words)}H", *words).split(b"\0", 1)[0]
    try:
        return value.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise ProtocolError("Invalid SunSpec device identity.") from error


@dataclass(frozen=True)
class SunSpecMeter:
    endpoint: Endpoint
    base: int
    serial: str
    model: int
    meter_index: int
    manufacturer: str = ""

    def __post_init__(self):
        if (not integer(self.base, 0, 65468) or not isinstance(self.serial, str)
                or not self.serial.strip() or len(self.serial) > 32
                or type(self.model) is not int or (self.model not in SCALED_METERS and self.model not in FLOAT_METERS)
                or not integer(self.meter_index, 1, 16) or not isinstance(self.manufacturer, str)):
            raise ValueError("Specify a SunSpec base, device serial, meter model and meter index.")

    def read(self):
        with ModbusTCP(self.endpoint) as connection:
            if connection.read(self.base, 2) != (0x5375, 0x6E53):
                raise ProtocolError("SunSpec signature missing.")
            common = self.base + 2
            model_id, length = connection.read(common, 2)
            if model_id != 1 or length not in (65, 66):
                raise ProtocolError("Unsupported SunSpec common block.")
            identity = connection.read(common + 2, 64)
            if self.serial != string_registers(identity[48:64]):
                raise ProtocolError("SunSpec serial number changed.")
            if self.manufacturer and self.manufacturer != string_registers(identity[:16]):
                raise ProtocolError("SunSpec manufacturer mismatch.")
            model = self._find_meter(connection, common + length + 2)
            if self.model in SCALED_METERS:
                fields = connection.read(model + 18, 5)
                raw, exponent = signed16(fields[0]), signed16(fields[4])
                if raw == -32768 or not -6 <= exponent <= 6:
                    raise ProtocolError("SunSpec power or scale is unavailable.")
                watts = raw * 10.0 ** exponent
            else:
                fields = connection.read(model + 28, 2)
                watts = struct.unpack(">f", struct.pack(">HH", *fields))[0]
            if not math.isfinite(watts) or abs(watts) > 1_000_000:
                raise ProtocolError("SunSpec power is unavailable or out of range.")
            return watts

    def _find_meter(self, connection, address):
        remaining = self.meter_index
        for _ in range(32):
            if address > 65534:
                break
            model, length = connection.read(address, 2)
            if model in (0, 0xFFFF) or not length or address + 2 + length > 65536:
                break
            if model == self.model:
                remaining -= 1
                if remaining == 0:
                    expected = 105 if model in SCALED_METERS else 124
                    if length != expected:
                        raise ProtocolError("Unexpected SunSpec meter model length.")
                    return address
            address += 2 + length
        raise ProtocolError("Selected SunSpec meter model not found.")


@dataclass(frozen=True)
class SolarmanMeter:
    endpoint: Endpoint
    logger_serial: int
    function: int
    register: int
    exponent: int

    def __post_init__(self):
        if (not integer(self.logger_serial, 1, 0xFFFFFFFF)
                or type(self.function) is not int or self.function not in (3, 4)
                or not integer(self.register, 0, 65535) or not integer(self.exponent, -6, 6)):
            raise ValueError("Set the logger serial and a documented signed 16-bit power register and scale.")

    def read(self):
        with SolarmanV5(self.endpoint, self.logger_serial, self.function) as connection:
            raw = signed16(connection.read(self.register, 1)[0])
        watts = raw * 10.0 ** self.exponent
        if raw == -32768 or abs(watts) > 1_000_000:
            raise ProtocolError("Solarman power is unavailable or out of range.")
        return watts
