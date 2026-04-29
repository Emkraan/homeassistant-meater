# Changelog

All notable changes to this integration are documented here.

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
