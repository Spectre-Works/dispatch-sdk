# SPDX-FileCopyrightText: 2026 SPECTRE WORKS LLC
# SPDX-License-Identifier: Apache-2.0
import copy
import json
from pathlib import Path
import unittest

from dispatch_sdk.profile import STOCK, pack


class ProfileTest(unittest.TestCase):
    def test_stock(self):
        for family, fields in STOCK.items():
            path = Path(__file__).resolve().parents[1] / "profiles" / f"{family}.json"
            profile = json.loads(path.read_bytes())
            self.assertEqual(profile["fields"], fields)
            self.assertEqual(json.loads(pack(profile)), profile)

    def test_bad_register_and_version(self):
        profile = {"version": 1, "family": "victron-grid", "fields": copy.deepcopy(STOCK["victron-grid"])}
        profile["fields"]["firstRegister"] = 65531
        with self.assertRaises(ValueError):
            pack(profile)
        profile["fields"]["firstRegister"] = 908
        profile["version"] = True
        with self.assertRaises(ValueError):
            pack(profile)

    def test_identity_additions(self):
        rows = copy.deepcopy(STOCK["shelly-gen1"]["models"])
        profile = {"version": 1, "family": "shelly-gen1", "fields": {"models": rows}}
        rows.append(["MOCK-1", "shellydemo-", 2])
        pack(profile)
        rows[-1][1] = rows[0][1]
        with self.assertRaises(ValueError):
            pack(profile)
