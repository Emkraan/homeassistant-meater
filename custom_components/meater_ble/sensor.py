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
from homeassistant.const import PERCENTAGE, UnitOfTemperature
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
    async_add_entities(
        MeaterSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    )


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
