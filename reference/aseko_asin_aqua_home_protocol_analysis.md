# ASEKO ASIN AQUA Home — Protocol Analysis

**Integration domain**: `aseko_asin_aqua_home`  
**Target device**: ASEKO ASIN AQUA Home  
**Transport**: local TCP stream through USR-K5 gateway  
**Default local listener**: `0.0.0.0:47524`  
**Optional cloud forwarding**: `pool.aseko.com:47524`  
**Decoder source**: tested Node-RED flow ported into the native Home Assistant integration  
**Firmware-v7 binary wire-frame length**: `120 bytes` on port `47524`
**Minimum decodable payload length**: `116 bytes`  

---

## Evidence levels

| Marker | Meaning |
|--------|---------|
| ✓ | Implemented and validated by the current decoder |
| ◇ | Implemented from the tested Node-RED flow but needs more packet captures |
| ? | Unknown or not yet decoded |
| — | Padding, raw diagnostic field or intentionally not exposed |

## TCP framing and synchronization

Firmware-v7 binary traffic on port `47524` is handled as fixed 120-byte wire
frames. The tested Node-RED flow accesses offsets through byte `115`, and this
repository therefore keeps `MIN_PAYLOAD_LENGTH = 116` as the currently mapped
decode span. Bytes `116..119` are preserved in diagnostics but remain undecoded.

The current parser behavior is:

- buffers fragmented TCP chunks
- handles multiple wire frames received in one read
- searches for structural 120-byte binary frame starts
- validates repeated block headers and block IDs before semantic decoding
- decodes only aligned bytes `0..115`
- retains incomplete synchronized wire frames for the next read
- discards malformed or shifted candidates before publishing values
- exposes bounded capture diagnostics when enabled

Before publishing decoded values, the parser validates at least:

- controller month
- controller day
- controller hour
- controller minute
- controller second
- valid controller datetime
- pH range
- chlorine range
- filter schedule hours and minutes
- backwash schedule hours and minutes

The parser consumes exactly one aligned 120-byte binary wire frame at a time.
Additional captures are still required to determine whether bytes `116..119`
are padding, checksum data or another protocol field.

## Byte-by-byte mapping implemented by this integration

| Byte(s) | Field | Decode rule | Home Assistant value | Evidence |
|---------|-------|-------------|----------------------|----------|
| 6 | year | byte + 2000 | `system_date`, `system_time`, `time_deviation`, `set_time_recommended` | ✓ |
| 7 | month | raw byte, validated as 1..12 | `system_date`, `system_time`, `time_deviation`, `set_time_recommended` | ✓ |
| 8 | day | raw byte, validated as 1..31 and by full datetime construction | `system_date`, `system_time`, `time_deviation`, `set_time_recommended` | ✓ |
| 9 | hour | raw byte, validated as 0..23 | `system_date`, `system_time`, `time_deviation`, `set_time_recommended` | ✓ |
| 10 | minute | raw byte, validated as 0..59 | `system_date`, `system_time`, `time_deviation`, `set_time_recommended` | ✓ |
| 11 | second | raw byte, validated as 0..59 | `system_date`, `system_time`, `time_deviation`, `set_time_recommended` | ✓ |
| 13 | error_byte | raw error bit field | `error_byte`, `error_byte_binary`, `error_*` binary sensors | ◇ |
| 14–15 | ph | big-endian word / 100 | `ph` | ✓ |
| 16–17 | chlorine | big-endian word / 100 | `chlorine` | ✓ |
| 23–24 | air_temperature | signed custom decode / 10; if byte 23 is `255`, decode as `(byte24 - 256) / 10`, otherwise decode as big-endian word / 10; implausible values retain previous valid value | `air_temperature` | ◇ |
| 25–26 | water_temperature | big-endian word / 10; implausible values retain previous valid value | `water_temperature` | ✓ |
| 27 | water_level_probe | raw probe centimeters | `water_level_probe` | ✓ |
| 27 | water_level | raw value + configurable offset | `water_level` | ✓ |
| 29 | relay_byte | raw relay bit field | `relay_byte`, `relay_byte_binary`, `relay_*` binary sensors | ◇ |
| 52 | ph_target | byte / 10 | `ph_target` | ✓ |
| 53 | chlorine_target | byte / 10 | `chlorine_target` | ✓ |
| 54 | flocculation_dose | raw byte | `flocculation_dose` | ✓ |
| 55 | water_temperature_target | raw byte | `water_temperature_target` | ✓ |
| 56–57 | filter_1_start | HH:MM, hour validated as 0..23 and minute as 0..59 | `filter_1_start` | ✓ |
| 58–59 | filter_1_end | HH:MM, hour validated as 0..23 and minute as 0..59 | `filter_1_end` | ✓ |
| 60–61 | filter_2_start | HH:MM, hour validated as 0..23 and minute as 0..59 | `filter_2_start` | ✓ |
| 62–63 | filter_2_end | HH:MM, hour validated as 0..23 and minute as 0..59 | `filter_2_end` | ✓ |
| 68 | backwash_interval_days | raw byte | `backwash_interval_days` | ✓ |
| 69–70 | backwash_start | HH:MM, hour validated as 0..23 and minute as 0..59 | `backwash_start` | ✓ |
| 72 | algicide_dose | raw byte | `algicide_dose` | ✓ |
| 76–77 | filling_time_limit | big-endian word / 60 | `filling_time_limit` | ✓ |
| 78 | raw_status | stateful status byte | `raw_status`, retained status attributes | ◇ |
| 92–93 | pool_volume | big-endian word | `pool_volume` | ✓ |
| 102 | water_level_low | raw byte | `water_level_low` | ✓ |
| 103 | refill_on | raw byte | `refill_on` | ✓ |
| 104 | refill_off | raw byte | `refill_off` | ✓ |
| 105 | water_level_high | raw byte | `water_level_high` | ✓ |
| 106–107 | dosing_delay | big-endian word / 60 | `dosing_delay` | ✓ |
| 109–110 | startup_delay | big-endian word / 60 | `startup_delay` | ✓ |
| 111 | concentration | raw byte | `concentration` | ✓ |
| 112 | ph_minus_concentration | raw byte | `ph_minus_concentration` | ✓ |
| 114 | max_chlorine_doses | raw byte | `max_chlorine_doses` | ✓ |
| 115 | max_ph_doses | raw byte | `max_ph_doses` | ✓ |

Raw diagnostic fields exposed by the integration include:

| Field | Source | Purpose | Evidence |
|-------|--------|---------|----------|
| `error_byte_binary` | byte `13` formatted as eight binary digits | Diagnostic view of the raw error bit field | — |
| `relay_byte_binary` | byte `29` formatted as eight binary digits | Diagnostic view of the raw relay bit field | — |
| `byte24` | byte `25` in the current implementation | Unresolved raw diagnostic field; despite the name, it currently mirrors the first byte of the water-temperature word | ? |
| `byte24_binary` | `byte24` formatted as eight binary digits | Diagnostic view of unresolved `byte24` | ? |
| `raw_status` | byte `78` | Diagnostic view of the stateful status byte | ◇ |

`byte24` remains unresolved. It is intentionally documented as a raw diagnostic
field rather than a verified protocol value.

## Error byte mapping

The current decoder interprets byte `13` as an eight-bit error field.

| Bit | Mask | Key | Meaning |
|-----|------|-----|---------|
| 0 | `0x01` | `hour_dosing_exceeded` | Hourly dosing limit exceeded |
| 1 | `0x02` | `time_correction` | Controller time correction required |
| 2 | `0x04` | `no_probe_flow` | No flow at the probes |
| 3 | `0x08` | `buffer_tank_empty` | Buffer tank empty |
| 4 | `0x10` | `buffer_tank_overflow` | Buffer tank overflow |
| 5 | `0x20` | `low_filling_speed` | Filling speed too low |
| 6 | `0x40` | `ph_doses_without_change` | pH dosing without measured change |
| 7 | `0x80` | `chlorine_doses_without_change` | Chlorine dosing without measured change |

The meaning is inherited from the tested Node-RED mapping and should remain
traceable to packet captures.

## Relay byte mapping

The current decoder interprets byte `29` as an eight-bit relay field.

| Bit | Mask | Key | Meaning |
|-----|------|-----|---------|
| 0 | `0x01` | `backwash` | Backwash relay |
| 1 | `0x02` | `filling` | Refill relay |
| 2 | `0x04` | `heating` | Heating demand relay |
| 3 | `0x08` | `filtration` | Filtration relay |
| 4 | `0x10` | `algicide` | Algicide dosing relay |
| 5 | `0x20` | `flocculation` | Flocculation dosing relay |
| 6 | `0x40` | `chlorine` | Chlorine dosing relay |
| 7 | `0x80` | `ph_minus` | pH-minus dosing relay |

Relay runtimes are also used by the persistent dosing-container tracker for the
chlorine, pH-minus, flocculation and algicide channels.

## Stateful status-byte handling

Byte `78` is interpreted statefully rather than as a simple direct bitmask. The
current decoder retains previous status state for special cases and updates
selected booleans from observed raw status values.

Implemented mappings:

```text
current == 0:
    preserve previous state

current == 40:
    open_menu = true

filtration true:
    1, 17, 34, 98, 129, 130, 131, 145, 162, 178

filtration false:
    64, 226

heating true:
    130, 131, 162, 178

standby true:
    1, 17, 64, 129, 145

standby false:
    any non-special value except 64 and 1
```

When `current == 40`, `open_menu` is set to true. For other non-zero status
values, `open_menu` is set to false after applying the filtration, heating and
standby rules. Additional packet captures are still useful to document the
semantic meaning of every status value.

## Derived Home Assistant functionality

Not every Home Assistant entity is a direct protocol byte. The integration also
builds derived entities and persistent helpers from decoded payloads and user
configuration.

```text
water_level
    = water_level_probe + configurable water-level offset

last_backwash
    = persistent timestamp recorded when relay_backwash remains continuously
      active for at least 60 seconds

dosing runtime
    = accumulated relay runtime for chlorine, pH-minus, flocculation and algicide

remaining liters
    = container size - consumed liters

remaining percent
    = remaining liters / container size × 100

suggested flow rate
    = container size / accumulated runtime since container replacement
```

Container sizes and pump flow rates are manually configurable. These settings,
together with accumulated dosing runtime and confirmed backwash state, persist
across Home Assistant restarts and integration reloads.

## Known limitations and open protocol questions

1. Bytes 116..119 are not currently decoded.
   Additional packet captures are required to determine whether these bytes are
   padding, checksum data or another protocol field.

2. byte24 remains unresolved.
   It is exposed as a raw diagnostic field.

3. The semantic meaning of every raw status-byte value is not fully documented.

4. The current implementation targets the tested ASEKO ASIN AQUA Home LAN
   payload. Firmware variants may require additional validation.

5. Additional captures should be collected while individual relays are active
   to verify all relay-bit assignments independently.

6. Additional captures should be collected before and after changing individual
   controller settings to verify unknown bytes and scaling rules.

## Recommended packet-capture workflow

1. Enable capture diagnostics temporarily.
2. Record a baseline frame while the system is idle.
3. Activate only one relay or change only one controller setting at a time.
4. Record the next validated payload.
5. Compare byte differences.
6. Confirm the displayed value in the ASEKO app or controller UI.
7. Add only independently verified mappings to this reference.
8. Disable capture diagnostics after testing.

Raw payloads may contain device-specific information. Redact network addresses,
serial numbers and other installation-specific identifiers before publishing
captures publicly.
