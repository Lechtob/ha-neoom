"""Sensor platform for neoom."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from neoom_connect import DataPoint, State
from neoom_connect.diagnostics import numeric_value
from neoom_connect.units import normalize_unit

from .const import DOMAIN

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class NeoomSensorDescription(SensorEntityDescription):
    """Description for a neoom energy-flow sensor."""


SENSOR_DESCRIPTIONS: tuple[NeoomSensorDescription, ...] = (
    NeoomSensorDescription(
        key="POWER_PRODUCTION",
        translation_key="power_production",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    NeoomSensorDescription(
        key="POWER_CONSUMPTION",
        translation_key="power_consumption",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    NeoomSensorDescription(
        key="POWER_CONSUMPTION_CALC",
        translation_key="power_consumption_calc",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    NeoomSensorDescription(
        key="POWER_GRID",
        translation_key="power_grid",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    NeoomSensorDescription(
        key="POWER_STORAGE",
        translation_key="power_storage",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    NeoomSensorDescription(
        key="STATE_OF_CHARGE",
        translation_key="state_of_charge",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    NeoomSensorDescription(
        key="SELF_SUFFICIENCY",
        translation_key="self_sufficiency",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    NeoomSensorDescription(
        key="ENERGY_PRODUCED",
        translation_key="energy_produced",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    NeoomSensorDescription(
        key="ENERGY_IMPORTED",
        translation_key="energy_imported",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    NeoomSensorDescription(
        key="ENERGY_EXPORTED",
        translation_key="energy_exported",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    NeoomSensorDescription(
        key="ENERGY_CHARGED",
        translation_key="energy_charged",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    NeoomSensorDescription(
        key="ENERGY_DISCHARGED",
        translation_key="energy_discharged",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    NeoomSensorDescription(
        key="VOLTAGE",
        translation_key="voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    NeoomSensorDescription(
        key="CURRENT",
        translation_key="current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    NeoomSensorDescription(
        key="FREQUENCY",
        translation_key="frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


SENSOR_DESCRIPTIONS += tuple(
    NeoomSensorDescription(
        key=key,
        translation_key=key.lower(),
        native_unit_of_measurement=UnitOfPower.WATT
        if key.startswith("POWER_")
        else UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.POWER
        if key.startswith("POWER_")
        else SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT
        if key.startswith("POWER_")
        else SensorStateClass.TOTAL_INCREASING,
    )
    for key in (
        "POWER_APPLIANCES",
        "POWER_CHARGING_STATIONS",
        "POWER_HEATING",
        "ENERGY_CONSUMED",
        "ENERGY_CONSUMED_CALC",
        "ENERGY_APPLIANCES",
        "ENERGY_CHARGING_STATIONS",
        "ENERGY_HEATING",
    )
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up neoom sensors from a config entry."""
    coordinator = entry.runtime_data
    known: set[tuple[str | None, str]] = set()

    @callback
    def discover() -> None:
        entities = []
        descriptions = {description.key: description for description in SENSOR_DESCRIPTIONS}
        configuration = coordinator.configuration
        if configuration:
            for point in configuration.energy_flow_data_points.values():
                description = describe_point(point)
                if description:
                    descriptions[point.key] = description
        for description in descriptions.values():
            identity = (None, description.key)
            if identity not in known and (
                description.key in coordinator.data.flow.states
                or configuration
                and any(
                    point.key == description.key
                    for point in configuration.energy_flow_data_points.values()
                )
            ):
                known.add(identity)
                entities.append(NeoomEnergyFlowSensor(entry.entry_id, coordinator, description))
        if configuration:
            for thing in configuration.things.values():
                for point in thing.data_points.values():
                    identity = (thing.id, point.key)
                    description = describe_point(point)
                    if identity in known or description is None:
                        continue
                    known.add(identity)
                    entities.append(
                        NeoomEnergyFlowSensor(
                            entry.entry_id,
                            coordinator,
                            description,
                            thing_id=thing.id,
                            thing_name=thing.name or thing.type,
                        )
                    )
        async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class NeoomEnergyFlowSensor(CoordinatorEntity, SensorEntity):
    """Sensor backed by a neoom EnergyFlow state."""

    entity_description: NeoomSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        entry_id: str,
        coordinator: Any,
        description: NeoomSensorDescription,
        *,
        thing_id: str | None = None,
        thing_name: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self.thing_id = thing_id
        device_id = f"{entry_id}-{thing_id}" if thing_id else entry_id
        self._attr_unique_id = f"{device_id}-{description.key.lower()}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)},
            "name": thing_name or "neoom Energy Management",
            "manufacturer": "neoom",
        }

    @property
    def _state(self) -> State | None:
        data = self.coordinator.data
        states = data.things.get(self.thing_id, {}) if self.thing_id else data.flow.states
        return states.get(self.entity_description.key)

    @property
    def native_value(self) -> Any:
        state = self._state
        value = numeric_value(state.value) if state else None
        if (
            value is not None
            and self.coordinator.data.source == "cloud"
            and (self.entity_description.native_unit_of_measurement == "kW")
        ):
            return value / 1000
        return value

    @property
    def available(self) -> bool:
        if not super().available or self._state is None:
            return False
        # BEAAM timestamps describe changes, not successful polling heartbeats.
        if self.thing_id:
            states = self.coordinator.data.things.get(self.thing_id, {})
            connection = states.get("CONNECTION")
            if connection and connection.value is False:
                return False
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self._state
        return {
            "data_source": self.coordinator.data.source,
            "last_reported": state.timestamp.isoformat() if state and state.timestamp else None,
        }


def describe_point(point: DataPoint) -> NeoomSensorDescription | None:
    """Prefer device-provided units; expose scalar measurements only."""
    if point.data_type != "NUMBER":
        return None
    unit = normalize_unit(point.unit)
    known = next((item for item in SENSOR_DESCRIPTIONS if item.key == point.key), None)
    if known and known.native_unit_of_measurement == unit:
        return known
    device_class = {
        "W": SensorDeviceClass.POWER,
        "Wh": SensorDeviceClass.ENERGY,
        "kWh": SensorDeviceClass.ENERGY,
        "kW": SensorDeviceClass.POWER,
        "V": SensorDeviceClass.VOLTAGE,
        "A": SensorDeviceClass.CURRENT,
        "Hz": SensorDeviceClass.FREQUENCY,
        UnitOfTemperature.CELSIUS: SensorDeviceClass.TEMPERATURE,
    }.get(unit)
    cumulative = point.key in {
        "ENERGY_PRODUCED",
        "ENERGY_CONSUMED",
        "ENERGY_CONSUMED_CALC",
        "ENERGY_IMPORTED",
        "ENERGY_EXPORTED",
        "ENERGY_CHARGED",
        "ENERGY_DISCHARGED",
        "PRODUCED_ENERGY",
        "CONSUMED_ENERGY",
        "CHARGED_ENERGY",
        "DISCHARGED_ENERGY",
        "INPUT_ENERGY",
        "OUTPUT_ENERGY",
        "CONSUMED_ENERGY_TOTAL",
        "ENERGY_APPLIANCES",
        "ENERGY_CHARGING_STATIONS",
        "ENERGY_HEATING",
    }
    description = NeoomSensorDescription(
        key=point.key,
        name=point.key.replace("_", " ").capitalize(),
        native_unit_of_measurement=unit,
        device_class=device_class,
        state_class=SensorStateClass.TOTAL_INCREASING
        if cumulative and device_class == (SensorDeviceClass.ENERGY)
        else (None if device_class == SensorDeviceClass.ENERGY else SensorStateClass.MEASUREMENT),
        entity_category=EntityCategory.DIAGNOSTIC,
    )
    if known:
        description = replace(
            description, name=None, translation_key=known.translation_key, entity_category=None
        )
    return description
