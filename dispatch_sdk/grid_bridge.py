# SPDX-FileCopyrightText: 2026 SPECTRE WORKS LLC
# SPDX-License-Identifier: Apache-2.0
"""Serve a configured grid meter as the DISPATCH LAN bridge's power sensor."""

import argparse
import hashlib
import json
from pathlib import Path
import tomllib

from .bridge import Bridge, Entity, Reading
from .grid_sources import SolarmanMeter, SunSpecMeter
from .modbus import Endpoint, ProtocolError

POLARITY = {"import-positive": 1, "export-positive": -1}


def load_source(path):
    with path.open("rb") as file:
        profile = tomllib.load(file)
    fields = {"version", "protocol", "direction", "device", "meter"}
    if set(profile) != fields or type(profile["version"]) is not int or profile["version"] != 1:
        raise ValueError("Expected a version 1 bridge profile.")
    if profile["direction"] not in POLARITY:
        raise ValueError("Set direction to import-positive or export-positive after checking your meter.")
    endpoint = Endpoint(**profile["device"])
    protocols = {"sunspec-tcp": SunSpecMeter, "solarman-v5": SolarmanMeter}
    if profile["protocol"] not in protocols:
        raise ValueError("Unsupported grid meter protocol.")
    source = protocols[profile["protocol"]](endpoint, **profile["meter"])
    # A changed device binding or direction requires commissioning a new entity.
    config = json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
    binding = hashlib.sha256(config).hexdigest()[:12]
    return source, POLARITY[profile["direction"]], f"sensor.dispatch_grid_{binding}"


def grid_entity(source, polarity):
    def read():
        try:
            watts = source.read() * polarity
        except (OSError, ProtocolError):
            return Reading("unavailable")
        return Reading(f"{watts:.6f}".rstrip("0").rstrip("."),
                       {"unit_of_measurement": "W", "device_class": "power"})

    return Entity(read)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8123, help="HTTP listener port")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--check", action="store_true", help="Read one sample without starting the bridge")
    args = parser.parse_args()
    try:
        source, polarity, entity = load_source(args.profile)
        if args.check:
            print(f"{entity}: {polarity * source.read():.3f} W (positive import, negative export)")
            return
        if args.token_file is None:
            parser.error("--token-file is required when serving the bridge")
        token = args.token_file.read_text().strip()
        with Bridge((args.bind, args.port), token, {entity: grid_entity(source, polarity)}) as server:
            print(f"Serving {entity}", flush=True)
            server.serve_forever()
    except (KeyError, TypeError, ValueError, OSError, ProtocolError) as error:
        parser.exit(1, f"{error}\n")
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
