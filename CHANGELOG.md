# Changelog

## 1.0.5

- Treat firmware-v7 port 47524 binary traffic as 120-byte wire frames while
  keeping the current decoded field mapping limited to bytes 0..115.
- Retain partial synchronized frames across TCP reads and reject shifted or
  malformed frames before updating entities or persistent relay trackers.
- Preserve bytes 116..119 for diagnostics as an undecoded wire-frame tail.
