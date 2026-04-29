# Changelog

All notable changes to this integration are documented here.

## [2026.4.8] — 2026-04-29

### Fixed

- README header image uses absolute raw.githubusercontent.com URL — fixes broken image in HACS.

## [2026.4.7] — 2026-04-29

### Fixed

- Icon updated to the red MEATER logo mark (wordmark removed) — proper PNG, renders correctly in both HACS and HA.

## [2026.4.6] — 2026-04-29

### Fixed

- README header icon now renders correctly in HACS — switched to `.github/homeassistant-meater.png` relative path, matching the franklinwh pattern.

## [2026.4.5] — 2026-04-29

### Fixed

- Complete rewrite of BLE connectivity. The MEATER+ probe requires an active persistent GATT connection — passive advertisement scanning does not carry any data. The coordinator now maintains a persistent connection with GATT notify callbacks for real-time updates, matching the ESPHome `ble_client` approach. Entities now populate as soon as a connection is established.
- **Important:** The MEATER app and Block must be closed/disconnected before HA can connect — the probe supports only one BLE connection at a time.
- README troubleshooting updated to document the single-connection limitation.

## [2026.4.4] — 2026-04-29

### Fixed

- HACS icon now displays correctly — added `icon` URL field to `hacs.json`.

## [2026.4.3] — 2026-04-29

### Fixed

- Removed startup GATT read. The integration now sets up cleanly regardless of whether the probe is powered on or in range at boot. Entities start as unavailable and populate on the first BLE broadcast — no "Failed setup, will retry" message.

## [2026.4.2] — 2026-04-29

### Added

- GitHub issue templates — structured bug report (probe model, BLE adapter type, distance, logs) and feature request (with BLE vs cloud data distinction), plus `config.yml` disabling blank issues and linking to Discussions and MEATER support.

## [2026.4.1] — 2026-04-29

### Changed

- README rewritten with full entity reference, automation examples, troubleshooting table, and protocol documentation.
- Brand icon added (`custom_components/meater_ble/brand/icon.png`).
- LICENSE file added (MIT).

## [2026.4.0] — 2026-04-28

### Added

- Initial release.
- **Local Bluetooth** — reads MEATER+ tip temperature, ambient temperature, and battery level directly over BLE using Home Assistant's built-in Bluetooth stack. No cloud, no ESP32, no ESPHome required.
- **Passive BLE discovery** — HA automatically detects the MEATER+ probe via its BLE service UUID and presents a config-flow notification.
- **Cook status sensor** — derives `idle`, `cooking`, `approaching_target`, and `resting` states from live temperature data without any cloud connection.
- **HACS-ready** — installable via HACS as a custom integration.

[2026.4.0]: https://github.com/Emkraan/homeassistant-meater/releases/tag/2026.4.0
