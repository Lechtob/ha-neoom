"""Read-only channel discovery is bounded, stable and safe during outages."""

from dataclasses import replace
from unittest.mock import patch

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from neoom_connect import DataPoint, State
from neoom_connect.exceptions import ApiUnavailableError

from custom_components.neoom.sensor import MAX_CHANNELS, describe_point


def state(hass, entry, channel):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "neoom", f"{entry.entry_id}-battery-1-inputs_power-channel-{channel}"
    )
    return hass.states.get(entity_id) if entity_id else None


async def setup(hass, clients, entry, values):
    config = clients[0].get_site_configuration.return_value
    thing = config.things["battery-1"]
    config.things["battery-1"] = replace(
        thing,
        type="INVERTER",
        data_points={
            **thing.data_points,
            "inputs": DataPoint("inputs", "INPUTS_POWER", "NUMBER_ARRAY[]", "W"),
        },
    )
    clients[0].get_thing_states.return_value["INPUTS_POWER"] = State("INPUTS_POWER", values)
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "mode": "hybrid", "cloud_token": "secret"}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data


async def test_channels_and_device_link(hass, clients, entry):
    await setup(hass, clients, entry, [100, 200.5])
    assert state(hass, entry, 1).state == "100"
    second = state(hass, entry, 2)
    assert second.state == "200.5"
    assert second.attributes["unit_of_measurement"] == "W"
    assert second.attributes["state_class"] == "measurement"
    assert "2" in second.attributes["friendly_name"]
    device = dr.async_get(hass).async_get(er.async_get(hass).async_get(second.entity_id).device_id)
    assert device.model == "Inverter"
    assert device.via_device_id == entry.runtime_data.site_device_id


async def test_shrink_growth_and_reload_preserve_channel_ids(hass, clients, entry):
    coordinator = await setup(hass, clients, entry, [10, 20])
    original_id = state(hass, entry, 2).entity_id
    clients[0].get_thing_states.return_value["INPUTS_POWER"] = State("INPUTS_POWER", [30])
    await coordinator.async_refresh()
    assert state(hass, entry, 2).state == "unavailable"
    clients[0].get_thing_states.return_value["INPUTS_POWER"] = State("INPUTS_POWER", [40, 50, 60])
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert state(hass, entry, 2).entity_id == original_id
    assert state(hass, entry, 2).state == "50"
    assert state(hass, entry, 3).state == "60"
    count = len(er.async_get(hass).entities)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(er.async_get(hass).entities) == count
    assert state(hass, entry, 2).entity_id == original_id


async def test_fallback_and_device_offline(hass, clients, entry):
    coordinator = await setup(hass, clients, entry, [10, 20])
    clients[0].get_site_state.side_effect = ApiUnavailableError("offline")
    with patch("custom_components.neoom.coordinator.monotonic", return_value=1000):
        await coordinator.async_refresh()
    assert state(hass, entry, 1).state == "unavailable"
    clients[0].get_site_state.side_effect = None
    await coordinator.async_refresh()
    assert state(hass, entry, 1).state == "10"
    clients[0].get_thing_states.return_value["CONNECTION"] = State("CONNECTION", False)
    await coordinator.async_refresh()
    assert state(hass, entry, 1).state == "unavailable"


@pytest.mark.parametrize("value", [None, True, "bad", float("nan"), float("inf")])
async def test_invalid_channel_value_is_unknown(hass, clients, entry, value):
    await setup(hass, clients, entry, [value, 1])
    assert state(hass, entry, 1).state == "unknown"
    assert state(hass, entry, 2).state == "1"


@pytest.mark.parametrize("values", [None, [], [[1], [2]], {"channel": 1}])
async def test_absent_or_nested_channels_not_discovered(hass, clients, entry, values):
    await setup(hass, clients, entry, values)
    assert state(hass, entry, 1) is None


async def test_discovery_is_bounded(hass, clients, entry):
    await setup(hass, clients, entry, [1] * (MAX_CHANNELS + 1))
    assert state(hass, entry, MAX_CHANNELS).state == "1"
    assert state(hass, entry, MAX_CHANNELS + 1) is None


@pytest.mark.parametrize(
    "key,unit,expected",
    [
        ("VOLTAGES", "V", "voltage"),
        ("CURRENTS", "A", "current"),
        ("INPUTS_POWER", "W", "power"),
    ],
)
def test_channel_units(key, unit, expected):
    description = describe_point(DataPoint("point", key, "NUMBER_ARRAY[]", unit))
    assert description.device_class == expected


@pytest.mark.parametrize("key,unit", [("ENERGY", "Wh"), ("VOLTAGES", "W")])
def test_unverified_arrays_are_not_exposed(key, unit):
    assert describe_point(DataPoint("point", key, "NUMBER_ARRAY[]", unit)) is None
