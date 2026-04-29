"""DataUpdateCoordinator for the MEATER BLE integration.

The MEATER+ probe exposes temperature and battery data exclusively via GATT —
there is nothing in the advertisement payload. It supports only one concurrent
BLE connection, so the MEATER app or Block must be closed before HA can connect.

This coordinator maintains a persistent BLE connection and uses GATT notify
to receive characteristic updates in real time, mirroring the ESPHome ble_client
approach documented at https://github.com/R00S/meater-in-local-haos.

Decode formulas derived from the same ESPHome community config.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    AMBIENT_MIN_OFFSET,
    CHAR_BATTERY,
    CHAR_TEMPERATURE,
    COOK_REST_DELTA,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# How long to wait for a GATT connection before giving up on this attempt.
_CONNECT_TIMEOUT = 20.0
# How long to wait between reconnect attempts when the probe drops.
_RECONNECT_DELAY = 10.0


@dataclass
class MeaterData:
    """Snapshot of decoded MEATER+ probe data."""

    tip_temp: float | None
    ambient_temp: float | None
    battery: int | None
    cook_state: str  # idle | cooking | resting


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


def _derive_cook_state(tip: float, prev_state: str, prev_tip: float | None) -> str:
    """Derive cook state from tip temperature."""
    if tip < 30.0:
        return "idle"
    if prev_state in ("cooking",) and prev_tip is not None:
        if tip < prev_tip - COOK_REST_DELTA:
            return "resting"
    return "cooking"


class MeaterBLECoordinator(DataUpdateCoordinator[MeaterData]):
    """Maintains a persistent GATT connection to a MEATER+ probe."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{address}",
        )
        self.address = address
        self._client: BleakClient | None = None
        self._keep_running = True
        self._connection_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the persistent connection loop as a background task."""
        self._keep_running = True
        self._connection_task = self.hass.async_create_background_task(
            self._connection_loop(),
            name=f"meater_ble:{self.address}",
        )

    async def stop(self) -> None:
        """Stop the connection loop and disconnect cleanly."""
        self._keep_running = False
        if self._connection_task:
            self._connection_task.cancel()
            try:
                await self._connection_task
            except asyncio.CancelledError:
                pass
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except BleakError:
                pass

    # ------------------------------------------------------------------
    # Internal — connection loop
    # ------------------------------------------------------------------

    async def _connection_loop(self) -> None:
        """Maintain a persistent connection; reconnect on drop."""
        while self._keep_running:
            ble_device = async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                _LOGGER.debug(
                    "MEATER %s not visible yet — waiting %ss before retry",
                    self.address, _RECONNECT_DELAY,
                )
                await asyncio.sleep(_RECONNECT_DELAY)
                continue

            _LOGGER.debug("Connecting to MEATER %s", self.address)
            try:
                async with BleakClient(
                    ble_device,
                    timeout=_CONNECT_TIMEOUT,
                    disconnected_callback=self._on_disconnect,
                ) as client:
                    self._client = client
                    _LOGGER.info("Connected to MEATER %s", self.address)

                    await client.start_notify(CHAR_TEMPERATURE, self._on_temp_notify)
                    await client.start_notify(CHAR_BATTERY, self._on_batt_notify)

                    # Do an immediate read so entities populate right away.
                    temp_raw = await client.read_gatt_char(CHAR_TEMPERATURE)
                    batt_raw = await client.read_gatt_char(CHAR_BATTERY)
                    self._process(temp_raw, batt_raw)

                    # Hold the connection open; notify callbacks handle updates.
                    while client.is_connected and self._keep_running:
                        await asyncio.sleep(1.0)

            except (BleakError, asyncio.TimeoutError) as err:
                _LOGGER.warning(
                    "MEATER %s connection error (%s) — retrying in %ss",
                    self.address, err, _RECONNECT_DELAY,
                )
            finally:
                self._client = None

            if self._keep_running:
                await asyncio.sleep(_RECONNECT_DELAY)

    def _on_disconnect(self, client: BleakClient) -> None:
        """Called by Bleak when the probe drops the connection."""
        _LOGGER.debug("MEATER %s disconnected", self.address)

    # ------------------------------------------------------------------
    # Notify callbacks
    # ------------------------------------------------------------------

    @callback
    def _on_temp_notify(
        self, characteristic: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Handle a temperature characteristic notification."""
        batt_raw = None
        if self._client and self._client.is_connected:
            # Battery rarely changes — use last known value if available.
            if self.data is not None and self.data.battery is not None:
                self._process(bytes(data), None)
                return
        self._process(bytes(data), batt_raw)

    @callback
    def _on_batt_notify(
        self, characteristic: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Handle a battery characteristic notification."""
        if self.data is None:
            return
        battery = _decode_battery(bytes(data))
        updated = MeaterData(
            tip_temp=self.data.tip_temp,
            ambient_temp=self.data.ambient_temp,
            battery=battery,
            cook_state=self.data.cook_state,
        )
        self.async_set_updated_data(updated)

    def _process(self, temp_raw: bytes, batt_raw: bytes | None) -> None:
        """Decode raw bytes and push an update to all listeners."""
        tip = _decode_tip(temp_raw)
        ambient = _decode_ambient(temp_raw, tip)
        battery = (
            _decode_battery(batt_raw)
            if batt_raw is not None
            else (self.data.battery if self.data else None)
        )
        prev_state = self.data.cook_state if self.data else "idle"
        prev_tip = self.data.tip_temp if self.data else None
        cook_state = _derive_cook_state(tip, prev_state, prev_tip)

        self.async_set_updated_data(
            MeaterData(
                tip_temp=tip,
                ambient_temp=ambient,
                battery=battery,
                cook_state=cook_state,
            )
        )

    # ------------------------------------------------------------------
    # DataUpdateCoordinator override — not used for polling, but required.
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> MeaterData:
        """Not used — data arrives via notify callbacks."""
        if self.data is not None:
            return self.data
        raise UpdateFailed("No data yet — waiting for GATT connection")
