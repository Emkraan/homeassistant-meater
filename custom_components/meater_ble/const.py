"""Constants for the MEATER BLE integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "meater_ble"
MANUFACTURER = "Apption Labs"
MODEL = "MEATER+"

PLATFORMS: list[Platform] = [Platform.SENSOR]

# BLE service UUID that identifies a MEATER+ probe advertisement.
MEATER_SERVICE_UUID = "a75cc7fc-c956-488f-ac2a-2dbc08b63a04"

# GATT characteristic: 6 bytes — tip(2) + raw_ambient(2) + offset_ambient(2).
CHAR_TEMPERATURE = "7edda774-045e-4bbf-909b-45d1991a2876"

# GATT characteristic: 2 bytes — little-endian uint16 battery value.
CHAR_BATTERY = "2adb4877-68d8-4884-bd3c-d83853bf27b8"

# Ambient decode constants (from ESPHome community reverse-engineering).
AMBIENT_MIN_OFFSET = 48

# Cook-status temperature thresholds (°C).
COOK_APPROACHING_DELTA = 10.0   # degrees below target to enter "approaching"
COOK_REST_DELTA = 2.0           # tip drops this many degrees from peak → resting
