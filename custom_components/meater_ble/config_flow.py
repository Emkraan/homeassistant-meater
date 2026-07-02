"""Config flow for MEATER BLE."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import (
    DOMAIN,
    KNOWN_MEATER_SERVICE_UUIDS,
    MANUFACTURER,
    MEATER_DOCK_SERVICE_UUID,
    MEATER_MANUFACTURER_ID,
    MEATER_PRO_SERVICE_UUID,
    MEATER_SERVICE_UUID,
    MODEL,
)

_LOGGER = logging.getLogger(__name__)

# Service UUIDs that identify the *probe* (a valid connection target), as opposed to
# the charger/dock. Used to avoid auto-adding the un-connectable dock (see #2).
_PROBE_SERVICE_UUIDS = {MEATER_SERVICE_UUID.lower(), MEATER_PRO_SERVICE_UUID.lower()}


def _is_meater(discovery_info: BluetoothServiceInfoBleak) -> bool:
    """Return True if a BLE advertisement looks like a MEATER probe or dock.

    Matches on any signal a MEATER device may broadcast: the Apption Labs manufacturer
    ID (always in the primary advertisement), a known MEATER service UUID, or a name
    beginning with "meater" (case-insensitive - the probe advertises "MEATER", "MEATER+"
    or "meater2" depending on model/firmware).
    """
    if MEATER_MANUFACTURER_ID in discovery_info.manufacturer_data:
        return True
    advertised = {uuid.lower() for uuid in discovery_info.service_uuids}
    if advertised & KNOWN_MEATER_SERVICE_UUIDS:
        return True
    name = (discovery_info.name or "").lower()
    return name.startswith("meater")


def _is_dock_only(discovery_info: BluetoothServiceInfoBleak) -> bool:
    """Return True if the advertisement is the charger/dock and NOT a probe.

    The dock advertises the ``dcbb67ca`` service UUID and has no readable temperature
    characteristics - connecting to it fails with ATT 0x0e (see #2). We only treat an
    advertisement as the dock when it carries the dock UUID and none of the probe UUIDs,
    so a probe is never mistaken for the dock.
    """
    advertised = {uuid.lower() for uuid in discovery_info.service_uuids}
    return MEATER_DOCK_SERVICE_UUID.lower() in advertised and not (
        advertised & _PROBE_SERVICE_UUIDS
    )


def _title(discovery_info: BluetoothServiceInfoBleak) -> str:
    """Human title for a discovered probe."""
    name = discovery_info.name
    if name and name.lower() != discovery_info.address.lower():
        return name
    return f"MEATER {discovery_info.address}"


class MeaterBLEConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MEATER BLE.

    Two entry points:
    * ``async_step_bluetooth`` - HA auto-discovers a probe whose advertisement matches a
      matcher in manifest.json (manufacturer ID, service UUID, or local name). The user
      just confirms.
    * ``async_step_user`` - manual "add device". Forces an active Bluetooth scan and lists
      every advertisement HA has seen so the user can pick their probe by name/address,
      even when auto-discovery never fired (e.g. a proxy that drops the scan response).
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        # address -> display label, populated by the manual picker.
        self._discovered_devices: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a probe discovered automatically via a manifest matcher."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        # The Apption Labs manufacturer ID (and, on some firmware, the local name) also
        # match the charger/dock, which is not a valid connection target. Don't nag the
        # user to add it - the probe advertises separately when out of the charger.
        if _is_dock_only(discovery_info):
            return self.async_abort(reason="dock")

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": _title(discovery_info)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm addition of the discovered probe."""
        assert self._discovery_info is not None
        title = _title(self._discovery_info)
        if user_input is not None:
            return self.async_create_entry(
                title=title,
                data={CONF_ADDRESS: self._discovery_info.address},
            )

        self._set_confirm_only()
        placeholders = {
            "name": title,
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
        """Handle a manual setup attempt - let the user pick a discovered probe.

        Auto-discovery relies on the probe's name/service UUID reaching HA, which does not
        always happen through a Bluetooth proxy. This step forces an active scan and lists
        the advertisements HA already knows about so the user always has a way in.
        """
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self._discovered_devices.get(address, f"MEATER {address}"),
                data={CONF_ADDRESS: address},
            )

        # Nudge the adapters/proxies to actively scan so scan-response data (the MEATER
        # local name and service UUID) is captured for devices seen only passively so far.
        await bluetooth.async_request_active_scan(self.hass)

        current_addresses = self._async_current_ids(include_ignore=False)
        meater_devices: dict[str, str] = {}
        all_devices: dict[str, str] = {}
        for discovery_info in async_discovered_service_info(
            self.hass, connectable=True
        ):
            address = discovery_info.address
            if address in current_addresses:
                continue
            if _is_dock_only(discovery_info):
                continue
            label = _title(discovery_info)
            all_devices[address] = label
            if _is_meater(discovery_info):
                meater_devices[address] = label

        # Prefer the filtered MEATER list; fall back to every device so a probe that
        # advertises nothing recognizable can still be added by its MAC address.
        self._discovered_devices = meater_devices or all_devices
        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices)}
            ),
        )
