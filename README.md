# MEATER BLE — Home Assistant Integration

Local Bluetooth integration for **MEATER+** wireless meat thermometer probes. Reads temperature and battery data directly over BLE using Home Assistant's built-in Bluetooth stack — no cloud account, no ESP32, no ESPHome required.

---

## Features

- **Fully local** — no MEATER cloud account or internet connection needed
- **Real-time** — BLE passive scan; updates as soon as the probe broadcasts
- **Auto-discovery** — HA detects the probe automatically and prompts to configure
- **4 entities per probe:**
  - Tip temperature (°C)
  - Ambient temperature (°C)
  - Battery level (%)
  - Cook status (`idle` / `cooking` / `approaching_target` / `resting`)

---

## Requirements

- Home Assistant **2023.12** or newer
- A Bluetooth adapter accessible to HA (built-in, USB dongle, or Bluetooth proxy)
- **MEATER+** probe (MEATER 2 Plus may also work — not yet confirmed)

---

## Installation

### Via HACS (recommended)

1. Open HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/Emkraan/homeassistant-meater` as an **Integration**
3. Search for **MEATER BLE** and install
4. Restart Home Assistant

### Manual

Copy `custom_components/meater_ble/` into your HA `config/custom_components/` directory and restart.

---

## Setup

Turn on your MEATER+ probe and bring it within Bluetooth range. HA will discover it automatically and show a notification under **Settings → Devices & Services**. Click **Configure** to add it.

---

## How It Works

The MEATER+ probe broadcasts BLE advertisements containing raw temperature and battery bytes. This integration registers a passive BLE listener for the MEATER service UUID (`a75cc7fc-c956-488f-ac2a-2dbc08b63a04`). When the probe is detected, it connects briefly via GATT to read:

- **Characteristic** `7edda774-045e-4bbf-909b-45d1991a2876` — 6 bytes encoding tip temp, raw ambient, and ambient offset
- **Characteristic** `2adb4877-68d8-4884-bd3c-d83853bf27b8` — 2 bytes encoding battery level

Temperature decode formulas are derived from the open ESPHome community config at [R00S/meater-in-local-haos](https://github.com/R00S/meater-in-local-haos).

---

## Credits

BLE protocol reverse-engineering credit to the ESPHome community and [R00S/meater-in-local-haos](https://github.com/R00S/meater-in-local-haos).
