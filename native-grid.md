<!-- SPDX-FileCopyrightText: 2026 SPECTRE WORKS LLC -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Native grid meter profiles

In DISPATCH/01 firmware with native SunSpec and Solarman support, open
**Settings → Energy sources → Connect or verify a whole-site meter** and
choose **Load meter profile**. The profile fills the form. Enter the local
device address and serial, review the settings, and save. DISPATCH polls the meter or logger
directly from the Atom.

| Profile | Starting values |
| --- | --- |
| [SunSpec Modbus TCP](native_profiles/sunspec-meter.json) | Port 502, base address 40000, and meter model 203. Models 201–204 and 211–214 are supported. |
| [SolarEdge attached meter](native_profiles/solaredge-meter.json) | Port 1502, base address 40000, and model 203. Match the meter model, position, and unit on your installation. |
| [Solarman V5](native_profiles/solarman-v5-meter.json) | Port 8899. Fill in the documented signed 16-bit grid power register, function, and decimal scale for the exact inverter. |

All addresses are zero-based Modbus addresses. The SunSpec meter position
counts occurrences of the selected model, beginning at one. Enter the
SunSpec Common model serial for the device serving the registers. For
Solarman V5, enter the logger serial and use synchronized clocks on the
logger and controller.

Use a whole-site import/export meter. Select the raw polarity so DISPATCH
shows positive import and negative export. Compare live readings in both
directions before saving direction verification. Changing the configured
meter or register settings requires verification again.

These JSON files are form presets. The existing [integration profile
uploader](profiles.md) handles the other firmware profile families.
