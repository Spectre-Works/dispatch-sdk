<!-- SPDX-FileCopyrightText: 2026 SPECTRE WORKS LLC -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# LAN bridge v1

A bridge runs independently on a trusted LAN server. Enter its IPv4 address,
HTTP port and bearer token in the controller's Home Assistant connection,
then pair selected entities. Use a different token for each installation and
restrict the listener to your trusted network. The mock in
[examples](examples/demo_bridge.py) is suitable for testing a binding.

The bridge serves this fixed Home Assistant REST subset under bearer
authentication.

| Request | Response or action |
| --- | --- |
| `GET /api/dispatch/v1/capabilities` | Version 1, transport `ha-rest`, allowlisted entity IDs, and whether solar data is available. |
| `GET /api/dispatch/v1/solar` | Optional fresh generation observation. See the solar contract below. |
| `GET /api/states/{entity_id}` | `entity_id`, a string `state`, and `attributes`. |
| `POST /api/services/switch/turn_on` or `turn_off` | Call the configured switch writer with a Boolean. |
| `POST /api/services/number/set_value` | Check range and step and call its writer with `value`. |
| `POST /api/services/select/select_option` | Check the available options and call its writer with `option`. |
| `POST /api/services/button/press` | Call a restart-class button's writer once. |

All action requests specify `entity_id`. A successful action acknowledges
the request. The controller reads state separately to observe it. Return
`Reading("unavailable")` when the device is missing, stale, or unverified.
A restart button returns the most recent observed press marker as a string,
or `unknown` until the first press. Supply `device_class: restart` for that
button.

For sensors, provide a numeric string and the corresponding
`unit_of_measurement` and `device_class`. For example, use `W` and `power`
for power readings or `Wh`, `energy`, and `state_class: total_increasing`
for cumulative energy. For a grid-point reading, positive power means
import. Number entities supply `min`, `max`, and `step`. Select entities
supply up to eight `options` and the current option.

Register up to 32 entities and at least one entity or solar source. The server processes one request at a time with
bounded request and response sizes. Set a short deadline on equipment I/O
inside each callback. Use a stable binding to the physical device and assign
a single controller to each writable device. To move an existing device to
a bridge, replace its native binding, then verify that DISPATCH can observe
the selected entity in Preview.

## Solar production

Pass a `solar` callback to `Bridge` for a gateway that measures generation.
Select **DISPATCH SDK bridge** in the controller's solar source setup and
enter the expected gateway ID. Use the same endpoint and token as the saved
REST connection. Firmware polls this route on its solar production schedule.

The callback returns `SolarReading` with a stable 12-digit gateway ID, sample
age in seconds, current watts, today's production in hundredths of a kWh,
lifetime production in tenths of a kWh, and installed and online inverter
counts. Use the age of the underlying device observation. Return `None`
when the device is unreachable or the observation is older than 30 seconds.
The controller checks identity, age, and recent production progress before
using the reading in a solar plan.
