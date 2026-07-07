"""Base entity for the MEATER BLE integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import MeaterBLECoordinator


class MeaterBaseEntity(CoordinatorEntity[MeaterBLECoordinator]):
    """Common base - sets device info and availability for every platform."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MeaterBLECoordinator,
        unique_id_suffix: str,
    ) -> None:
        """Initialize and anchor the entity to the probe device."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=f"{MANUFACTURER} {coordinator.address}",
        )

    @property
    def available(self) -> bool:
        """Available while connected, or briefly after a drop (reconnect grace).

        Tied to the coordinator connection state plus a short grace window, so a probe
        that truly goes away (put back in its charger, out of range) eventually shows
        unavailable, while a transient proxy-link blip does not flap the entity while a
        reconnect is in flight.
        """
        return self.coordinator.available and self.coordinator.data is not None
