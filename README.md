<p align="center">
  <img src="https://raw.githubusercontent.com/Emkraan/homeassistant-meater/main/.github/homeassistant-meater.png" alt="MEATER BLE" width="120" />
</p>

<h1 align="center">MEATER BLE - Home Assistant Integration</h1>

<p align="center">
  Local Bluetooth integration for MEATER and MEATER+ wireless meat thermometer probes.<br>
  No cloud. No ESP32. No ESPHome. Just HA and your probe.
</p>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-blue.svg?style=for-the-badge" alt="HACS Custom"></a>
  <a href="https://github.com/Emkraan/homeassistant-meater/releases"><img src="https://img.shields.io/github/v/release/Emkraan/homeassistant-meater?style=for-the-badge" alt="Latest release"></a>
  <a href="https://www.home-assistant.io/"><img src="https://img.shields.io/badge/Home%20Assistant-2023.12%2B-41BDF5?style=for-the-badge&logo=home-assistant&logoColor=white" alt="HA 2023.12+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License"></a>
</p>

<div align="center">

⚠️ 🚨 **This is an unofficial integration and is not affiliated with or endorsed by Apption Labs or MEATER.** 🚨 ⚠️

</div>

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

- **Fully local** - communicates directly with the MEATER / MEATER+ probe over Bluetooth. No MEATER cloud account or internet connection required.
- **Auto-discovery** - Home Assistant detects the probe automatically via its BLE service UUID and presents a one-click setup notification.
- **Real-time updates** - passive BLE scan triggers a coordinator refresh whenever the probe broadcasts, rather than waiting for a fixed poll interval.
- **No extra hardware** - works with any Bluetooth adapter visible to HA (built-in, USB dongle, or an [ESP32 Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html)).
- **Self-healing** - if the probe goes out of range, the last known values are retained and HA retries automatically on the next broadcast.
- **Structured cook status** - derives a cook state from live temperature without any cloud dependency.

---

## Requirements

| Requirement | Details |
|---|---|
| Home Assistant | **2023.12** or newer |
| Bluetooth | Any adapter accessible to HA - built-in, USB, or ESP32 Bluetooth proxy |
| Hardware | Original **MEATER**, **MEATER+**, **MEATER Pro**, or **MEATER 2 Plus** probe. |

---

## Installation

### Via HACS (recommended)

Click the badge below to open HACS and add this repository in one step:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Emkraan&repository=homeassistant-meater&category=integration)

Or manually:

1. Open **HACS → Integrations**.
2. Click the menu (⋮) → **Custom repositories**.
3. Add `https://github.com/Emkraan/homeassistant-meater` - category: **Integration**.
4. Search for **MEATER BLE** and click **Download**.
5. Restart Home Assistant.

### Manual

1. Download the [latest release](https://github.com/Emkraan/homeassistant-meater/releases/latest).
2. Copy the `custom_components/meater_ble/` folder into `<config>/custom_components/`.
3. Restart Home Assistant.

---

## Configuration

Turn on your MEATER probe and bring it within Bluetooth range of your HA host. Within a few seconds, a notification will appear under **Settings → Devices & Services**:

> *New device discovered: MEATER …*

Click **Configure** → **Submit** to add it. No credentials needed.

**Don't see the notification?** Some probes (notably the MEATER Pro / MEATER 2 Plus) only broadcast their name and service UUID intermittently, and a Bluetooth proxy may not forward that part of the advertisement - so auto-discovery can be hit-or-miss. Add the probe manually instead: **Settings → Devices & Services → + Add Integration → MEATER BLE**. Take the probe out of its charger first; then pick it from the list. If it isn't listed by name, it will still appear by its MAC address.

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
| Cook Status | Current cook state (see below) | - | `enum` |
| Signal Strength | RSSI of the probe's last-seen advertisement (diagnostic, disabled by default). Freezes while connected - the probe does not advertise then - so it reflects signal quality just before connecting or since the last drop, not a live connection signal. | dBm | `signal_strength` |

### Cook Status States

| State | Meaning |
|---|---|
| `idle` | Probe is not inserted - tip temp below 30 °C |
| `cooking` | Probe is in food and temperature is rising |
| `approaching_target` | Tip is within target range (requires cloud supplement) |
| `resting` | Tip temperature has dropped from its peak - meat is resting |

---

## Automations

### Notify when meat is done resting

```yaml
automation:
  - alias: "MEATER - Notify when resting complete"
    trigger:
      - platform: state
        entity_id: sensor.meater_cook_status
        from: resting
        to: idle
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "MEATER"
          message: "Your meat has finished resting - time to slice!"
```

### Alert if probe gets too hot

```yaml
automation:
  - alias: "MEATER - High ambient temperature alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.meater_ambient_temperature
        above: 300
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "MEATER - High Grill Temp"
          message: "Ambient temperature is above 300 °C - check your grill."
```

### Low battery warning

```yaml
automation:
  - alias: "MEATER - Low battery"
    trigger:
      - platform: numeric_state
        entity_id: sensor.meater_battery
        below: 20
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "MEATER"
          message: "Probe battery is below 20% - charge soon."
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Entities stuck "unavailable" | MEATER app or Block is connected | **Close the MEATER app and disconnect the Block** - the probe only allows one BLE connection at a time |
| Entities stuck "unavailable" | Probe out of range or off | Turn probe on, bring within 10 m of HA Bluetooth adapter; integration retries automatically |
| Connects, then drops after a minute or two (esp. via a Bluetooth proxy) | The connectable adapter/proxy hears the probe too weakly to hold the connection | Move a **connectable** ESP32/ESPHome Bluetooth proxy closer to the probe. A passive scanner (e.g. Shelly) can relay advertisements but cannot hold the connection a MEATER needs |
| Drops and does not come back, even though the probe is right next to a proxy | The proxy is holding a **wedged/half-open connection slot** to the probe (a known ESPHome issue), so the probe never re-advertises for a reconnect | Update ESPHome on the proxy (a slot leak was fixed in ESPHome 2026.5.1) and reboot it; keep a **connectable** proxy close enough to hold a strong link. A probe buried in a metal grill/smoker heavily attenuates BLE |
| No discovery notification on first setup | Probe not yet seen by HA BLE scanner | Turn probe on, wait ~30 seconds, check Settings → Devices & Services |
| No discovery notification (MEATER Pro / 2 Plus, esp. via a Bluetooth proxy) | Probe advertises its name/service UUID only in the scan response, which the proxy may drop | Add it manually: **+ Add Integration → MEATER BLE** and pick the probe (out of the charger) from the list |
| Ambient temp reads very high | Probe too close to heat source | Normal behavior; the MEATER ambient sensor reads radiant heat, not air temp |
| Battery reads 0% | Probe fully discharged | Charge in the block for 2+ hours |

Enable debug logging with:

```yaml
logger:
  logs:
    custom_components.meater_ble: debug
```

---

## How It Works

The probe continuously broadcasts BLE advertisements. Auto-discovery matches on the **Apption Labs manufacturer ID** (`0x037B` / 891), which every MEATER puts in the primary advertising packet, so it works even through a Bluetooth proxy (the local name and service UUID ride in the scan response, which proxies do not reliably forward).

Temperature and battery are not in the advertisement, so the integration holds a **persistent GATT connection** to the probe. It receives updates via GATT notify and also **reads the probe on a short timer**, which is a reliable data path for probes that are read-populated rather than push-driven and doubles as a liveness heartbeat. Reconnection is self-healing: it listens for advertisements from any scanner (so a probe seen by a passive proxy still triggers a reconnect) and keeps retrying on a backoff timer until a connectable path is available, and it keeps the last reading for a short grace window across brief drops. If the link goes silent while nominally connected (a half-open drop, common through Bluetooth proxies), a **liveness watchdog** tears it down and reconnects rather than leaving the entities frozen on a stale reading. The connection reads two characteristics:

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
