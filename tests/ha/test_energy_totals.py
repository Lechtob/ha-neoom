"""Correctable BEAAM totals must not imply a new meter cycle on a decrease."""

import pytest
from homeassistant.helpers import entity_registry as er
from neoom_connect import DataPoint, EnergyFlow, State
from neoom_connect.exceptions import ApiUnavailableError

from custom_components.neoom.sensor import describe_point


@pytest.mark.parametrize("key", ["ENERGY_CONSUMED_CALC", "ENERGY_APPLIANCES"])
@pytest.mark.parametrize("unit", ["Wh", "kWh"])
async def test_corrected_total_preserves_values_and_identity(hass, clients, entry, key, unit):
    local = clients[0]
    config = local.get_site_configuration.return_value
    config.energy_flow_data_points[key] = DataPoint(key, key, "NUMBER", unit)
    local.get_site_state.return_value = EnergyFlow({key: State(key, 1000.334767)})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "neoom", f"{entry.entry_id}-{key.lower()}"
    )

    for value in (1000.334767, 1000.288923, 1001.5, None):
        local.get_site_state.return_value = EnergyFlow({key: State(key, value)})
        await entry.runtime_data.async_refresh()
        state = hass.states.get(entity_id)
        assert state.state == (str(value) if value is not None else "unknown")
        assert state.attributes["state_class"] == "total"
        assert state.attributes["unit_of_measurement"] == unit
        assert state.attributes["device_class"] == "energy"
        assert "last_reset" not in state.attributes

    local.get_site_state.side_effect = ApiUnavailableError("offline")
    await entry.runtime_data.async_refresh()
    assert hass.states.get(entity_id).state == "unavailable"
    local.get_site_state.side_effect = None
    local.get_site_state.return_value = EnergyFlow({key: State(key, 1002.5)})
    await entry.runtime_data.async_refresh()
    count = len(er.async_get(hass).entities)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "1002.5"
    assert hass.states.get(entity_id).attributes["state_class"] == "total"
    assert len(er.async_get(hass).entities) == count


@pytest.mark.parametrize(
    "key",
    [
        "ENERGY_IMPORTED",
        "ENERGY_EXPORTED",
        "ENERGY_PRODUCED",
        "ENERGY_CHARGED",
        "ENERGY_DISCHARGED",
    ],
)
@pytest.mark.parametrize("unit", ["Wh", "kWh"])
def test_main_energy_counters_keep_reset_semantics(key, unit):
    description = describe_point(DataPoint(key, key, "NUMBER", unit))
    assert description.state_class == "total_increasing"
    assert description.native_unit_of_measurement == unit
