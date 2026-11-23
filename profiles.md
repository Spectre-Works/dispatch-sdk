<!-- SPDX-FileCopyrightText: 2026 SPECTRE WORKS LLC -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Integration profiles v1

An upload is one JSON object with `version: 1`, `family`, and `fields`. It can
occupy up to 1,536 bytes. Each firmware version advertises the accepted schema
version and its supported families in the owner-authenticated
`GET /api/profiles` response. The [schema](profile.schema.json) describes the
shape. The [validator](dispatch_sdk/profile.py) also checks cross-field rules.

Each controller can save one profile per family. A profile revision becomes
active at restart. The controller's stock defaults correspond to the files in
[profiles](profiles). Use **Restore stock** and restart to remove a saved
profile. Keep the file you uploaded if you want to reinstall that revision.

| Family | Editable mapping |
| --- | --- |
| `shelly-gen1` | Seven stock model identities and up to four additive entries. Each new entry supplies the reported model, unique device ID prefix, and relay count from 1 through 4. The native Gen1 status, metering units, and relay protocol apply. |
| `shelly-rpc` | Switch watts and watt-hours fields, and the signed watts fields for EM1 and EM components. Identity, component validity, and relay command handling belong to the controller. |
| `tasmota` | Scalar watts and cumulative kilowatt-hours keys inside `StatusSNS.ENERGY` on single-output meters. The same mapping serves HTTP and MQTT. |
| `victron-grid` | First system-unit grid register and 32-bit word order. Each commissioned phase occupies two consecutive words and supplies signed whole watts. ESS target reads and writes use the stock register map. |
| `fronius` | Signed grid watts and PV watts fields inside the Power Flow site object. Grid-point and backup checks still apply. |
| `cgminer` | Summary field names for MH/s over 5 seconds, 20 seconds, and lifetime average, plus the accepted-share count and elapsed seconds. |
| `home-assistant` | Optional battery sensor, temperature sensor, and number, select, or restart button entity IDs. Select **Fill from SDK template** in the Home Assistant setup to review them before saving. |

Field names are literal, case-sensitive keys. Supply the documented units and
the same physical meaning as the corresponding stock key. Use distinct
measurements. A blank Home Assistant field leaves the matching form input alone.
Configure endpoints, credentials, and equipment bindings through the controller
setup. Keep profiles with your backups if you move an installation.

The existing ECU-R binary protocol, Goldshell model-qualified controls, and
XBT and CONVOY DATUM readiness checks ship in the controller. Device protocol
changes that need code can use the [LAN bridge](bridge.md) for supported
measurement and control roles.
