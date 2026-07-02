"""Constants for the MEATER BLE integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "meater_ble"
MANUFACTURER = "Apption Labs"
MODEL = "MEATER / MEATER+ / MEATER Pro"

PLATFORMS: list[Platform] = [Platform.SENSOR]

# Bluetooth SIG company identifier assigned to Apption Labs Inc. (maker of MEATER,
# now owned by Traeger) — 0x037B. This is broadcast in the manufacturer-specific data
# (AD type 0xFF) of the PRIMARY advertising packet, so it is present on every advertisement
# HA receives, independent of the scan response. Matching on it is the reliable way to
# auto-discover a MEATER probe through an ESP32/ESPHome proxy, where the local name and
# service UUID (both carried in the scan response) arrive only intermittently (see #3).
MEATER_MANUFACTURER_ID = 891

# BLE service UUID — original MEATER / MEATER+.
MEATER_SERVICE_UUID = "a75cc7fc-c956-488f-ac2a-2dbc08b63a04"

# BLE service UUID — MEATER Pro / MEATER 2 Plus probe (advertises local name "MEATER+"
# on the original Pro firmware, "meater2" on newer MEATER 2 Plus firmware, when removed
# from its charger). Same characteristic UUIDs as the original but delivers a 12-byte
# temperature payload (6 × signed int16 LE) and a 5-byte battery payload.
#
# This UUID *is* broadcast by the probe — the community M5Stack display discovers the
# probe purely by matching it (isAdvertisingService) under an active scan, and @itsaw's
# nRF Connect capture in #2 lists it under the advertisement. The catch (see #3): the
# service UUID and the local name ride in the SCAN RESPONSE, not the primary ADV_IND, and
# they arrive intermittently — an ESP32/ESPHome proxy does not always forward or merge the
# scan response in time for HA's discovery matcher to fire. So auto-discovery via this
# matcher is best-effort; the manual "add device" flow (which forces an active scan and
# lists every BLE advertisement HA has seen) is the reliable path.
MEATER_PRO_SERVICE_UUID = "c9e2746c-59f1-4e54-a0dd-e1e54555cf8b"

# BLE service UUID — MEATER Pro / MEATER 2 Plus *charger/dock*. The dock is a separate,
# always-on advertiser (local name "MEATER2"). It is NOT a valid connection target — its
# GATT tree has no temperature/battery characteristics and connecting returns ATT 0x0e
# (see #2). It is used to identify and *exclude* the dock from both auto-discovery (the
# bluetooth step aborts with reason "dock") and the manual picker (skipped via
# _is_dock_only), so a user is never offered the un-connectable dock. It is deliberately
# NOT a manifest auto-discovery matcher.
MEATER_DOCK_SERVICE_UUID = "dcbb67ca-64fb-41a3-99d1-5d9fd8cf33ca"

# Every MEATER-family service UUID that may appear in an advertisement, normalized to
# lower case so comparison against BluetoothServiceInfoBleak.service_uuids (also lower
# case) is case-insensitive regardless of how the source constants are written.
KNOWN_MEATER_SERVICE_UUIDS = frozenset(
    uuid.lower()
    for uuid in (
        MEATER_SERVICE_UUID,
        MEATER_PRO_SERVICE_UUID,
        MEATER_DOCK_SERVICE_UUID,
    )
)

# GATT characteristic: 6 bytes — tip(2) + raw_ambient(2) + offset_ambient(2).
CHAR_TEMPERATURE = "7edda774-045e-4bbf-909b-45d1991a2876"

# GATT characteristic: 2 bytes — little-endian uint16 battery value.
CHAR_BATTERY = "2adb4877-68d8-4884-bd3c-d83853bf27b8"

# Ambient decode constants (from ESPHome community reverse-engineering).
AMBIENT_MIN_OFFSET = 48

# Plausible ambient range (°C). Readings outside this are corrupt BLE packets
# and are discarded so a single bad packet cannot spike the sensor graph.
# Ceiling sits well above the rated ~275 °C to allow high-heat grilling/searing.
AMBIENT_TEMP_MIN_C = -20.0
AMBIENT_TEMP_MAX_C = 600.0

# Cook-status temperature threshold (°C).
COOK_REST_DELTA = 2.0  # tip drops this many degrees from peak → resting
