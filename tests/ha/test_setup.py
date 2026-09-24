"""Exercise actual setup, entity registries, fallback, recovery and unload."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from neoom_connect.exceptions import ApiUnavailableError, AuthenticationError

from custom_components.neoom.diagnostics import async_get_config_entry_diagnostics


def state_for(hass, entry, key):
    entity_id = er.async_get(hass).async_get_entity_id("sensor", "neoom", f"{entry.entry_id}-{key}")
    return hass.states.get(entity_id)


async def setup(hass, entry):
    if hass.config_entries.async_get_entry(entry.entry_id) is None:
        entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_local_setup_entities_and_unload(hass, clients, entry):
    await setup(hass, entry)
    assert state_for(hass, entry, "power_grid").state == "21"
    energy = state_for(hass, entry, "energy_imported")
    assert energy.attributes["unit_of_measurement"] == "Wh"
    assert energy.attributes["state_class"] == "total_increasing"
    assert state_for(hass, entry, "battery-1-state_of_charge").state == "35"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.NOT_LOADED


async def test_hybrid_fallback_is_throttled_and_recovers(hass, clients, entry):
    local, cloud = clients
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            "mode": "hybrid",
            "cloud_token": "cloud-secret",
        },
    )
    await setup(hass, entry)
    coordinator = entry.runtime_data
    local.get_site_state.side_effect = ApiUnavailableError("offline")
    with patch("custom_components.neoom.coordinator.monotonic", return_value=1000):
        await coordinator.async_refresh()
        assert coordinator.data.source == "cloud"
        assert state_for(hass, entry, "power_grid").state == "50"
        assert state_for(hass, entry, "energy_imported").state == "unavailable"
        assert state_for(hass, entry, "battery-1-state_of_charge").state == "unavailable"
        await coordinator.async_refresh()
        assert cloud.get_latest_energy_flow.await_count == 1
    local.get_site_state.side_effect = None
    await coordinator.async_refresh()
    assert state_for(hass, entry, "power_grid").state == "21"
    assert coordinator.data.source == "local"


async def test_single_device_failure_does_not_hide_site(hass, clients, entry):
    await setup(hass, entry)
    clients[0].get_thing_states.side_effect = ApiUnavailableError("offline")
    await entry.runtime_data.async_refresh()
    assert state_for(hass, entry, "power_grid").state == "21"
    assert state_for(hass, entry, "battery-1-state_of_charge").state == "unavailable"


async def test_setup_connection_failure_retries(hass, clients, entry):
    clients[0].get_site_configuration.side_effect = ApiUnavailableError("offline")
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state == ConfigEntryState.SETUP_RETRY


async def test_invalid_credentials_trigger_reauth(hass, clients, entry):
    clients[0].get_site_configuration.side_effect = AuthenticationError("invalid")
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.SETUP_ERROR
    assert hass.config_entries.flow.async_progress_by_handler("neoom")


async def test_diagnostics_exclude_secrets_and_identity(hass, clients, entry):
    await setup(hass, entry)
    report = await async_get_config_entry_diagnostics(hass, entry)
    text = str(report)
    for secret in ("local-secret", "beaam.test", "site-1", "battery-1"):
        assert secret not in text
    assert report["devices"][0]["type"] == "BATTERY"
    assert report["polling_intervals"] == {"local_seconds": 20, "cloud_seconds": 120}


@pytest.mark.parametrize("value", [None, True, "bad", float("nan"), float("inf")])
async def test_invalid_measurements_are_unknown(hass, clients, entry, value):
    from neoom_connect import EnergyFlow, State

    clients[0].get_site_state.return_value = EnergyFlow({"POWER_GRID": State("POWER_GRID", value)})
    await setup(hass, entry)
    assert state_for(hass, entry, "power_grid").state == "unknown"


async def test_cloud_only_setup(hass, clients, entry):
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={
            "mode": "cloud",
            "cloud_token": "secret",
            "site_id": "site-1",
        },
    )
    await setup(hass, entry)
    assert state_for(hass, entry, "power_grid").state == "50"
    clients[0].get_site_configuration.assert_not_called()


async def test_hybrid_boots_with_cloud_and_discovers_devices_on_recovery(hass, clients, entry):
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            "mode": "hybrid",
            "cloud_token": "secret",
        },
    )
    clients[0].get_site_configuration.side_effect = ApiUnavailableError("offline")
    await setup(hass, entry)
    assert state_for(hass, entry, "power_grid").state == "50"
    clients[0].get_site_configuration.side_effect = None
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert state_for(hass, entry, "battery-1-state_of_charge").state == "35"
    count = len(hass.states.async_all())
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(hass.states.async_all()) == count


async def test_expired_cloud_cache_does_not_hide_failure(hass, clients, entry):
    from neoom_connect.exceptions import RateLimitError

    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            "mode": "hybrid",
            "cloud_token": "secret",
        },
    )
    clients[0].get_site_state.side_effect = ApiUnavailableError("offline")
    with patch("custom_components.neoom.coordinator.monotonic", return_value=1000):
        await setup(hass, entry)
    clients[1].get_latest_energy_flow.side_effect = RateLimitError(300)
    with patch("custom_components.neoom.coordinator.monotonic", return_value=1121):
        await entry.runtime_data.async_refresh()
    assert state_for(hass, entry, "power_grid").state == "unavailable"
    count = clients[1].get_latest_energy_flow.await_count
    with patch("custom_components.neoom.coordinator.monotonic", return_value=1300):
        await entry.runtime_data.async_refresh()
    assert clients[1].get_latest_energy_flow.await_count == count
