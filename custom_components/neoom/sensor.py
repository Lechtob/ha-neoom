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

from .const import MODE_CLOUD, MODE_LOCAL
from .device import device_info

PARALLEL_UPDATES = 0

ARRAY_CHANNELS = {"INPUTS_POWER": "W", "VOLTAGES": "V", "CURRENTS": "A"}
MAX_CHANNELS = 64
TRANSLATED_POINTS = {
    "ACTIVE_POWER",
    "REACTIVE_POWER",
    "APPARENT_POWER",
    "POWER_FACTOR",
    "POWER",
    "ACTIVE_POWER_LIMIT",
    "MAX_POWER_GRID_FEED_IN",
    "MAX_CURRENT_CHARGE",
    "MAX_CURRENT_DISCHARGE",
    "MAX_POWER_CHARGE",
    "MAX_POWER_DISCHARGE",
    "TARGET_POWER",
    "MIN_SOC",
    "MIN_SOC_BACKUP_ENERGY",
    "MIN_SOC_SELF_CONSUMPTION_OPT",
    "CHARGED_ENERGY",
    "DISCHARGED_ENERGY",
    "INPUT_ENERGY",
    "OUTPUT_ENERGY",
    "PRODUCED_ENERGY",
    "CONSUMED_ENERGY_TOTAL",
    "CHARGING_PROCESS_ENERGY",
    "CHARGING_TIME",
    *(
        f"{quantity}_P{phase}"
        for quantity in ("VOLTAGE", "CURRENT", "POWER")
        for phase in (1, 2, 3)
    ),
}


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
    known: set[tuple[str | None, str, int | None]] = set()
    async_add_entities([NeoomDataSourceSensor(entry.entry_id, coordinator)])

    @callback
    def discover() -> None:
        entities = []
        descriptions = {description.key: description for description in SENSOR_DESCRIPTIONS}
        configuration = coordinator.configuration
        if configuration:
            for point in configuration.energy_flow_data_points.values():
                if point.data_type != "NUMBER":
                    continue
                description = describe_point(point)
                if description:
                    descriptions[point.key] = description
        for description in descriptions.values():
            identity = (None, description.key, None)
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
                    description = describe_point(point)
                    if description is None:
                        continue
                    indices: list[int | None] = [None]
                    if point.data_type == "NUMBER_ARRAY[]":
                        state = coordinator.data.things.get(thing.id, {}).get(point.key)
                        if state is None or not isinstance(state.value, list):
                            continue
                        if any(isinstance(value, (list, dict)) for value in state.value):
                            continue
                        indices = list(range(min(len(state.value), MAX_CHANNELS)))
                    for index in indices:
                        identity = (thing.id, point.key, index)
                        if identity in known:
                            continue
                        known.add(identity)
                        entities.append(
                            NeoomEnergyFlowSensor(
                                entry.entry_id,
                                coordinator,
                                description,
                                thing_id=thing.id,
                                array_index=index,
                            )
                        )
        async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class NeoomDataSourceSensor(CoordinatorEntity, SensorEntity):
    """Expose the source of the latest successful site reading."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "data_source"
    _attr_options = [MODE_LOCAL, MODE_CLOUD]

    def __init__(self, entry_id, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}-data_source"
        self._attr_device_info = device_info(entry_id)

    @property
    def native_value(self):
        return self.coordinator.data.source


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
        array_index: int | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self.thing_id = thing_id
        self.array_index = array_index
        device_id = f"{entry_id}-{thing_id}" if thing_id else entry_id
        self._attr_unique_id = f"{device_id}-{description.key.lower()}"
        if array_index is not None:
            self._attr_unique_id += f"-channel-{array_index + 1}"
            self._attr_translation_placeholders = {"channel": str(array_index + 1)}
        configuration = coordinator.configuration
        thing = configuration.things[thing_id] if configuration and thing_id else None
        self._attr_device_info = device_info(
            entry_id, thing, configuration, via_device_id=coordinator.site_device_id
        )

    @property
    def _state(self) -> State | None:
        data = self.coordinator.data
        states = data.things.get(self.thing_id, {}) if self.thing_id else data.flow.states
        return states.get(self.entity_description.key)

    @property
    def native_value(self) -> Any:
        state = self._state
        value = state.value if state else None
        if self.array_index is not None:
            value = (
                value[self.array_index]
                if isinstance(value, list) and self.array_index < len(value)
                else None
            )
        value = numeric_value(value)
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
        if self.array_index is not None and (
            not isinstance(self._state.value, list) or self.array_index >= len(self._state.value)
        ):
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
    """Prefer device-provided units; only expand documented power/voltage/current arrays."""
    if point.data_type == "NUMBER_ARRAY[]":
        if point.key not in ARRAY_CHANNELS or point.unit != ARRAY_CHANNELS[point.key]:
            return None
        scalar = describe_point(replace(point, data_type="NUMBER"))
        return replace(scalar, name=None, translation_key=point.key.lower())
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
    elif point.key in TRANSLATED_POINTS:
        description = replace(description, name=None, translation_key=point.key.lower())
    return description
