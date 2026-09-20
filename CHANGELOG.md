# Changelog

## 1.0.10

- Expand the README with desktop and mobile Pool Cockpit screenshots and notes about required additional sensors.
- Add sanitized Pool Cockpit v2.7.9 source, installation instructions, and standalone previews under `dashboard/`.
- Add a reference to the local BADU FlowSonic Plus connection through the ifm AL1350/AL1352 integration.
- No runtime behavior of the ASEKO integration changes in this release.

## 1.0.6

- Store and display dosing pump flow rates in `ml/min` instead of `l/h`, with
  automatic migration for existing config entries and stored suggested flow rates.
- Add per-channel daily consumption sensors in `ml`, persisted across restarts and
  reset at the local Home Assistant midnight.
- Keep total consumed volume and remaining volume in liters without requiring
  recalibration.

## 1.0.5

- Treat firmware-v7 port 47524 binary traffic as 120-byte wire frames while
  keeping the current decoded field mapping limited to bytes 0..115.
- Retain partial synchronized frames across TCP reads and reject shifted or
  malformed frames before updating entities or persistent relay trackers.
- Preserve bytes 116..119 for diagnostics as an undecoded wire-frame tail.
