"""DataUpdateCoordinator for the MEATER BLE integration.

Reads tip temperature, ambient temperature, and battery level from a MEATER+
probe via GATT over Home Assistant's native Bluetooth stack. No cloud, no
ESPHome relay required.

Decode formulas are derived from the open ESPHome community config at
https://github.com/R00S/meater-in-local-haos (meater.yaml).
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from bleak import BleakClient
from bleak.exc import BleakError

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    AMBIENT_MIN_OFFSET,
    CHAR_BATTERY,
    CHAR_TEMPERATURE,
    COOK_APPROACHING_DELTA,
    COOK_REST_DELTA,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class MeaterData:
    """Snapshot of a single MEATER+ poll."""

    tip_temp: float | None
    ambient_temp: float | None
    battery: int | None
    cook_state: str  # idle | cooking | approaching_target | resting


def _decode_tip(data: bytes) -> float:
    """Decode tip temperature (°C) from the 6-byte temperature characteristic."""
    raw = data[0] + (data[1] << 8)
    return (raw + 8.0) / 16.0


def _decode_ambient(data: bytes, tip: float) -> float:
    """Decode ambient temperature (°C) from the 6-byte temperature characteristic."""
    ra = data[2] + (data[3] << 8)
    oa = data[4] + (data[5] << 8)
    correction = max(0.0, ((ra - min(AMBIENT_MIN_OFFSET, oa)) * 16 * 589) / 1487)
    return tip + correction + 8.0 / 16.0


def _decode_battery(data: bytes) -> int:
    """Decode battery percentage from the 2-byte battery characteristic."""
    raw = data[0] + (data[1] << 8)
    return min(100, raw * 10)


def _derive_cook_state(
    tip: float | None,
    prev: MeaterData | None,
) -> str:
    """Derive a simple cook state from temperature without cloud data."""
    if tip is None:
        return "idle"
    # Below 30 °C the probe is almost certainly not inserted in food.
    if tip < 30.0:
        return "idle"
    # If the tip is dropping from a previous peak, call it resting.
    if prev is not None and prev.tip_temp is not None:
        if prev.cook_state in ("cooking", "approaching_target"):
            if tip < prev.tip_temp - COOK_REST_DELTA:
                return "resting"
    # Treat a sustained temp above 30 °C as cooking; the approaching_target
    # threshold is only useful when a target is known (cloud supplement), so
    # we omit it here to avoid false positives.
    return "cooking"


class MeaterBLECoordinator(DataUpdateCoordinator[MeaterData]):
    """Coordinator that reads a MEATER+ probe on demand via GATT."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{address}",
        )
        self.address = address
        self._last_good: MeaterData | None = None

    async def _async_update_data(self) -> MeaterData:
        """Connect via GATT, read characteristics, decode, disconnect."""
        ble_device = async_ble_device_from_address(self.hass, self.address, connectable=True)
        if ble_device is None:
            if self._last_good is not None:
                _LOGGER.debug("MEATER %s not in range; reusing last data", self.address)
                return self._last_good
            raise UpdateFailed(f"MEATER {self.address} not reachable")

        try:
            async with BleakClient(ble_device) as client:
                temp_raw = await client.read_gatt_char(CHAR_TEMPERATURE)
                batt_raw = await client.read_gatt_char(CHAR_BATTERY)
        except BleakError as err:
            if self._last_good is not None:
                _LOGGER.warning("MEATER %s GATT read failed (%s); reusing last data", self.address, err)
                return self._last_good
            raise UpdateFailed(f"GATT read failed: {err}") from err

        tip = _decode_tip(temp_raw)
        ambient = _decode_ambient(temp_raw, tip)
        battery = _decode_battery(batt_raw)
        cook_state = _derive_cook_state(tip, self._last_good)

        data = MeaterData(
            tip_temp=tip,
            ambient_temp=ambient,
            battery=battery,
            cook_state=cook_state,
        )
        self._last_good = data
        return data

    @callback
    def async_handle_bluetooth_event(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Trigger a coordinator refresh when the probe is seen in a BLE scan."""
        self.hass.async_create_task(self.async_request_refresh())
