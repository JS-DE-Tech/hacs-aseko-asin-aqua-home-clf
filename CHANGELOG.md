# Changelog

## 1.0.9

- Add estimated remaining days and a translated forecast status for each of the
  four dosing containers, with independent persistent daily observation history.
- Recognize algicide/flocculation pauses when the controller dose is zero. Exclude
  pauses and unobserved gaps from consumption averages; mark stale estimates as
  provisional after long pauses.
- Preserve all existing entity IDs, including legacy duplicated-prefix IDs.
- Preserve number-entity calibration and container options when the options
  dialog is saved.
- Refuse unsupported newer tracker storage instead of overwriting it with defaults.
- Reset today's consumption at local midnight even when no gateway data arrives,
  preserving accumulated runtime and container/replacement/calibration state.
- Run Python regression tests on pushes, pull requests, and published releases.

## 1.0.8

- Use the persisted calculated pump flow rate as a fallback for consumed volume,
  remaining volume, remaining percent, and daily consumption when the editable
  configured flow rate is still `0 ml/min`.
- Keep active TCP gateway sessions alive when decoder-only options change, such as
  water-level offset, water-level alarm labels, maximum chlorine, and the time
  correction threshold.
- Keep configuration number entities available independently of the live ASEKO data
  stream.
- Leave the 120-byte TCP framing, cloud forwarding, and backwash logic unchanged.

## 1.0.7

- Add extended ASIN AQUA Home alarm handling, including the confirmed
  `data[12] & 0x04` rapid pH-change alarm.
- Add a combined disturbance status sensor that lists active alarms without
  repeating the `Störung:` prefix in the value.
- Add binary sensors for `Status: 24h NONSTOP` and `Status: Timer`, decoded from
  the observed filtration mode byte.
- Add an option to display the buffer-tank alarm entities and combined status as
  water-level alarms instead.
- Replace the separate time-correction recommendation sensor with a configurable
  threshold that drives `Störung: Zeitkorrektur`.

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
