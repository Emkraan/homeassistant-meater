"""DataUpdateCoordinator for the MEATER BLE integration.

The original MEATER and MEATER+ probes expose temperature and battery data
exclusively via GATT - there is nothing useful in the advertisement payload. They
support only one concurrent BLE connection, so the MEATER app or Block must be
closed before HA can connect.

This coordinator maintains a persistent GATT connection. Connections go through
bleak_retry_connector.establish_connection (the same helper HA's own BLE
integrations use), which transparently handles ESP32/ESPHome proxies, stale
BLEDevice handles, and transient connection errors with retry + backoff.

Data flows two ways, so the integration works across the whole MEATER family and
survives a half-open link:

* GATT notify. The MEATER 2 Plus / Pro push temperature automatically after
  subscribing, so notifications give low-latency updates when they arrive.
* An active read poll. The coordinator also reads the temperature (and, less often,
  battery) characteristic on a timer. This is the reliable data path for probes that
  are read-populated rather than notify-driven (the original MEATER/MEATER+ appear to
  be), and it doubles as a liveness probe: a read that fails or hangs is a definitive
  sign of a dead link. If neither notify nor a successful read produces data within a
  stall window, the link is treated as half-open (a common ESP32/ESPHome-proxy failure
  where the GATT layer dies but the proxy keeps the connection slot) and the connection
  is torn down and re-established. A passive notify-silence timer alone cannot catch
  this, because a half-open drop often fires no Bleak disconnect callback at all.

Reconnection is both event-driven and self-scheduling. A bluetooth advertisement
callback fires whenever the probe is seen in range by ANY scanner - connectable or
not - and a self-rescheduling backoff loop keeps retrying while disconnected even
when no connectable adapter has a fresh view of the probe yet. This matters through
Bluetooth proxies: a probe is often heard continuously by a passive (non-connectable)
scanner while the only connectable proxy hears it weakly and intermittently (see #3),
so recovery must not depend on a connectable advertisement alone. A short availability
grace window keeps the last reading visible across brief drops instead of flapping
every entity to unavailable while a reconnect is in flight.

Note: when a probe stops advertising entirely because a Bluetooth proxy is holding a
leaked/half-open connection slot to it, no HA-side API can force a remote proxy to
release that slot (bleak_retry_connector's stale-connection helpers are BlueZ-local
and proxy-blind). The coordinator surfaces this with an actionable warning after
sustained failure to find any connectable path; the fix there is proxy-side (update
ESPHome firmware, move a connectable proxy closer, or reboot the proxy).

Decode formulas derived from ESPHome/community reverse-engineering.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import timedelta
import logging
import struct

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    AMBIENT_MIN_OFFSET,
    AMBIENT_TEMP_MAX_C,
    AMBIENT_TEMP_MIN_C,
    CHAR_BATTERY,
    CHAR_TEMPERATURE,
    COOK_REST_DELTA,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Number of connection attempts establish_connection makes per reconnect, each with
# its own backoff. It re-fetches a fresh BLEDevice between attempts.
_MAX_CONNECT_ATTEMPTS = 4

# Base gap between reconnection attempts after a drop or a failed attempt. Stops a
# probe that accepts then instantly drops the connection (single-connection contention
# with the MEATER app/Block) from thrashing the adapter.
_RECONNECT_COOLDOWN = 5.0

# Ceiling for the reconnection backoff. Each consecutive failed attempt doubles the
# gap up to this cap, so a probe that is genuinely gone (asleep, out of range, or in
# its charger) is retried gently instead of hammered.
_RECONNECT_COOLDOWN_MAX = 30.0

# How long entities keep serving their last reading after an unexpected drop while a
# reconnect is attempted. A weak proxy link blips routinely; without this window every
# blip would flap the entities to unavailable. If recovery does not happen within it,
# the entities go unavailable (the probe really is gone). The window is measured from
# the FIRST drop and is not re-armed by subsequent blips, so a probe that keeps
# flapping without ever reconnecting cannot serve a stale reading indefinitely.
_AVAILABILITY_GRACE = 90.0

# How often to actively read the temperature characteristic. This is the reliable data
# path for read-populated probes and the heartbeat that detects a dead link. Kept
# deliberately gentle: every read is an over-the-air request/response round trip through
# the proxy, and on a weak link (a probe buried in a metal grill/smoker) frequent GATT
# reads add congestion that can itself provoke a supervision-timeout drop. BLE best
# practice is to prefer notifications and poll sparingly in a noisy 2.4 GHz environment,
# so this is a slow heartbeat, not a fast poll: the MEATER 2 Plus / Pro stream via notify
# anyway, and a 20 s cadence is plenty for a cook.
_READ_POLL_INTERVAL = 20.0

# Read the battery characteristic once every N poll ticks (~60 s). Battery changes slowly,
# so there is no reason to read it as often as temperature.
_BATTERY_POLL_EVERY = 3

# Per-read ceiling. A healthy read through a proxy completes in well under a second; a
# half-open link makes the read hang, so it must be bounded or the poll loop wedges.
_READ_TIMEOUT = 10.0

# If neither a notification nor a successful read produces data within this window while
# nominally connected, the link is half-open (the GATT layer is dead but no disconnect
# callback fired). Tear it down and reconnect. Sized above the read cadence plus a
# hung-read timeout (20 s + 10 s) with margin so normal jitter never trips it, and below
# the grace window so a forced reconnect still has time to recover before entities flap
# to unavailable.
_STALL_TIMEOUT = 45.0

# Ceiling on how long to wait for a deliberate disconnect to complete. A half-open link
# can make client.disconnect() hang, so recovery must not block on it.
_DISCONNECT_TIMEOUT = 10.0

# A gap this long since the previous advertisement means the probe genuinely reappeared
# (e.g. taken out of its charger) rather than the rapid advertisement stream of a probe
# we keep failing to hold. Only then is the reconnect backoff reset, so app/Block
# contention still escalates the backoff instead of pinning it at the floor.
_ADVERT_SILENCE_RESET = 60.0

# Number of consecutive reconnect attempts with no connectable path before warning the
# user. With the backoff capped at 30 s this is a few minutes of a probe that is heard
# (or not) but never has a connectable route - the signature of a wedged proxy slot or a
# signal too weak to hold a link.
_NO_PATH_WARN_AFTER = 8


@dataclass
class MeaterData:
    """Snapshot of decoded MEATER / MEATER+ probe data."""

    tip_temp: float | None
    ambient_temp: float | None
    battery: int | None
    cook_state: str  # idle | cooking | resting


def _decode_tip(data: bytes) -> float:
    """Decode tip temperature (°C) from the 6-byte temperature characteristic."""
    raw = data[0] + (data[1] << 8)
    return (raw + 8.0) / 16.0


def _decode_ambient(data: bytes) -> float:
    """Decode ambient temperature (°C) from the 6-byte temperature characteristic.

    The ambient correction is computed on the raw ADC scale using the raw tip
    value, then the whole result is converted to Celsius once via (x + 8) / 16 -
    matching the ESPHome community decode. Feeding it the already-converted tip
    (and skipping the final conversion) is what produced 1000 °C+ readings.
    """
    tip_raw = data[0] + (data[1] << 8)
    ra = data[2] + (data[3] << 8)
    oa = data[4] + (data[5] << 8)
    raw_ambient = tip_raw + max(
        0.0, ((ra - min(AMBIENT_MIN_OFFSET, oa)) * 16 * 589) / 1487
    )
    return (raw_ambient + 8.0) / 16.0


def _decode_battery(data: bytes) -> int:
    """Decode battery percentage from the 2-byte battery characteristic."""
    raw = data[0] + (data[1] << 8)
    return min(100, raw * 10)


# ---------------------------------------------------------------------------
# MEATER Pro / MEATER 2 Plus decoders
# ---------------------------------------------------------------------------
# The Pro probe uses the same characteristic UUIDs as the original but packs
# 6 sensors into a single 12-byte notification: 6 × signed int16 little-endian.
# T0 (bytes 0-1) = innermost tip sensor; T5 (bytes 10-11) = ambient (ceramic end).
# Formula confirmed by community testing: tempC = raw_int16 / 32.0
# (see github.com/yyrliu/meater-pro-display for test data).


def _decode_tip_pro(data: bytes) -> float:
    """Decode tip temperature (°C) from the 12-byte MEATER Pro characteristic."""
    (raw,) = struct.unpack_from("<h", data, 0)
    return raw / 32.0


def _decode_ambient_pro(data: bytes) -> float:
    """Decode ambient temperature (°C) from the 12-byte MEATER Pro characteristic."""
    (raw,) = struct.unpack_from("<h", data, 10)
    return raw / 32.0


def _decode_battery_pro(data: bytes) -> int | None:
    """Battery decode for MEATER Pro 5-byte format - not yet confirmed.

    The raw bytes are logged at DEBUG level to help gather data for decoding.
    Returns None until the formula is validated.
    """
    return None


def _derive_cook_state(tip: float, prev_state: str, prev_tip: float | None) -> str:
    """Derive cook state from tip temperature."""
    if tip < 30.0:
        return "idle"
    if prev_state in ("cooking",) and prev_tip is not None:
        if tip < prev_tip - COOK_REST_DELTA:
            return "resting"
    return "cooking"


class MeaterBLECoordinator(DataUpdateCoordinator[MeaterData]):
    """Maintains a persistent, self-healing GATT connection to a MEATER probe."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{address}",
        )
        self.address = address
        self._client: BleakClientWithServiceCache | None = None
        self._connected = False
        self._connecting = False
        self._closing = False
        self._expected_disconnect = False
        self._connect_task: asyncio.Task | None = None
        self._cancel_reconnect: CALLBACK_TYPE | None = None
        self._cancel_bluetooth_callback: CALLBACK_TYPE | None = None
        self._reconnect_backoff = _RECONNECT_COOLDOWN
        self._grace_active = False
        self._cancel_grace: CALLBACK_TYPE | None = None
        # Liveness / active-poll state.
        self._cancel_poll: CALLBACK_TYPE | None = None
        self._polling = False
        self._poll_tick = 0
        self._last_data_time = 0.0
        # Reconnect diagnostics.
        self._last_advert_time = 0.0
        self._no_path_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        """Whether a live GATT connection to the probe is currently held."""
        return self._connected

    @property
    def available(self) -> bool:
        """Whether entities should present data.

        True while connected, and briefly after an unexpected drop (the grace
        window) so a transient blip on a proxy link does not flap every entity to
        unavailable while a reconnect is in flight.
        """
        return self._connected or self._grace_active

    @callback
    def async_start(self) -> None:
        """Register for advertisements and attempt an initial connection.

        The callback is registered with ``connectable=False`` so HA invokes it for
        advertisements heard by ANY scanner, including passive (non-connectable) ones.
        Through a Bluetooth proxy the probe is frequently heard only by a passive
        scanner while the connectable proxy hears it weakly (see #3); a
        ``connectable=True`` matcher would silently drop those advertisements and the
        reconnect trigger would rarely fire. Seeing the probe on any scanner means it
        is powered on and nearby, so we then attempt a connectable connection from
        there (and the backoff loop keeps trying if no connectable path exists yet).
        """
        self._closing = False
        self._cancel_bluetooth_callback = bluetooth.async_register_callback(
            self.hass,
            self._async_on_advertisement,
            BluetoothCallbackMatcher(address=self.address, connectable=False),
            BluetoothScanningMode.ACTIVE,
        )
        # The probe may already be in range at setup; don't wait for the next advert.
        self._schedule_connect()

    async def async_stop(self) -> None:
        """Stop reconnecting and drop the connection cleanly."""
        self._closing = True
        self._expected_disconnect = True
        if self._cancel_bluetooth_callback is not None:
            self._cancel_bluetooth_callback()
            self._cancel_bluetooth_callback = None
        if self._cancel_reconnect is not None:
            self._cancel_reconnect()
            self._cancel_reconnect = None
        self._stop_poll()
        self._clear_grace()
        if self._connect_task is not None:
            self._connect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._connect_task
            self._connect_task = None
        await self._async_disconnect()

    # ------------------------------------------------------------------
    # Reconnection plumbing
    # ------------------------------------------------------------------

    @callback
    def _async_on_advertisement(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        """Handle a fresh advertisement for our probe - (re)connect if needed.

        Fires for advertisements from any scanner (see ``async_start``). A fresh
        advertisement means the probe is powered on and nearby, so try to connect
        promptly. The backoff is only reset when the probe reappears after a period of
        silence (see ``_ADVERT_SILENCE_RESET``); a probe that advertises continuously
        while we keep failing to hold it (app/Block contention) must not pin the backoff
        at its floor.
        """
        if self._connected or self._closing:
            return
        now = self.hass.loop.time()
        if now - self._last_advert_time > _ADVERT_SILENCE_RESET:
            self._reset_reconnect_backoff()
        self._last_advert_time = now
        self._schedule_connect()

    @callback
    def _reset_reconnect_backoff(self) -> None:
        """Return the reconnect backoff to its floor (probe reappeared / just connected)."""
        self._reconnect_backoff = _RECONNECT_COOLDOWN

    @callback
    def _schedule_reconnect(self) -> None:
        """Queue the next reconnect attempt, escalating the backoff each time.

        This is what makes recovery self-healing without a connectable advertisement:
        a failed attempt always schedules the next one (up to ``_RECONNECT_COOLDOWN_MAX``)
        instead of waiting for an advert that may never arrive on the connectable path.
        """
        if self._closing or self._connected:
            return
        delay = self._reconnect_backoff
        self._reconnect_backoff = min(
            self._reconnect_backoff * 2, _RECONNECT_COOLDOWN_MAX
        )
        self._schedule_connect(delay)

    @callback
    def _schedule_connect(self, delay: float = 0.0) -> None:
        """Kick off a connection attempt, optionally after a cooldown.

        A pending cooldown (``_cancel_reconnect``) or an in-flight attempt
        (``_connecting``) suppresses new requests, so overlapping advertisement and
        disconnect callbacks can neither double-connect nor bypass the cooldown.
        """
        if self._closing or self._connected:
            return
        if self._cancel_reconnect is not None:
            return
        if delay > 0:
            # Queue a cooldown attempt. Deliberately not gated on an in-flight task:
            # this is called from _async_connect's own finally, where the current
            # task has not yet returned.
            self._cancel_reconnect = async_call_later(
                self.hass, delay, self._async_reconnect_fire
            )
            return
        if self._connecting:
            return
        if self._connect_task is not None and not self._connect_task.done():
            return
        self._connect_task = self.hass.async_create_background_task(
            self._async_connect(), name=f"meater_ble_connect:{self.address}"
        )

    @callback
    def _async_reconnect_fire(self, _now: object) -> None:
        """Fire a cooldown-delayed reconnect."""
        self._cancel_reconnect = None
        self._schedule_connect()

    async def _async_connect(self) -> None:
        """Establish the connection and subscribe to notifications."""
        if self._connected or self._closing:
            return
        self._connecting = True
        retry = False
        try:
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                # No connectable adapter has a path to the probe yet - through a proxy
                # it may currently be heard only by a passive scanner. Keep retrying on
                # the backoff timer rather than waiting for a connectable advertisement
                # that may never arrive (see #3).
                self._no_path_count += 1
                if self._no_path_count == _NO_PATH_WARN_AFTER:
                    _LOGGER.warning(
                        "MEATER %s: no connectable Bluetooth path after repeated "
                        "attempts. The probe is not reachable for a GATT connection. "
                        "If a Bluetooth proxy is in range, its connection slot may be "
                        "wedged (a known ESPHome issue, fixed in ESPHome 2026.5.1) or "
                        "the probe's signal is too weak to hold a link. Try updating "
                        "ESPHome on the proxy, moving a connectable proxy closer to the "
                        "probe, or rebooting the proxy.",
                        self.address,
                    )
                else:
                    _LOGGER.debug(
                        "MEATER %s has no connectable path yet; will retry",
                        self.address,
                    )
                retry = True
                return
            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    self.address,
                    disconnected_callback=self._async_on_disconnect,
                    max_attempts=_MAX_CONNECT_ATTEMPTS,
                    ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                        self.hass, self.address, connectable=True
                    ),
                )
            except (BleakError, asyncio.TimeoutError) as err:
                _LOGGER.debug(
                    "MEATER %s connection attempt failed (%s)", self.address, err
                )
                retry = True
                return
            # Connected: from here a failure must release the probe's single
            # connection slot, or every future reconnect will fail.
            try:
                await client.start_notify(CHAR_TEMPERATURE, self._on_temp_notify)
                await client.start_notify(CHAR_BATTERY, self._on_batt_notify)
                temp_raw = await client.read_gatt_char(CHAR_TEMPERATURE)
                batt_raw = await client.read_gatt_char(CHAR_BATTERY)
            except (BleakError, asyncio.TimeoutError) as err:
                _LOGGER.debug(
                    "MEATER %s failed to subscribe after connecting (%s); "
                    "disconnecting to free the probe",
                    self.address,
                    err,
                )
                self._expected_disconnect = True
                with contextlib.suppress(BleakError):
                    await client.disconnect()
                retry = True
                return
            self._client = client
            self._connected = True
            self._expected_disconnect = False
            # Back to a healthy link: drop the backoff to its floor, clear the
            # no-path counter, and end any grace window from a previous drop.
            self._reset_reconnect_backoff()
            self._no_path_count = 0
            self._clear_grace()
            _LOGGER.info("Connected to MEATER %s", self.address)
            # First reading populates entities and clears the unavailable state, and
            # seeds the liveness clock before the poll loop starts.
            self._process(temp_raw, batt_raw)
            self._start_poll()
        finally:
            self._connecting = False
            if retry and not self._closing and not self._connected:
                self._schedule_reconnect()

    @callback
    def _async_on_disconnect(self, client: BleakClientWithServiceCache) -> None:
        """Called by Bleak when the probe drops the connection."""
        if client is not self._client:
            # A late callback from a torn-down attempt (e.g. a deliberate disconnect on
            # the subscribe-failure path, or a previous client that dropped after a newer
            # one connected). It must not clobber the current connection's state.
            return
        self._connected = False
        self._client = None
        self._stop_poll()
        _LOGGER.debug(
            "MEATER %s disconnected (expected=%s)",
            self.address,
            self._expected_disconnect,
        )
        # An unexpected drop: hold the last reading for a short grace window and keep
        # retrying with backoff. Recovery must not depend on a connectable advertisement
        # - through a proxy the probe is often heard only by a passive scanner (see #3).
        if not self._expected_disconnect and not self._closing:
            self._start_grace_period()
            self._schedule_reconnect()
        # Reflect the state change. During the grace window ``available`` stays True, so
        # entities keep the last reading instead of flapping to unavailable.
        self.async_update_listeners()

    async def _async_disconnect(self) -> None:
        """Tear down the current client, if any.

        Nulls ``_client`` first so a resulting disconnect callback is recognized as
        stale, and bounds ``client.disconnect()`` with a timeout because a half-open
        link can make it hang.
        """
        self._stop_poll()
        client = self._client
        self._client = None
        self._connected = False
        if client is not None and client.is_connected:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=_DISCONNECT_TIMEOUT)
            except (BleakError, asyncio.TimeoutError) as err:
                _LOGGER.debug("MEATER %s error on disconnect: %s", self.address, err)

    # ------------------------------------------------------------------
    # Active read poll / liveness watchdog
    # ------------------------------------------------------------------

    @callback
    def _start_poll(self) -> None:
        """Begin actively reading the probe on a timer (data + liveness heartbeat)."""
        self._stop_poll()
        self._poll_tick = 0
        self._last_data_time = self.hass.loop.time()
        self._cancel_poll = async_track_time_interval(
            self.hass,
            self._async_poll,
            timedelta(seconds=_READ_POLL_INTERVAL),
            name=f"meater_ble_poll:{self.address}",
        )

    @callback
    def _stop_poll(self) -> None:
        """Cancel the active read poll, if running."""
        if self._cancel_poll is not None:
            self._cancel_poll()
            self._cancel_poll = None

    async def _async_poll(self, _now: object) -> None:
        """Read the probe and detect a dead link.

        Runs under a single ``_polling`` guard so only one tick is ever in flight, and
        so the recovery path cannot overlap a read. A successful read updates the
        entities and the liveness clock; if neither a read nor a notification has
        produced data within ``_STALL_TIMEOUT`` the link is half-open and is torn down
        for a reconnect.
        """
        client = self._client
        if (
            not self._connected
            or client is None
            or self._closing
            or self._connecting
            or self._polling
        ):
            return
        self._polling = True
        try:
            self._poll_tick += 1
            try:
                temp_raw = await asyncio.wait_for(
                    client.read_gatt_char(CHAR_TEMPERATURE), timeout=_READ_TIMEOUT
                )
                batt_raw: bytes | None = None
                if self._poll_tick % _BATTERY_POLL_EVERY == 0:
                    with contextlib.suppress(
                        BleakError, asyncio.TimeoutError, EOFError
                    ):
                        batt_raw = await asyncio.wait_for(
                            client.read_gatt_char(CHAR_BATTERY), timeout=_READ_TIMEOUT
                        )
                self._process(bytes(temp_raw), batt_raw)
            except (BleakError, asyncio.TimeoutError, EOFError) as err:
                _LOGGER.debug("MEATER %s poll read failed (%s)", self.address, err)
            # Liveness check, inside the guard so recovery cannot race another tick.
            if (
                self._connected
                and not self._closing
                and self.hass.loop.time() - self._last_data_time > _STALL_TIMEOUT
            ):
                await self._async_recover_stalled_link()
        finally:
            self._polling = False

    async def _async_recover_stalled_link(self) -> None:
        """Force a reconnect after the link went silent (half-open drop)."""
        if not self._connected or self._closing:
            return
        _LOGGER.info(
            "MEATER %s: no data for over %.0fs, link appears dead - reconnecting",
            self.address,
            _STALL_TIMEOUT,
        )
        # Route through the normal teardown so the disconnect is treated as expected
        # (no duplicate grace/reschedule from the disconnect callback), then drive a
        # single reconnect ourselves.
        self._expected_disconnect = True
        self._start_grace_period()
        await self._async_disconnect()
        self.async_update_listeners()
        self._schedule_reconnect()

    # ------------------------------------------------------------------
    # Availability grace window
    # ------------------------------------------------------------------

    @callback
    def _start_grace_period(self) -> None:
        """Keep entities on their last reading briefly while we try to reconnect.

        Measured from the first drop: if a window is already active it is left running,
        so a probe that keeps flapping without reconnecting cannot serve a stale reading
        for longer than one grace window.
        """
        if self.data is None:
            # Never had a reading - nothing to preserve, stay unavailable.
            return
        if self._cancel_grace is not None:
            return
        self._grace_active = True
        self._cancel_grace = async_call_later(
            self.hass, _AVAILABILITY_GRACE, self._async_grace_expired
        )

    @callback
    def _async_grace_expired(self, _now: object) -> None:
        """Grace window elapsed without recovery - let entities go unavailable."""
        self._cancel_grace = None
        self._grace_active = False
        self.async_update_listeners()

    @callback
    def _clear_grace(self) -> None:
        """Cancel any active grace window (we are connected again, or shutting down)."""
        if self._cancel_grace is not None:
            self._cancel_grace()
            self._cancel_grace = None
        self._grace_active = False

    # ------------------------------------------------------------------
    # Notify callbacks
    # ------------------------------------------------------------------

    @callback
    def _on_temp_notify(
        self, characteristic: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Handle a temperature characteristic notification."""
        # Battery arrives on its own characteristic; carry the last known value.
        self._process(bytes(data), None)

    @callback
    def _on_batt_notify(
        self, characteristic: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Handle a battery characteristic notification."""
        # Any traffic from the probe proves the link is alive - feed the liveness clock.
        self._last_data_time = self.hass.loop.time()
        raw = bytes(data)
        if len(raw) == 5:
            _LOGGER.debug(
                "MEATER Pro %s battery raw (5 bytes): %s - decode not yet confirmed",
                self.address,
                raw.hex("-"),
            )
            battery = _decode_battery_pro(raw)
        else:
            battery = _decode_battery(raw)
        if battery is None:
            return
        prev = self.data
        self.async_set_updated_data(
            MeaterData(
                tip_temp=prev.tip_temp if prev else None,
                ambient_temp=prev.ambient_temp if prev else None,
                battery=battery,
                cook_state=prev.cook_state if prev else "idle",
            )
        )

    def _process(self, temp_raw: bytes, batt_raw: bytes | None) -> None:
        """Decode raw bytes and push an update to all listeners."""
        # Any packet (even a corrupt one) proves the link is alive - feed the liveness
        # clock before the plausibility check so a run of bad packets does not look like
        # a dead link.
        self._last_data_time = self.hass.loop.time()
        if len(temp_raw) == 12:
            tip = _decode_tip_pro(temp_raw)
            ambient = _decode_ambient_pro(temp_raw)
        else:
            tip = _decode_tip(temp_raw)
            ambient = _decode_ambient(temp_raw)
        if not AMBIENT_TEMP_MIN_C <= ambient <= AMBIENT_TEMP_MAX_C:
            # Corrupt BLE packet - keep the last good value rather than spiking.
            _LOGGER.warning(
                "MEATER %s: implausible ambient %.1f°C decoded - discarding packet",
                self.address,
                ambient,
            )
            return
        if batt_raw is not None:
            if len(batt_raw) == 5:
                _LOGGER.debug(
                    "MEATER Pro %s battery raw (5 bytes): %s - decode not yet confirmed",
                    self.address,
                    batt_raw.hex("-"),
                )
                battery = _decode_battery_pro(batt_raw)
            else:
                battery = _decode_battery(batt_raw)
        else:
            battery = self.data.battery if self.data else None
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
    # DataUpdateCoordinator override - not used for polling, but required.
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> MeaterData:
        """Not used - data arrives via notify callbacks and the active read poll."""
        if self.data is not None:
            return self.data
        raise UpdateFailed("No data yet - waiting for GATT connection")
