<!-- SPDX-FileCopyrightText: 2026 SPECTRE WORKS LLC -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Bridge a whole-site grid meter

Run this bridge on a LAN machine that can reach the controller and the
meter or gateway. The bridge reads power from the equipment and serves
`sensor.dispatch_grid_…` through the DISPATCH REST connection.

| Profile | Equipment and measurements |
| --- | --- |
| [SunSpec meter](bridge_profiles/sunspec-meter.toml) | SunSpec Modbus TCP Common model and meter model 201–204 (scaled integer) or 211–214 (float). Reads total active power. |
| [SolarEdge meter](bridge_profiles/solaredge-meter.toml) | SolarEdge inverter with local Modbus TCP and an attached import/export meter. Starts with port 1502, base 40000, and integer model 203. Use the configured unit ID and actual model for your setup. |
| [Solarman V5 meter template](bridge_profiles/solarman-v5-meter.toml) | Direct V5 logger connection with an identified logger serial. Supply the exact inverter's documented signed 16-bit grid power register, read function, and decimal scale. The template requires those values before it can run. |

## Configure and check a reading

1. Copy a profile to your local configuration directory. Fill in the equipment
   IPv4 address, unit ID, and the device or logger serial. In SunSpec profiles,
   the base is the zero-based address of the SunSpec signature. The meter index
   selects the occurrence of the specified meter model. In Solarman profiles,
   use the zero-based Modbus register address for the inverter reached by the
   logger.
2. Select a meter at the whole-site grid connection. Set the profile direction to
   match the raw register's sign for known import and export. The bridge reports
   positive values for import and negative values for export. Compare a sample
   against the installed meter before commissioning.

   ```sh
   python3 -m dispatch_sdk.grid_bridge /path/to/grid-meter.toml --check
   ```

3. Create a [bridge token](README.md#lan-bridge). Start the server with the
   LAN address of the bridge host.

   ```sh
   python3 -m dispatch_sdk.grid_bridge /path/to/grid-meter.toml \
     --bind BRIDGE_IPV4 --token-file /path/to/bridge-token
   ```

4. Save the bridge address, port and token in DISPATCH's Home Assistant
   connection. Under **Energy → Connect or verify a whole-site meter**, use
   the bridge address and the entity ID printed by the bridge. Compare both
   directions with the physical meter before enabling surplus control.
   Changing the profile produces a new entity ID so the prior meter binding
   cannot silently take over with a different mapping.

These profiles run on the bridge host. The controller connects through
its existing REST setup. Keep these LAN protocols on a trusted network.
The drivers send register reads only and report an unavailable value on
invalid replies or timeouts. Solarman replies must carry a current
observation timestamp. SunSpec measurements use the meter's current
register response, so the gateway must report unavailable data on device loss.

## Evidence and sources

Loopback simulators exercise SunSpec model discovery, integer and float
power, serial binding, missing data, Modbus TCP framing, the HTTP sensor
response, and Solarman V5 sequence, serial, timestamp and checksums.
Physical-device compatibility remains to be verified.

The implementation and fixtures were written for this SDK using protocol
facts from the references below. The drivers use the Python standard library and locally authored profiles.

- [Modbus Organization protocol and messaging specifications](https://www.modbus.org/modbus-specifications)
- [SunSpec model definitions pinned at 90b4a331](https://github.com/sunspec/models/tree/90b4a331dcca1d6eac69c1bead952fddcc5852e0/json)
- [SolarEdge SunSpec implementation technical note](https://knowledge-center.solaredge.com/sites/kc/files/sunspec-implementation-technical-note.pdf)
- [Solarman V5 implementation's protocol measurements pinned at 8cfe8465](https://github.com/jmccrohan/pysolarmanv5/blob/8cfe84650f48f0803c32b3c4ca061364abd9cf49/docs/solarmanv5_protocol.rst)
