<!-- SPDX-FileCopyrightText: 2026 SPECTRE WORKS LLC -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# DISPATCH SDK

Build integration profiles and LAN bridges for SPECTRE WORKS DISPATCH.
The SDK uses Python 3.11 or later with the standard library.

## Integration profiles

Start with a [stock profile](profiles), then change the fields listed in the
[profile contract](profiles.md). Validate it and produce an upload file.

```sh
python3 -m dispatch_sdk.profile profiles/fronius.json -o fronius.dispatch-profile
```

On firmware that supports profile version 1, open **Settings → Integration
profiles** and choose the file. Restart the controller to apply it. The same
page shows the active and saved mappings and lets you restore the stock profile.
Check readings in Preview and reverify grid direction if prompted before
resuming operation.

## LAN bridge

Use the [bridge interface](bridge.md) for a custom protocol with code that runs
on a separate LAN machine. The SDK provides a bounded Home Assistant-compatible
REST server and a mock outlet and meter you can run locally.

```sh
umask 077
python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > bridge-token
python3 -m examples.demo_bridge --token-file bridge-token
```

Use `--bind` with a trusted LAN IPv4 address to connect a controller during
development. Register your own device callbacks with `dispatch_sdk.bridge.Bridge`.

Use the [grid meter bridge](grid-bridge.md) for SunSpec Modbus TCP meters,
SolarEdge import/export meters, and Solarman V5 logger setups with a
documented inverter register map.

## License

Copyright 2026 SPECTRE WORKS LLC. The SDK is available under the
[Apache License, Version 2.0](LICENSE). The
[DISPATCH application repository](https://github.com/Spectre-Works/dispatch)
publishes its own license terms.
