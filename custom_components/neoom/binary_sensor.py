"""Connection and error status supplied by BEAAM devices."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import MODE_CLOUD, MODE_HYBRID
from .device import device_info

PARALLEL_UPDATES = 0

SITE_STATUS_DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="site_connection",
        translation_key="site_connection",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    BinarySensorEntityDescription(
        key="cloud_fallback",
        translation_key="cloud_fallback",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known = set()
    async_add_entities(
        NeoomSiteStatus(coordinator, entry.entry_id, description)
        for description in SITE_STATUS_DESCRIPTIONS
        if description.key != "cloud_fallback" or coordinator.mode == MODE_HYBRID
    )

    @callback
    def discover():
        if coordinator.configuration is None:
            return
        entities = []
        for thing in coordinator.configuration.things.values():
            for point in thing.data_points.values():
                identity = (thing.id, point.key)
                if (
                    point.key in {"CONNECTION", "CONNECTIONS", "ERROR_CODES"}
                    and identity not in known
                ):
                    known.add(identity)
                    entities.append(NeoomStatus(coordinator, entry.entry_id, thing, point.key))
        async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class NeoomSiteStatus(CoordinatorEntity, BinarySensorEntity):
    """Report site polling health independently from individual devices."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id, description):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}-{description.key}"
        self._attr_device_info = device_info(entry_id)

    @property
    def available(self):
        # Connection must remain readable when polling fails; cached source must not.
        return self.entity_description.key == "site_connection" or super().available

    @property
    def is_on(self):
        if self.entity_description.key == "site_connection":
            return self.coordinator.last_update_success
        return self.coordinator.data.source == MODE_CLOUD


class NeoomStatus(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id, thing, key):
        super().__init__(coordinator)
        self.thing_id = thing.id
        self.key = key
        self._attr_unique_id = f"{entry_id}-{thing.id}-{key.lower()}"
        self._attr_translation_key = "errors" if key == "ERROR_CODES" else "connection"
        self._attr_device_class = (
            BinarySensorDeviceClass.PROBLEM
            if key == "ERROR_CODES"
            else BinarySensorDeviceClass.CONNECTIVITY
        )
        self._attr_device_info = device_info(
            entry_id, thing, coordinator.configuration, via_device_id=coordinator.site_device_id
        )

    @property
    def available(self):
        return super().available and self.key in self.coordinator.data.things.get(self.thing_id, {})

    @property
    def is_on(self):
        state = self.coordinator.data.things.get(self.thing_id, {}).get(self.key)
        if state is None or state.value is None:
            return None
        value = state.value
        if self.key == "ERROR_CODES":
            return bool(value) if isinstance(value, list) else None
        if self.key == "CONNECTIONS":
            return (
                all(value)
                if isinstance(value, list)
                and value
                and all(isinstance(item, bool) for item in value)
                else None
            )
        return value if isinstance(value, bool) else None
