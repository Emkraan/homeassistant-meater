"""The MEATER BLE integration."""

from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, MEATER_SERVICE_UUID, PLATFORMS
from .coordinator import MeaterBLECoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MEATER BLE from a config entry."""
    address: str = entry.data[CONF_ADDRESS]

    coordinator = MeaterBLECoordinator(hass, address)

    # Register a passive BLE callback so the coordinator refreshes whenever the
    # probe is seen in a scan — this is the "local_push" path.
    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            coordinator.async_handle_bluetooth_event,
            bluetooth.BluetoothCallbackMatcher(
                service_uuid=MEATER_SERVICE_UUID,
                address=address,
            ),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
    )

    # Do an initial GATT read so entities have data before HA finishes setup.
    await coordinator.async_refresh()
    if not coordinator.last_update_success:
        raise ConfigEntryNotReady(
            f"MEATER probe {address!r} not reachable at startup; will retry"
        )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
