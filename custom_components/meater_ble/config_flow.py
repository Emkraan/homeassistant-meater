"""Config flow for MEATER BLE."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN, MANUFACTURER, MODEL

_LOGGER = logging.getLogger(__name__)


class MeaterBLEConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MEATER BLE.

    The flow is triggered automatically when HA's Bluetooth integration detects
    a MEATER+ advertisement matching the service UUID declared in manifest.json.
    The user just confirms — no credentials needed.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a discovered MEATER+ probe."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or f"MEATER {discovery_info.address}",
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm addition of the discovered probe."""
        if user_input is not None:
            assert self._discovery_info is not None
            return self.async_create_entry(
                title=self._discovery_info.name
                or f"MEATER {self._discovery_info.address}",
                data={CONF_ADDRESS: self._discovery_info.address},
            )

        assert self._discovery_info is not None
        self._set_confirm_only()
        placeholders = {
            "name": self._discovery_info.name
            or f"MEATER {self._discovery_info.address}",
            "address": self._discovery_info.address,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders=placeholders,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a manual setup attempt (probe not yet in range)."""
        return self.async_abort(reason="no_devices_found")
