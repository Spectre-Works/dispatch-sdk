# SPDX-FileCopyrightText: 2026 SPECTRE WORKS LLC
# SPDX-License-Identifier: Apache-2.0
"""Run a local mock outlet and power meter for integration development."""

import argparse
from pathlib import Path

from dispatch_sdk.bridge import Bridge, Entity, Reading


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--token-file", type=Path, required=True)
    args = parser.parse_args()
    relay = False

    def turn(value):
        nonlocal relay
        relay = value

    entities = {
        "switch.demo_outlet": Entity(lambda: Reading("on" if relay else "off"), turn),
        "sensor.demo_watts": Entity(lambda: Reading(
            "300" if relay else "0", {"unit_of_measurement": "W", "device_class": "power"}
        )),
    }
    with Bridge((args.bind, args.port), args.token_file.read_text().strip(), entities) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
