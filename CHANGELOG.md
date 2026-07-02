# Changelog

All notable changes to this integration are documented here.

## [2026.6.4] - 2026-07-02

### Fixed

- **MEATER Pro / MEATER 2 Plus still not discovered, and manual setup found nothing** ([#3](https://github.com/Emkraan/homeassistant-meater/issues/3), reported by @finity69x2). Two problems:
  - **Auto-discovery matched only on data carried in the scan response.** The service UUID and local name a MEATER probe broadcasts ride in the BLE *scan response*, which arrives intermittently and which an ESP32/ESPHome Bluetooth proxy does not always forward - so the matchers added in 2026.6.2/2026.6.3 never fired reliably. (The `local_name: "MEATER*"` matcher also can't match the lowercase `meater2` name newer probes advertise, because Home Assistant's local-name matching is case-sensitive.) Auto-discovery now matches on the **Apption Labs manufacturer ID (`0x037B` / 891)**, which is broadcast in the *primary* advertising packet on every advertisement, plus case-insensitive local-name variants. Manufacturer ID `0x037B` confirmed against the Bluetooth SIG assigned-numbers database and community advertisement captures.
  - **Manual setup was a dead end.** "Add Integration → MEATER BLE" unconditionally reported "no probes found" - there was no manual path at all. It now runs an active Bluetooth scan and lists every advertisement Home Assistant has seen, so you can always pick your probe by name or, failing that, by its MAC address.
- **Charger/dock no longer offered as a device.** The MEATER Pro/2 Plus charger advertises separately but can't be read (connecting returns ATT `0x0e`). It is now recognized and skipped during discovery and hidden from the manual picker, with a clear message if encountered.

### Note

- The claim in 2026.6.3 that service UUID `c9e2746c-…` is "GATT-only, never advertised" was incorrect - it *is* advertised (the community M5Stack display discovers the probe purely by matching it under an active scan). The real issue was that it, like the local name, rides in the intermittently delivered scan response.

## [2026.6.3] - 2026-07-01

### Fixed

- **MEATER Pro / MEATER 2 Plus never discovered** ([#3](https://github.com/Emkraan/homeassistant-meater/issues/3), reported by @finity69x2). The service UUID added for Pro support in 2026.6.2 (`c9e2746c-…`) was captured by connecting to the probe and enumerating its GATT services - it is not actually present in the probe's BLE advertisement, so HA's `service_uuid` bluetooth matcher never fired and the config-flow discovery notification never appeared, even with the probe clearly visible to an ESPHome Bluetooth proxy. Auto-discovery now also matches on advertised local name (`MEATER*`), which the Pro/2 Plus does broadcast, so discovery works regardless of which service UUIDs a given firmware revision advertises.

## [2026.6.2] - 2026-06-28

### Added

- **MEATER Pro / MEATER 2 Plus support** ([#2](https://github.com/Emkraan/homeassistant-meater/issues/2), reported by @itsaw). The Pro probe advertises under a new BLE service UUID (`c9e2746c-…`) and delivers a 12-byte temperature payload (6 × signed int16 LE, one per sensor) instead of 6 bytes. Tip is decoded from sensor T0 (bytes 0-1) and ambient from sensor T5 (bytes 10-11), using the confirmed formula `raw / 32.0`. Temperature formula and sensor layout validated by community testing ([yyrliu/meater-pro-display](https://github.com/yyrliu/meater-pro-display)).
- Auto-discovery now matches both the original MEATER/MEATER+ service UUID and the MEATER Pro service UUID.

### Known limitation

- **Battery is not decoded for MEATER Pro**: the 5-byte battery payload format is not yet confirmed. The battery sensor will show unavailable on MEATER Pro until a future release adds the decode. Raw bytes are logged at DEBUG level to help gather data.

## [2026.6.1] - 2026-06-09

### Changed

- Clarified that the integration supports both the original **MEATER** and the **MEATER+** (they share the same BLE protocol) - branding and config-flow text updated from "MEATER+" to "MEATER". The original MEATER reported in [#1](https://github.com/Emkraan/homeassistant-meater/issues/1) was already supported.

### Documentation

- README now states explicitly that **MEATER Pro / MEATER 2 Plus are not supported** - they use a different BLE protocol (12-byte temperature payload, different service UUID). Tracked in [#2](https://github.com/Emkraan/homeassistant-meater/issues/2).

## [2026.6.0] - 2026-06-09

### Fixed

- **Ambient temperature reading 1000 °C+** ([#1](https://github.com/Emkraan/homeassistant-meater/issues/1), reported by @dugite-code). The ambient decode was adding a raw-ADC-scale correction term to an already-Celsius tip value and never converting the result back down, so a ~180 °C oven decoded into the thousands. Ambient is now computed entirely on the raw scale from the raw tip value and converted to Celsius once, matching the ESPHome community decode.

### Added

- Out-of-range guard: ambient readings outside −20 °C to 600 °C are treated as corrupt BLE packets and discarded, so the sensor holds its last good value instead of spiking the graph.

## [2026.4.10] - 2026-04-29

### Fixed

- Remove `content_in_root` from `hacs.json` - caused HACS to look for `manifest.json` in the repo root instead of `custom_components/meater_ble/`, breaking installation.

## [2026.4.9] - 2026-04-29

### Added

- HACS one-click install badge in README.
- PR submitted to home-assistant/brands for official icon registration (will enable HACS store icon once merged).

## [2026.4.8] - 2026-04-29

### Fixed

- README header image uses absolute raw.githubusercontent.com URL - fixes broken image in HACS.

## [2026.4.7] - 2026-04-29

### Fixed

- Icon updated to the red MEATER logo mark (wordmark removed) - proper PNG, renders correctly in both HACS and HA.

## [2026.4.6] - 2026-04-29

### Fixed

- README header icon now renders correctly in HACS - switched to `.github/homeassistant-meater.png` relative path, matching the franklinwh pattern.

## [2026.4.5] - 2026-04-29

### Fixed

- Complete rewrite of BLE connectivity. The MEATER+ probe requires an active persistent GATT connection - passive advertisement scanning does not carry any data. The coordinator now maintains a persistent connection with GATT notify callbacks for real-time updates, matching the ESPHome `ble_client` approach. Entities now populate as soon as a connection is established.
- **Important:** The MEATER app and Block must be closed/disconnected before HA can connect - the probe supports only one BLE connection at a time.
- README troubleshooting updated to document the single-connection limitation.

## [2026.4.4] - 2026-04-29

### Fixed

- HACS icon now displays correctly - added `icon` URL field to `hacs.json`.

## [2026.4.3] - 2026-04-29

### Fixed

- Removed startup GATT read. The integration now sets up cleanly regardless of whether the probe is powered on or in range at boot. Entities start as unavailable and populate on the first BLE broadcast - no "Failed setup, will retry" message.

## [2026.4.2] - 2026-04-29

### Added

- GitHub issue templates - structured bug report (probe model, BLE adapter type, distance, logs) and feature request (with BLE vs cloud data distinction), plus `config.yml` disabling blank issues and linking to Discussions and MEATER support.

## [2026.4.1] - 2026-04-29

### Changed

- README rewritten with full entity reference, automation examples, troubleshooting table, and protocol documentation.
- Brand icon added (`custom_components/meater_ble/brand/icon.png`).
- LICENSE file added (MIT).

## [2026.4.0] - 2026-04-28

### Added

- Initial release.
- **Local Bluetooth** - reads MEATER+ tip temperature, ambient temperature, and battery level directly over BLE using Home Assistant's built-in Bluetooth stack. No cloud, no ESP32, no ESPHome required.
- **Passive BLE discovery** - HA automatically detects the MEATER+ probe via its BLE service UUID and presents a config-flow notification.
- **Cook status sensor** - derives `idle`, `cooking`, `approaching_target`, and `resting` states from live temperature data without any cloud connection.
- **HACS-ready** - installable via HACS as a custom integration.

[2026.4.0]: https://github.com/Emkraan/homeassistant-meater/releases/tag/2026.4.0
