# SPDX-FileCopyrightText: 2026 SPECTRE WORKS LLC
# SPDX-License-Identifier: Apache-2.0
"""Validate and pack a DISPATCH version 1 profile."""

import argparse
import json
import re
from pathlib import Path

VERSION = 1
MAX_BYTES = 1536
FIELD = r"[A-Za-z0-9_ -]{1,23}"
ENTITY = r"sensor\.[a-z0-9_]{1,31}"
OUTLET = r"switch\.[a-z0-9_]{1,31}"
ACTION = r"(?:number|select|button)\.[a-z0-9_]{1,31}"
PREFIX = r"shelly[a-z0-9-]{1,11}-"
RPC_PREFIX = r"shelly[a-z0-9-]{1,16}-"
MODEL = r"[A-Z0-9-]{1,11}"

STOCK_MODELS = (
    ("SHPLG-1", "shellyplug-", 1),
    ("SHPLG2-1", "shellyplug-", 1),
    ("SHPLG-S", "shellyplug-s-", 1),
    ("SHPLG-U1", "shellyplug-u1-", 1),
    ("SHSW-PM", "shelly1pm-", 1),
    ("SHSW-25", "shellyswitch25-", 2),
    ("SHEM-3", "shellyem3-", 1),
)
STOCK = {
    "shelly-gen1": {"models": [list(row) for row in STOCK_MODELS]},
    "shelly-rpc": {
        "relayWatts": "apower", "relayEnergyObject": "aenergy",
        "relayWattHours": "total", "singleGridWatts": "act_power",
        "threeGridWatts": "total_act_power", "models": [],
    },
    "tasmota": {"watts": "Power", "kilowattHours": "Total", "statusRelay": "auto"},
    "victron-grid": {"firstRegister": 908, "wordOrder": "high-first"},
    "fronius": {"gridWatts": "P_Grid", "solarWatts": "P_PV"},
    "cgminer": {
        "rate5s": "MHS 5s", "rate20s": "MHS 20s", "rateAverage": "MHS av",
        "accepted": "Accepted", "elapsed": "Elapsed",
    },
    "home-assistant": {
        "battery": "", "temperature": "", "actuator": "", "outlet": "", "grid": "",
        "outletWatts": "", "outletEnergy": "",
    },
}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate key: {key}")
        result[key] = value
    return result


def _check_models(rows):
    if not isinstance(rows, list) or not 7 <= len(rows) <= 11:
        raise ValueError("Supply the seven stock Shelly models and up to four additions.")
    models = {}
    prefixes = {row[1] for row in STOCK_MODELS}
    for row in rows:
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError("Each Shelly model has a model, prefix and relay count.")
        model, prefix, relays = row
        if (not isinstance(model, str) or not re.fullmatch(MODEL, model)
                or not isinstance(prefix, str) or not re.fullmatch(PREFIX, prefix)
                or type(relays) is not int or not 1 <= relays <= 4 or model in models):
            raise ValueError("Invalid or duplicate Shelly model.")
        models[model] = (model, prefix, relays)
        if models[model] in STOCK_MODELS:
            continue
        if prefix in prefixes or prefix in {"shellyproem-", "shellypro3em-"}:
            raise ValueError("Additional models need unique, unused prefixes.")
        prefixes.add(prefix)
    if any(models.get(row[0]) != row for row in STOCK_MODELS):
        raise ValueError("Retain the stock model identities and relay counts.")


def _check_rpc_models(rows):
    if not isinstance(rows, list) or len(rows) > 4:
        raise ValueError("Use up to four additional Shelly RPC model prefixes.")
    reserved = {row[1] for row in STOCK_MODELS} | {"shellyproem-", "shellypro3em-"}
    for row in rows:
        if not isinstance(row, list) or len(row) != 4:
            raise ValueError("Each RPC model has a prefix, first switch, last switch and meter component.")
        prefix, first, last, meter = row
        if (not isinstance(prefix, str) or not re.fullmatch(RPC_PREFIX, prefix) or prefix in reserved
                or type(first) is not int or type(last) is not int or not 0 <= first <= last <= 199
                or meter not in ("none", "em", "em1")):
            raise ValueError("Invalid Shelly RPC model mapping.")
        reserved.add(prefix)


def validate(profile):
    if not isinstance(profile, dict) or set(profile) != {"version", "family", "fields"}:
        raise ValueError("A profile requires version, family and fields.")
    if type(profile["version"]) is not int or profile["version"] != VERSION:
        raise ValueError("Unsupported profile version.")
    family, fields = profile["family"], profile["fields"]
    if not isinstance(family, str) or family not in STOCK:
        raise ValueError("Unsupported profile family.")
    if not isinstance(fields, dict) or set(fields) != set(STOCK[family]):
        raise ValueError(f"Expected fields: {', '.join(STOCK[family])}")
    if family == "shelly-gen1":
        _check_models(fields["models"])
    elif family == "victron-grid":
        register = fields["firstRegister"]
        if type(register) is not int or not 0 <= register <= 65530:
            raise ValueError("firstRegister must leave room for six registers.")
        if fields["wordOrder"] not in ("high-first", "low-first"):
            raise ValueError("Invalid wordOrder.")
    elif family == "home-assistant":
        for key, value in fields.items():
            pattern = {"actuator": ACTION, "outlet": OUTLET}.get(key, ENTITY)
            if not isinstance(value, str) or (value and not re.fullmatch(pattern, value)):
                raise ValueError(f"Invalid entity ID for {key}.")
    else:
        aliases = fields.copy()
        if family == "shelly-rpc":
            _check_rpc_models(aliases.pop("models"))
        elif family == "tasmota" and aliases.pop("statusRelay") not in ("auto", "indexed", "single"):
            raise ValueError("Invalid Tasmota statusRelay.")
        for key, value in aliases.items():
            if not isinstance(value, str) or not re.fullmatch(FIELD, value):
                raise ValueError(f"Invalid field name for {key}.")
        if len(set(aliases.values())) != len(aliases) and family != "shelly-rpc":
            raise ValueError("Measurements must use distinct field names.")


def pack(profile):
    validate(profile)
    artifact = json.dumps(profile, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    if len(artifact) > MAX_BYTES:
        raise ValueError(f"Profile exceeds the controller's {MAX_BYTES}-byte limit.")
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="Write a ready-to-upload artifact.")
    args = parser.parse_args()
    try:
        profile = json.loads(args.source.read_text(encoding="utf-8"), object_pairs_hook=_object)
        artifact = pack(profile)
        if args.output:
            args.output.write_bytes(artifact)
    except (ValueError, OSError, RecursionError) as error:
        parser.exit(1, f"{error}\n")
    print(f"{profile['family']} v{VERSION}: {len(artifact)} bytes")


if __name__ == "__main__":
    main()
