"""Connection diagnostics follow successful reads, outages and recovery."""

from unittest.mock import patch

import pytest
from homeassistant.helpers import entity_registry as er
from neoom_connect.exceptions import ApiUnavailableError, AuthenticationError, RateLimitError


def entity(hass, entry, key, domain="binary_sensor"):
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(domain, "neoom", f"{entry.entry_id}-{key}")
    return hass.states.get(entity_id) if entity_id else None


async def setup(hass, entry, mode):
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "mode": mode, "cloud_token": "cloud-secret"}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data


@pytest.mark.parametrize("mode", ["local", "cloud", "hybrid"])
async def test_status_entities_and_registry(hass, clients, entry, mode):
    await setup(hass, entry, mode)
    source = entity(hass, entry, "data_source", "sensor")
    assert source.state == ("cloud" if mode == "cloud" else "local")
    assert source.attributes["device_class"] == "enum"
    assert source.attributes["options"] == ["local", "cloud"]
    assert "state_class" not in source.attributes
    assert "unit_of_measurement" not in source.attributes
    connection = entity(hass, entry, "site_connection")
    assert connection.state == "on"
    assert connection.attributes["device_class"] == "connectivity"
    fallback = entity(hass, entry, "cloud_fallback")
    if mode == "hybrid":
        assert fallback.state == "off"
        assert fallback.attributes["device_class"] == "problem"
    else:
        assert fallback is None
    registry = er.async_get(hass)
    power = entity(hass, entry, "power_grid", "sensor")
    assert (
        registry.async_get(source.entity_id).device_id
        == registry.async_get(power.entity_id).device_id
    )
    for state in (source, connection, fallback):
        if state is not None:
            assert registry.async_get(state.entity_id).entity_category == "diagnostic"


@pytest.mark.parametrize("mode", ["local", "cloud", "hybrid"])
async def test_complete_failure_and_recovery(hass, clients, entry, mode):
    with patch("custom_components.neoom.coordinator.monotonic", return_value=1000):
        coordinator = await setup(hass, entry, mode)
    clients[0].get_site_state.side_effect = ApiUnavailableError("offline")
    clients[1].get_latest_energy_flow.side_effect = ApiUnavailableError("offline")
    with patch("custom_components.neoom.coordinator.monotonic", return_value=1121):
        await coordinator.async_refresh()
    assert entity(hass, entry, "site_connection").state == "off"
    assert entity(hass, entry, "data_source", "sensor").state == "unavailable"
    if mode == "hybrid":
        assert entity(hass, entry, "cloud_fallback").state == "unavailable"
    clients[0].get_site_state.side_effect = None
    clients[1].get_latest_energy_flow.side_effect = None
    with patch("custom_components.neoom.coordinator.monotonic", return_value=1242):
        await coordinator.async_refresh()
    assert entity(hass, entry, "site_connection").state == "on"
    assert entity(hass, entry, "data_source", "sensor").state == (
        "cloud" if mode == "cloud" else "local"
    )
    if mode == "hybrid":
        assert entity(hass, entry, "cloud_fallback").state == "off"


async def test_fallback_cache_expiry_and_local_recovery(hass, clients, entry):
    coordinator = await setup(hass, entry, "hybrid")
    clients[0].get_site_state.side_effect = ApiUnavailableError("offline")
    with patch("custom_components.neoom.coordinator.monotonic", return_value=1000):
        await coordinator.async_refresh()
        await coordinator.async_refresh()
    assert clients[1].get_latest_energy_flow.await_count == 1
    assert entity(hass, entry, "site_connection").state == "on"
    assert entity(hass, entry, "data_source", "sensor").state == "cloud"
    assert entity(hass, entry, "cloud_fallback").state == "on"
    clients[1].get_latest_energy_flow.side_effect = RateLimitError(300)
    with patch("custom_components.neoom.coordinator.monotonic", return_value=1121):
        await coordinator.async_refresh()
    assert entity(hass, entry, "site_connection").state == "off"
    assert entity(hass, entry, "data_source", "sensor").state == "unavailable"
    assert entity(hass, entry, "cloud_fallback").state == "unavailable"
    with patch("custom_components.neoom.coordinator.monotonic", return_value=1200):
        await coordinator.async_refresh()
        assert clients[1].get_latest_energy_flow.await_count == 2
        clients[0].get_site_state.side_effect = None
        await coordinator.async_refresh()
    assert entity(hass, entry, "site_connection").state == "on"
    assert entity(hass, entry, "data_source", "sensor").state == "local"
    assert entity(hass, entry, "cloud_fallback").state == "off"


async def test_cold_cloud_start_and_reload_do_not_duplicate_status(hass, clients, entry):
    clients[0].get_site_configuration.side_effect = ApiUnavailableError("offline")
    coordinator = await setup(hass, entry, "hybrid")
    assert entity(hass, entry, "data_source", "sensor").state == "cloud"
    assert entity(hass, entry, "cloud_fallback").state == "on"
    original_ids = {
        key: entity(hass, entry, key, domain).entity_id
        for key, domain in (
            ("data_source", "sensor"),
            ("site_connection", "binary_sensor"),
            ("cloud_fallback", "binary_sensor"),
        )
    }
    clients[0].get_site_configuration.side_effect = None
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    count = len(er.async_get(hass).entities)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(er.async_get(hass).entities) == count
    expected = {"data_source": "local", "site_connection": "on", "cloud_fallback": "off"}
    for key, entity_id in original_ids.items():
        assert hass.states.get(entity_id).state == expected[key]


async def test_device_failure_does_not_report_site_outage(hass, clients, entry):
    coordinator = await setup(hass, entry, "hybrid")
    clients[0].get_thing_states.side_effect = ApiUnavailableError("offline")
    await coordinator.async_refresh()
    assert entity(hass, entry, "site_connection").state == "on"
    assert entity(hass, entry, "cloud_fallback").state == "off"
    assert entity(hass, entry, "data_source", "sensor").state == "local"
    assert entity(hass, entry, "battery-1-state_of_charge", "sensor").state == "unavailable"


async def test_auth_failure_marks_connection_off(hass, clients, entry):
    coordinator = await setup(hass, entry, "hybrid")
    clients[0].get_site_state.side_effect = AuthenticationError("invalid")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert entity(hass, entry, "site_connection").state == "off"
    assert entity(hass, entry, "data_source", "sensor").state == "unavailable"
    assert entity(hass, entry, "cloud_fallback").state == "unavailable"
    clients[1].get_latest_energy_flow.assert_not_called()


async def test_six_hour_simulated_outage_keeps_counters_unavailable(hass, clients, entry):
    coordinator = await setup(hass, entry, "hybrid")
    original = entity(hass, entry, "energy_imported", "sensor").state
    clients[0].get_site_state.side_effect = ApiUnavailableError("offline")
    clients[1].get_latest_energy_flow.side_effect = RateLimitError(300)
    for tick in range(0, 6 * 3600, 60):
        with patch("custom_components.neoom.coordinator.monotonic", return_value=1000 + tick):
            await coordinator.async_refresh()
        assert entity(hass, entry, "energy_imported", "sensor").state == "unavailable"
        assert entity(hass, entry, "site_connection").state == "off"
    assert clients[1].get_latest_energy_flow.await_count == 72
    clients[0].get_site_state.side_effect = None
    await coordinator.async_refresh()
    assert entity(hass, entry, "energy_imported", "sensor").state == original
    assert entity(hass, entry, "site_connection").state == "on"
