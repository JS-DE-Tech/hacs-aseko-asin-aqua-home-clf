# ASEKO ASIN AQUA Home for Home Assistant

<p align="center">
  <img src="https://raw.githubusercontent.com/JS-DE-Tech/hacs-aseko-asin-aqua-home-clf/main/docs/images/aseko_asin_aqua_home.png"
       alt="ASEKO ASIN AQUA Home pool controller"
       width="420">
</p>

Home Assistant integration for the ASEKO ASIN AQUA Home pool controller using a local TCP gateway connection.

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-41BDF5?logo=home-assistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom%20Repository-41BDF5)](https://hacs.xyz/)
[![Protocol](https://img.shields.io/badge/protocol-local%20TCP-success)](#scope-and-protocol-notes)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](https://github.com/JS-DE-Tech/hacs-aseko-asin-aqua-home-clf/blob/main/LICENSE)
[![Support via PayPal](https://img.shields.io/badge/Support%20via-PayPal-0070BA?logo=paypal&logoColor=white)](https://paypal.me/JensSaffrich)

Read-only Home Assistant HACS custom integration for the **ASEKO ASIN AQUA Home**
pool controller. It receives controller data locally over the LAN without MQTT
or Node-RED and exposes push-updated sensors and binary sensors.

## Example Home Assistant dashboard

The integration exposes the ASEKO ASIN AQUA Home values as standard Home
Assistant entities. They can be used in a custom dashboard together with data
from other pool components to provide a complete overview of water chemistry,
dosing containers, temperatures, water level, circulation, filtration, heating,
and maintenance activity.

### Desktop view

<p align="center">
  <a href="docs/images/homeassistant_dashboard.png">
    <img
      src="https://raw.githubusercontent.com/JS-DE-Tech/hacs-aseko-asin-aqua-home-clf/main/docs/images/homeassistant_dashboard.png"
      alt="Desktop Home Assistant pool dashboard with ASEKO ASIN AQUA Home data"
      width="900">
  </a>
</p>

### Mobile view

<p align="center">
  <a href="docs/images/homeassistant_mobil1.png">
    <img
      src="https://raw.githubusercontent.com/JS-DE-Tech/hacs-aseko-asin-aqua-home-clf/main/docs/images/homeassistant_mobil1.png"
      alt="Mobile Home Assistant pool dashboard overview"
      width="390">
  </a>
  <a href="docs/images/homeassistant_mobil2.png">
    <img
      src="https://raw.githubusercontent.com/JS-DE-Tech/hacs-aseko-asin-aqua-home-clf/main/docs/images/homeassistant_mobil2.png"
      alt="Mobile Home Assistant pool dashboard technical details"
      width="390">
  </a>
</p>

Dashboard reference used for these screenshots: **Pool Cockpit v2.7.9**.

The matching public dashboard files are available under [`dashboard/`](dashboard/).

The ASEKO integration supplies the controller values used in these examples,
including water chemistry, ASIN temperatures, water level, relay states, dosing
container estimates, and maintenance data. The pump, BESGO pressure reserve,
filter pressure and filtered-water volume, heating system, and BADU FlowSonic
Plus require additional sensors or integrations. Their entity IDs and any
templates must be adapted to the individual installation. If a required entity
is unavailable, the corresponding dashboard field should display
`unavailable` or be hidden.

For a local Home Assistant connection of the **BADU FlowSonic Plus** through an
ifm AL1350/AL1352 IO-Link master, see
[JS-DE-Tech/hacs-ifm-io-link-master-al13xx-iot](https://github.com/JS-DE-Tech/hacs-ifm-io-link-master-al13xx-iot).

These screenshots show one possible custom layout. This integration does not
install a preconfigured dashboard automatically.

## Installation
1. In HACS, add this GitHub repository as a **Custom repository** with category **Integration**.
2. Install **ASEKO ASIN AQUA Home**, restart Home Assistant, and add the integration from **Settings → Devices & services**.
3. Disable the old Node-RED flow before enabling this integration: only one TCP listener can receive the gateway connection.
4. Configure the USR-K5 serial gateway target to the IP address of your Home Assistant host and TCP port `47524`.

The listener defaults to `0.0.0.0:47524`. One-way forwarding of the original received TCP bytes to `pool.aseko.com:47524` is enabled by default so the existing ASEKO cloud connection can be preserved. Cloud responses are drained but are not relayed back to the local gateway. Forwarding can be disabled or changed from the integration options.

<h2>USR-K5 gateway configuration</h2>

<p>
  You need to reconfigure the ASEKO USR-K5 gateway so that it sends the
  controller data to your Home Assistant server instead of connecting directly
  to the ASEKO cloud endpoint.
</p>

<h3>Access the USR-K5 gateway</h3>

<ol>
  <li>
    Open the local IP address of the ASEKO USR-K5 gateway in a web browser.
  </li>
  <li>
    Sign in with the default credentials:
    <pre><code>Username: admin
Password: admin</code></pre>
  </li>
  <li>
    Open the menu:
    <pre><code>Serial Port</code></pre>
  </li>
</ol>

<h3>Configure the TCP destination</h3>

<p>
  The existing configuration usually points to the ASEKO cloud server:
</p>

<pre><code>Remote Server Addr:   pool.aseko.com
Remote Port Number:   47524</code></pre>

<p align="center">
  <img
    src="https://raw.githubusercontent.com/JS-DE-Tech/hacs-aseko-asin-aqua-home-clf/main/docs/images/usr-k5-serial-port-configuration.png"
    alt="USR-K5 Serial Port configuration"
    width="850">
</p>

<p>
  Keep the existing serial-port settings unchanged unless your installation
  uses different verified values.
</p>

<p>Typical settings are:</p>

<pre><code>Baud Rate:           57600
Data Size:           8 bit
Parity:              None
Stop Bits:           1 bit
Flow Control:        NFC
Local Port Number:   47524
Remote Port Number:  47524
Work Mode:           TCP Client</code></pre>

<p>
  Change <code>Remote Server Addr</code> to the local IP address or DNS name of
  your Home Assistant server.
</p>

<p>
  For the installation shown in the screenshot, the Home Assistant server uses:
</p>

<pre><code>10.100.1.90</code></pre>

<p>The resulting configuration is:</p>

<pre><code>Remote Server Addr:   10.100.1.90
Remote Port Number:   47524</code></pre>

<p>
  The <strong>Remote Port Number</strong> must remain:
</p>

<pre><code>47524</code></pre>

<p>
  The ASEKO ASIN AQUA Home integration listens on the same TCP port in Home
  Assistant.
</p>

<h3>Save and restart the gateway</h3>

<ol>
  <li>Click <strong>Save</strong>.</li>
  <li>
    Restart the USR-K5 gateway if requested by the web interface.
  </li>
  <li>
    Add the <strong>ASEKO ASIN AQUA Home</strong> integration in Home Assistant.
  </li>
  <li>
    Keep the listener port set to:
    <pre><code>47524</code></pre>
  </li>
</ol>

<p>
  Only one application can receive the incoming TCP connection from the USR-K5
  gateway. Disable any previous Node-RED TCP listener before enabling the native
  Home Assistant integration.
</p>

<h3>Optional: keep forwarding data to the ASEKO cloud</h3>

<p>
  The integration can forward the received TCP data from Home Assistant to the
  ASEKO cloud endpoint:
</p>

<pre><code>pool.aseko.com:47524</code></pre>

<p>
  This forwarding path is optional and can be enabled or disabled from the
  integration settings.
</p>

<p>When enabled:</p>

<pre><code>USR-K5 gateway -&gt; Home Assistant -&gt; ASEKO cloud</code></pre>

<p>When disabled:</p>

<pre><code>USR-K5 gateway -&gt; Home Assistant</code></pre>

<p>
  Cloud responses are discarded and are not sent back to the local gateway.
</p>

<h3>Alternative: local DNS redirection</h3>

<p>
  As an alternative to changing the USR-K5 configuration, a local DNS override
  can redirect the original ASEKO cloud hostname to the Home Assistant server.
</p>

<p>Example:</p>

<pre><code>pool.aseko.com -&gt; 10.100.1.90</code></pre>

<p>
  This approach can be useful if access to the USR-K5 web interface is no longer
  possible, for example because the gateway password has been changed or is
  unknown.
</p>

<p>Important limitations:</p>

<ul>
  <li>
    DNS redirection works only when the USR-K5 gateway is configured with the
    hostname <code>pool.aseko.com</code>.
  </li>
  <li>
    DNS redirection does not work when the gateway stores a fixed remote IP
    address.
  </li>
  <li>
    The USR-K5 gateway must use the local DNS server that provides the override.
  </li>
  <li>
    Home Assistant must still listen on TCP port <code>47524</code>.
  </li>
</ul>

<h3>Security note</h3>

<p>
  The credentials <code>admin</code> / <code>admin</code> are common
  factory-default credentials for the USR-K5 gateway. Change the password after
  setup if supported by the device and keep the management interface accessible
  only from the trusted local network.
</p>

## Scope and protocol notes
This first version is intentionally **read-only**. It does not send pool-control commands. The decoder ports the tested offsets from `reference/node-red-flow.json`, including chemistry, temperatures, water level, schedules, delays, concentrations, error bits, relay bits, and stateful status handling.

Firmware-v7 binary traffic on port `47524` is synchronized as 120-byte wire frames. The currently implemented field mapping still decodes bytes `0..115`; bytes `116..119` are preserved for diagnostics as an undecoded wire-frame tail. The TCP parser retains incomplete synchronized frames across reads, rejects shifted or malformed frames before publishing updates, and recovers synchronization on the next valid frame. More packet captures are needed to document the tail bytes across firmware variants and to fully explain the inferred raw `byte24` field. Optional temporary capture diagnostics include raw TCP chunks, bounded candidate summaries, aligned frame hex, and decoded payload hex while redacting configured network hosts.

## Reference

A byte-level protocol reference for the currently implemented ASEKO ASIN AQUA
Home LAN payload is available here:

[`reference/aseko_asin_aqua_home_protocol_analysis.md`](reference/aseko_asin_aqua_home_protocol_analysis.md)

The document distinguishes between implemented mappings, derived Home Assistant
values and protocol fields that still require additional packet captures.

## Status and alarm handling

Version `1.0.7` and later adds a combined disturbance status sensor. It reports `OK` when
no supported disturbance is active. When one or more alarms are active, the value
contains the alarm texts separated by ` |`, for example
`Zu schnelle pH-Wert-Änderung | Kein Durchfluss an den Sonden`.

The individual alarm binary sensors remain available. The rapid pH-change alarm
is decoded from the confirmed `data[12] & 0x04` bit. The time-correction alarm is
derived locally from the calculated time deviation and the configurable threshold,
not directly from the device error bit. The threshold can be set from 1 to 10
minutes and defaults to 5 minutes.

The buffer-tank alarm labels can optionally be shown as water-level labels. With
the option disabled, the entities are named `Störung: Pufferbehälter leer` and
`Störung: Pufferbehälter übergelaufen`. With the option enabled, they are shown
as `Störung: Wasserstand zu niedrig` and `Störung: Wasserstand zu hoch`.

Two additional binary sensors expose the filtration mode as `Status: 24h
NONSTOP` and `Status: Timer`.

## Dosing container tracking and calibration

The integration can estimate the remaining volume for the chlorine, pH-minus,
flocculation, and algicide containers from the ASEKO dosing relay runtimes. These
values are estimates: the controller only reports whether each dosing pump relay is
active, so Home Assistant multiplies the accumulated runtime by the pump flow rate
you configure manually.

Each channel has two configuration number entities:

- container size in liters
- pump flow rate in milliliters per minute (`ml/min`)

Existing pump flow-rate values stored in `l/h` are migrated automatically to
`ml/min` during the update, so no recalibration is required. Total consumed volume
and remaining volume stay in liters and keep their existing values. Daily
consumption is exposed separately in milliliters and resets at local midnight.

The default pump flow rate is `0.0 ml/min`, which means the channel is not
calibrated yet. While a channel is uncalibrated, runtime tracking continues. If a
previously calculated pump flow rate is already stored, version `1.0.8` and later
uses it as a fallback so consumed liters, remaining liters, remaining percent, and
daily consumption remain available after an update or reload. The suggested flow
rate sensor becomes available after runtime has been recorded and is also shown in
`ml/min`.

Recommended calibration workflow:

1. Leave the pump flow rate at `0.0 ml/min`.
2. Install a full chemical container.
3. Press the matching `... Container Replaced` / `... Kanister ausgetauscht` button.
4. Let the integration accumulate runtime while the ASEKO controller doses normally.
5. When the container is actually empty, read the channel's suggested pump flow rate.
6. Enter that value manually into the channel's pump flow-rate number entity.
7. Install a new full container.
8. Press the matching replacement button again.
9. The integration can now estimate consumed volume, remaining liters, remaining
   percent, and daily consumption for the new container.

Total runtime and current-day runtime are persisted in Home Assistant storage and
survive restarts, reloads, integration updates, option changes, and Home Assistant
updates. To avoid unbounded overcounting after downtime, a single interval between
valid payloads is only counted when it is no longer than 60 seconds.

## Container remaining-days forecasts

Version `1.0.9` adds two sensors per chemical: `..._remaining_days` and
`..._forecast_status`, using the existing `asin_aqua_home_<channel>` prefix.
The channels are `chlorine`, `ph_minus`, `flocculation`, and `algicide`.
Existing entity IDs (including numeric, custom, and duplicated-prefix IDs), units,
calibration, accumulated runtime, and container replacement data are preserved.
The forecast history is separate: `.storage/aseko_asin_aqua_home_forecast`.

The estimate divides the remaining volume by expected daily consumption. It uses
up to 14 completed active days, giving the last seven usable active days twice the
weight. A usable day needs at least 90% observed coverage and six hours of enabled
dosing. At least three usable days are required. The current day is excluded.
Runtime is normalized to 24 hours of enabled dosing and converted with the same
configured/calculated pump flow rate used by the existing volume sensors.
Changing calibration therefore recalculates the estimate, just like the existing
remaining-volume calculation; it does not erase recorded runtime.

Setting algicide or flocculation dosing to zero **on the ASEKO device** pauses that
channel's forecast. Paused time is excluded, while ordinary relay-off time with
dosing enabled is included. Missing packets and intervals over 60 seconds never
count as observed zero consumption. History survives restarts and container
replacements and is retained for 180 days, including multi-week dosing pauses.
After a long pause, a retained estimate is provisional until at least three usable
days fall within the last seven calendar days. Incomplete recent samples also
make estimates provisional. History older than 180 days requires learning again.

Status values (translated in the Home Assistant UI):

| State | Meaning |
| --- | --- |
| `active` | Sufficient recent observations |
| `provisional` | Older or incomplete observations; estimate needs confirmation |
| `paused` | Algicide/flocculation dose is zero |
| `learning` | Initial collection of observations |
| `calibration_missing` | No positive pump flow rate available |
| `no_consumption` | Usable days contain no pump runtime |
| `insufficient_data` | Too few adequately observed active days |
| `device_data_missing` | No current valid device data or dose setting |

The remaining-days sensor is unknown when no numeric forecast is justified. It
never uses zero to mean paused, uncalibrated, or offline. Numeric results round
down: `0 d` means less than one full day, including an empty container. Attributes
include `estimated_daily_consumption_ml`, `evaluated_active_days`,
`last_sample_date`, `last_observation`, `last_calculation`, and `forecast_status`.

Daily consumption resets at Home Assistant's local midnight even without new
gateway packets. This does not reset the total runtime or discard historical days.
Store-format errors prevent loading rather than silently replacing stored values.
This protection applies when running this version; it cannot change how older
already-released versions behave. Keep a full Home Assistant backup before updates
or downgrades. Update the integration in place, without deleting/re-adding it.

## Live Cloud Forwarding switch

The **Cloud Forwarding** switch controls only the optional outbound connection from
Home Assistant to `pool.aseko.com:47524`. It does not reload the integration, stop
the local TCP listener, or close the USR-K5 gateway connection. Cloud Forwarding
can be toggled without interrupting the local USR-K5 gateway connection or local
Home Assistant sensor updates.

When enabled, traffic flows one way from `USR-K5 gateway -> Home Assistant -> ASEKO cloud`.
When disabled, the local path remains `USR-K5 gateway -> Home Assistant`. Cloud
responses are discarded and are never relayed back to the gateway.

## Last Backwash sensor

The **Last Backwash** / **Letzte Rückspülung** sensor reports a Home Assistant
timestamp for the most recent confirmed backwash detected from the existing
`relay_backwash` state.

The Last Backwash sensor records a backwash only when the backwash relay remains
continuously active for at least 60 seconds. Short relay activations are ignored.
The value is stored persistently and survives Home Assistant restarts,
integration reloads and integration updates.

The tracker stores its state separately from dosing-container runtime tracking. It
also ignores unobserved gaps longer than 60 seconds, so restarts, reloads, network
interruptions, gateway disconnects, and clock corrections do not create false
backwash events.

## Entity IDs for new installations

Newly created entities provide semantic suggested object IDs such as
`sensor.asin_aqua_home_ph`, `binary_sensor.asin_aqua_home_relay_backwash`,
`switch.asin_aqua_home_cloud_forwarding`, and
`sensor.asin_aqua_home_last_backwash`. Unique IDs are unchanged so existing Home
Assistant entity-registry entries remain stable.

## Legacy entity IDs

Older installations may retain numeric entity IDs such as
`binary_sensor.asin_aqua_home_3`. The integration now provides semantic entity
ID suggestions for newly created registry entries. Existing IDs are not renamed
automatically because automatic renaming could break dashboards, automations,
scripts and templates.

Existing entity IDs can be reset or renamed manually from the Home Assistant
entity settings after updating the integration.

## Development checks

Run `python -m pip install -r requirements-test.txt`, then `python -m pytest -q`
from the repository root. The suite uses lightweight Home Assistant stubs and
checks parsing, storage migration, retained entity identities, option preservation,
forecast behavior, local midnight/DST, and shutdown/reload behavior. GitHub runs
these tests with Python 3.12 and 3.13. These checks do not replace a smoke test in
a running Home Assistant instance before deploying to a production pool setup.
