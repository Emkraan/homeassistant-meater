"""Sensor platform for MEATER BLE."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MeaterBLECoordinator, MeaterData
from .entity import MeaterBaseEntity

COOK_STATES = ["idle", "cooking", "approaching_target", "resting"]


@dataclass(frozen=True, kw_only=True)
class MeaterSensorEntityDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with a value extractor."""

    value_fn: Callable[[MeaterData], float | int | str | None]


SENSOR_DESCRIPTIONS: tuple[MeaterSensorEntityDescription, ...] = (
    MeaterSensorEntityDescription(
        key="tip_temp",
        translation_key="tip_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.tip_temp,
    ),
    MeaterSensorEntityDescription(
        key="ambient_temp",
        translation_key="ambient_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.ambient_temp,
    ),
    MeaterSensorEntityDescription(
        key="battery",
        translation_key="battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.battery,
    ),
    MeaterSensorEntityDescription(
        key="cook_state",
        translation_key="cook_state",
        device_class=SensorDeviceClass.ENUM,
        options=COOK_STATES,
        value_fn=lambda d: d.cook_state,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add MEATER BLE sensors from a config entry."""
    coordinator: MeaterBLECoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        MeaterSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    ]
    entities.append(MeaterSignalSensor(coordinator))
    async_add_entities(entities)


class MeaterSensor(MeaterBaseEntity, SensorEntity):
    """Description-driven MEATER BLE sensor."""

    entity_description: MeaterSensorEntityDescription

    def __init__(
        self,
        coordinator: MeaterBLECoordinator,
        description: MeaterSensorEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | str | None:
        """Return the sensor value via the description's extractor."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class MeaterSignalSensor(MeaterBaseEntity, SensorEntity):
    """Diagnostic: RSSI of the probe's most recently seen advertisement.

    The probe does not advertise while a GATT connection is held (see the coordinator
    module docstring), so this freezes at whatever it was just before connecting, or
    since the last drop - it is not a live connection signal. Still useful for judging
    whether a weak signal is contributing to drops. Disabled by default, like other
    diagnostic entities, since most users only need the cook data.
    """

    _attr_translation_key = "signal_strength"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: MeaterBLECoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "rssi")

    @property
    def available(self) -> bool:
        """Available once any advertisement has been seen, independent of connection.

        Unlike the data sensors (gated on ``coordinator.available``, i.e. connected or
        in the grace window), a stale-but-present last-advertisement RSSI is useful
        precisely while the probe is NOT connected - e.g. while troubleshooting why it
        will not connect at all.
        """
        return (
            self.coordinator.data is not None and self.coordinator.data.rssi is not None
        )

    @property
    def native_value(self) -> int | None:
        """Return the last-seen advertisement RSSI, if any."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.rssi
