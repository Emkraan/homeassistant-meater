<p align="center">
  <img src="https://raw.githubusercontent.com/Emkraan/homeassistant-meater/main/custom_components/meater_ble/brand/icon.png" alt="MEATER BLE" width="120" />
</p>

<h1 align="center">MEATER BLE — Home Assistant Integration</h1>

<p align="center">
  Local Bluetooth integration for MEATER+ wireless meat thermometer probes.<br>
  No cloud. No ESP32. No ESPHome. Just HA and your probe.
</p>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-blue.svg?style=for-the-badge" alt="HACS Custom"></a>
  <a href="https://github.com/Emkraan/homeassistant-meater/releases"><img src="https://img.shields.io/github/v/release/Emkraan/homeassistant-meater?style=for-the-badge" alt="Latest release"></a>
  <a href="https://www.home-assistant.io/"><img src="https://img.shields.io/badge/Home%20Assistant-2023.12%2B-41BDF5?style=for-the-badge&logo=home-assistant&logoColor=white" alt="HA 2023.12+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License"></a>
</p>

> ⚠️ This is an unofficial integration and is not affiliated with Apption Labs or MEATER.

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
- [Automations](#automations)
- [Troubleshooting](#troubleshooting)
- [How It Works](#how-it-works)
- [License](#license)

---

## Features

- **Fully local** — communicates directly with the MEATER+ probe over Bluetooth. No MEATER cloud account or internet connection required.
- **Auto-discovery** — Home Assistant detects the probe automatically via its BLE service UUID and presents a one-click setup notification.
- **Real-time updates** — passive BLE scan triggers a coordinator refresh whenever the probe broadcasts, rather than waiting for a fixed poll interval.
- **No extra hardware** — works with any Bluetooth adapter visible to HA (built-in, USB dongle, or an [ESP32 Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html)).
- **Self-healing** — if the probe goes out of range, the last known values are retained and HA retries automatically on the next broadcast.
- **Structured cook status** — derives a cook state from live temperature without any cloud dependency.

---

## Requirements

| Requirement | Details |
|---|---|
| Home Assistant | **2023.12** or newer |
| Bluetooth | Any adapter accessible to HA — built-in, USB, or ESP32 Bluetooth proxy |
| Hardware | **MEATER+** probe (MEATER 2 Plus may work — not yet confirmed) |

---

## Installation

### Via HACS (recommended)

1. Open **HACS → Integrations**.
2. Click the menu (⋮) → **Custom repositories**.
3. Add `https://github.com/Emkraan/homeassistant-meater` — category: **Integration**.
4. Search for **MEATER BLE** and click **Download**.
5. Restart Home Assistant.

### Manual

1. Download the [latest release](https://github.com/Emkraan/homeassistant-meater/releases/latest).
2. Copy the `custom_components/meater_ble/` folder into `<config>/custom_components/`.
3. Restart Home Assistant.

---

## Configuration

Turn on your MEATER+ probe and bring it within Bluetooth range of your HA host. Within a few seconds, a notification will appear under **Settings → Devices & Services**:

> *New device discovered: MEATER …*

Click **Configure** → **Submit** to add it. No credentials needed.

Each probe becomes its own device in HA, identified by its Bluetooth MAC address.

---

## Entities

All entities are grouped under one device per probe.

### Sensors

| Entity | Description | Unit | Device class |
|---|---|---|---|
| Tip Temperature | Current internal meat temperature | °C | `temperature` |
| Ambient Temperature | Surrounding grill/oven temperature | °C | `temperature` |
| Battery | Probe battery level | % | `battery` |
| Cook Status | Current cook state (see below) | — | `enum` |

### Cook Status States

| State | Meaning |
|---|---|
| `idle` | Probe is not inserted — tip temp below 30 °C |
| `cooking` | Probe is in food and temperature is rising |
| `approaching_target` | Tip is within target range (requires cloud supplement) |
| `resting` | Tip temperature has dropped from its peak — meat is resting |

---

## Automations

### Notify when meat is done resting

```yaml
automation:
  - alias: "MEATER — Notify when resting complete"
    trigger:
      - platform: state
        entity_id: sensor.meater_cook_status
        from: resting
        to: idle
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "MEATER"
          message: "Your meat has finished resting — time to slice!"
```

### Alert if probe gets too hot

```yaml
automation:
  - alias: "MEATER — High ambient temperature alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.meater_ambient_temperature
        above: 300
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "MEATER — High Grill Temp"
          message: "Ambient temperature is above 300 °C — check your grill."
```

### Low battery warning

```yaml
automation:
  - alias: "MEATER — Low battery"
    trigger:
      - platform: numeric_state
        entity_id: sensor.meater_battery
        below: 20
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "MEATER"
          message: "Probe battery is below 20% — charge soon."
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Entities stuck "unavailable" | MEATER app or Block is connected | **Close the MEATER app and disconnect the Block** — the probe only allows one BLE connection at a time |
| Entities stuck "unavailable" | Probe out of range or off | Turn probe on, bring within 10 m of HA Bluetooth adapter; integration retries automatically |
| No discovery notification on first setup | Probe not yet seen by HA BLE scanner | Turn probe on, wait ~30 seconds, check Settings → Devices & Services |
| Ambient temp reads very high | Probe too close to heat source | Normal behavior; MEATER+ ambient sensor reads radiant heat, not air temp |
| Battery reads 0% | Probe fully discharged | Charge in the block for 2+ hours |

Enable debug logging with:

```yaml
logger:
  logs:
    custom_components.meater_ble: debug
```

---

## How It Works

The MEATER+ probe continuously broadcasts BLE advertisements. This integration registers a **passive BLE listener** for the MEATER service UUID (`a75cc7fc-c956-488f-ac2a-2dbc08b63a04`) using HA's native Bluetooth stack. When the probe is detected, it connects briefly via GATT to read two characteristics:

| Characteristic UUID | Content |
|---|---|
| `7edda774-045e-4bbf-909b-45d1991a2876` | 6 bytes: tip temp (2) + raw ambient (2) + ambient offset (2) |
| `2adb4877-68d8-4884-bd3c-d83853bf27b8` | 2 bytes: battery level |

**Tip temperature (°C):**
```
(byte[0] + (byte[1] << 8) + 8) / 16
```

**Ambient temperature (°C):**
```
tip + max(0, ((ra - min(48, oa)) × 16 × 589) / 1487) + 0.5
```
where `ra = byte[2] + (byte[3] << 8)`, `oa = byte[4] + (byte[5] << 8)`

**Battery (%):**
```
(byte[0] + (byte[1] << 8)) × 10
```

Decode formulas are derived from the open ESPHome community config at [R00S/meater-in-local-haos](https://github.com/R00S/meater-in-local-haos).

---

## License

Licensed under the MIT License. See [LICENSE](LICENSE) for details.
