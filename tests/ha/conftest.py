"""Actual HA runtime with mocked neoom transport; no Linux runner dependency."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import loader
from homeassistant.helpers import frame
from neoom_connect import BeaamLocalClient, EnergyFlow, NeoomCloudClient, Site, SiteConfiguration
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_test_home_assistant,
)


@pytest.fixture
async def hass(tmp_path):
    async with async_test_home_assistant(config_dir=str(tmp_path)) as instance:
        instance.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)
        frame.async_setup(instance)
        try:
            yield instance
        finally:
            await instance.async_stop(force=True)
            await instance.async_block_till_done()
            frame.async_setup(None)


@pytest.fixture
def clients():
    local = AsyncMock(spec=BeaamLocalClient)
    cloud = AsyncMock(spec=NeoomCloudClient)
    local.get_site_configuration.return_value = SiteConfiguration.from_api(
        {
            "siteId": "site-1",
            "energyFlow": {"dataPoints": {}},
            "things": {
                "battery-1": {
                    "type": "BATTERY",
                    "name": "Battery",
                    "dataPoints": {
                        "soc": {
                            "key": "STATE_OF_CHARGE",
                            "dataType": "NUMBER",
                            "unitOfMeasure": "%",
                        },
                        "online": {
                            "key": "CONNECTION",
                            "dataType": "BOOLEAN",
                            "unitOfMeasure": "None",
                        },
                    },
                }
            },
        }
    )
    local.get_site_state.return_value = EnergyFlow.from_local_state(
        {
            "energyFlow": {
                "states": [
                    {"key": "POWER_GRID", "value": 21, "ts": 1_700_000_000_000},
                    {"key": "ENERGY_IMPORTED", "value": 22711605, "ts": 1_700_000_000_000},
                ]
            }
        }
    )
    local.get_thing_states.return_value = EnergyFlow.from_local_state(
        {
            "energyFlow": {
                "states": [
                    {"key": "STATE_OF_CHARGE", "value": 35, "ts": 1_700_000_000_000},
                    {"key": "CONNECTION", "value": True, "ts": 1_700_000_000_000},
                ]
            }
        }
    ).states
    cloud.get_sites.return_value = [Site("site-1", "Home"), Site("site-2", "Office")]
    cloud.get_latest_energy_flow.return_value = EnergyFlow.from_cloud(
        {
            "power_grid": {"value": 50, "time": "2026-09-24T17:00:00Z"},
        }
    )
    with (
        patch("custom_components.neoom.coordinator.async_get_clientsession", return_value=None),
        patch("custom_components.neoom.config_flow.async_get_clientsession", return_value=None),
        patch("custom_components.neoom.coordinator.BeaamLocalClient", return_value=local),
        patch("custom_components.neoom.coordinator.NeoomCloudClient", return_value=cloud),
        patch("custom_components.neoom.config_flow.BeaamLocalClient", return_value=local),
        patch("custom_components.neoom.config_flow.NeoomCloudClient", return_value=cloud),
    ):
        yield local, cloud


@pytest.fixture
def entry():
    return MockConfigEntry(
        domain="neoom",
        title="neoom",
        unique_id="site-1",
        data={
            "mode": "local",
            "host": "http://beaam.test",
            "local_token": "local-secret",
            "site_id": "site-1",
        },
    )
