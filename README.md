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
[![License](https://img.shields.io/github/license/JS-DE-Tech/hacs-aseko-asin-aqua-home-clf)](LICENSE)
[![Support via PayPal](https://img.shields.io/badge/Support%20via-PayPal-0070BA?logo=paypal&logoColor=white)](https://paypal.me/JensSaffrich)

Read-only Home Assistant HACS custom integration for the **ASEKO ASIN AQUA Home**
pool controller. It receives controller data locally over the LAN without MQTT
or Node-RED and exposes push-updated sensors and binary sensors.

## Example Home Assistant dashboard

The integration exposes the ASEKO ASIN AQUA Home values as standard Home
Assistant entities. These entities can be combined in a dashboard to provide a
clear overview of the pool status, water values, relay states, dosing-container
levels, and recent maintenance activity.

The following screenshot shows one possible dashboard layout:

<p align="center">
  <img
    src="https://raw.githubusercontent.com/JS-DE-Tech/hacs-aseko-asin-aqua-home-clf/main/docs/images/aseko_dashboard.png"
    alt="Example Home Assistant dashboard for ASEKO ASIN AQUA Home"
    width="420">
</p>

The dashboard shown above is only an example. The integration does not install a
preconfigured dashboard automatically. Users can build their own dashboard from
the exposed Home Assistant entities and adapt the layout to their individual
requirements.

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

The tested extended payload accesses bytes `0..115`, which establishes a minimum decodable payload length of 116 bytes but does not prove the complete TCP wire-frame length. The TCP parser retains incomplete chunks, scans for semantically plausible payload starts, rejects shifted or malformed candidates, and recovers synchronization before publishing updates. More packet captures are needed to document delimiters or trailing bytes across firmware variants and to fully explain the inferred raw `byte24` field. Optional temporary capture diagnostics include raw TCP chunks and bounded candidate summaries while redacting configured network hosts.

## Reference

A byte-level protocol reference for the currently implemented ASEKO ASIN AQUA
Home LAN payload is available here:

[`reference/aseko_asin_aqua_home_protocol_analysis.md`](reference/aseko_asin_aqua_home_protocol_analysis.md)

The document distinguishes between implemented mappings, derived Home Assistant
values and protocol fields that still require additional packet captures.

## Dosing container tracking and calibration

The integration can estimate the remaining volume for the chlorine, pH-minus,
flocculation, and algicide containers from the ASEKO dosing relay runtimes. These
values are estimates: the controller only reports whether each dosing pump relay is
active, so Home Assistant multiplies the accumulated runtime by the pump flow rate
you configure manually.

Each channel has two configuration number entities:

- container size in liters
- pump flow rate in liters per hour

The default pump flow rate is `0.0 l/h`, which means the channel is not calibrated
yet. While a channel is uncalibrated, runtime tracking continues, but consumed
liters, remaining liters, and remaining percent stay unavailable. The suggested flow
rate sensor becomes available after runtime has been recorded.

Recommended calibration workflow:

1. Leave the pump flow rate at `0.0 l/h`.
2. Install a full chemical container.
3. Press the matching `... Container Replaced` / `... Kanister ausgetauscht` button.
4. Let the integration accumulate runtime while the ASEKO controller doses normally.
5. When the container is actually empty, read the channel's suggested pump flow rate.
6. Enter that value manually into the channel's pump flow-rate number entity.
7. Install a new full container.
8. Press the matching replacement button again.
9. The integration can now estimate consumed volume, remaining liters, and remaining
   percent for the new container.

Runtime is persisted in Home Assistant storage and survives restarts, reloads,
integration updates, option changes, and Home Assistant updates. To avoid
unbounded overcounting after downtime, a single interval between valid payloads is
only counted when it is no longer than 60 seconds.

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
