"""Consistent site/device links without changing registry identifiers."""

from homeassistant.helpers.device_registry import DeviceInfo
from neoom_connect import SiteConfiguration, Thing

from .const import DOMAIN

DEVICE_TYPES = {
    "INVERTER": "Inverter",
    "PV": "PV",
    "BATTERY": "Battery",
    "ELECTRICITY_METER_AC": "Electricity meter",
    "CHARGING_POINT_AC": "AC charging point",
}


def device_info(
    entry_id: str,
    thing: Thing | None = None,
    configuration: SiteConfiguration | None = None,
    *,
    via_device_id: str | None = None,
) -> DeviceInfo:
    if thing is None:
        return DeviceInfo(
            identifiers={(DOMAIN, entry_id)}, name="neoom Energy Management", manufacturer="neoom"
        )
    name = thing.name or DEVICE_TYPES.get(thing.type, thing.type)
    model = DEVICE_TYPES.get(thing.type, thing.type)
    if configuration and sum(t.name == thing.name for t in configuration.things.values()) > 1:
        name = f"{name} ({model} {thing.id[-6:]})"
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}-{thing.id}")},
        name=name,
        manufacturer="neoom",
        model=model,
        via_device_id=via_device_id,
    )
