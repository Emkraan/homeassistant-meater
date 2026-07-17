"""The MEATER BLE integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .const import CONF_KEEPALIVE_INTERVAL, DOMAIN, PLATFORMS
from .coordinator import MeaterBLECoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MEATER BLE from a config entry."""
    address: str = entry.data[CONF_ADDRESS]

    coordinator = MeaterBLECoordinator(
        hass,
        address,
        keepalive_interval=entry.options.get(CONF_KEEPALIVE_INTERVAL),
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload when the options (e.g. the keepalive interval) change so the coordinator picks
    # up the new cadence.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    # Register for advertisements and connect once entities exist to receive updates.
    coordinator.async_start()
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: MeaterBLECoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_stop()

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
