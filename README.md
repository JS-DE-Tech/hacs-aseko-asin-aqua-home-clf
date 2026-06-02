# ASEKO ASIN AQUA Home for Home Assistant

Read-only Home Assistant HACS custom integration for the **ASEKO ASIN AQUA Home** pool controller. It receives controller data locally over the LAN without MQTT or Node-RED and exposes push-updated sensors and binary sensors.

## Installation
1. In HACS, add this GitHub repository as a **Custom repository** with category **Integration**.
2. Install **ASEKO ASIN AQUA Home**, restart Home Assistant, and add the integration from **Settings → Devices & services**.
3. Disable the old Node-RED flow before enabling this integration: only one TCP listener can receive the gateway connection.
4. Configure the USR-K5 serial gateway target to the IP address of your Home Assistant host and TCP port `47524`.

The listener defaults to `0.0.0.0:47524`. Transparent forwarding of the original received TCP bytes to `pool.aseko.com:47524` is enabled by default so the existing ASEKO cloud connection can be preserved. Forwarding can be disabled or changed from the integration options.

## Scope and protocol notes
This first version is intentionally **read-only**. It does not send pool-control commands. The decoder ports the tested offsets from `reference/node-red-flow.json`, including chemistry, temperatures, water level, schedules, delays, concentrations, error bits, relay bits, and stateful status handling.

The tested extended payload accesses bytes `0..115`; the TCP parser therefore buffers the stream into fixed 116-byte frames. More packet captures are needed to verify whether every firmware variant uses the same fixed framing and to fully document the inferred raw `byte24` field. Diagnostics include raw protocol bytes interpreted by the integration while redacting configured network hosts.

## Maintainer note: external HACS metadata
HACS validates metadata that is managed outside this repository. Add repository topics such as `hacs`, `home-assistant`, `aseko`, and `pool-controller` under **GitHub → About → Settings**. Integration brand assets belong in the separate [`home-assistant/brands`](https://github.com/home-assistant/brands) repository. The workflow temporarily ignores the `topics` and `brands` checks so this source repository remains text-only. Remove each ignore after its external metadata has been configured.
