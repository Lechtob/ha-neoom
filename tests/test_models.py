from datetime import UTC, datetime

import pytest
from neoom_connect.exceptions import InvalidResponseError
from neoom_connect.models import EnergyFlow, SiteConfiguration, State


def test_state_converts_timestamp_ms_to_datetime() -> None:
    state = State.from_api(
        {
            "dataPointId": "dp-1",
            "key": "STATE_OF_CHARGE",
            "value": 87,
            "ts": 1_704_812_665_002,
        }
    )

    assert state.timestamp == datetime(2024, 1, 9, 15, 4, 25, 2000, tzinfo=UTC)


def test_site_configuration_parses_things_and_energy_flow_metadata() -> None:
    configuration = SiteConfiguration.from_api(
        {
            "siteId": "site-1",
            "things": {
                "thing-1": {
                    "type": "BATTERY",
                    "dataPoints": {
                        "dp-1": {
                            "key": "STATE_OF_CHARGE",
                            "dataType": "NUMBER",
                            "unitOfMeasure": "%",
                            "controllable": False,
                        }
                    },
                }
            },
            "energyFlow": {
                "dataPoints": {
                    "ef-1": {
                        "key": "POWER_GRID",
                        "dataType": "NUMBER",
                        "unitOfMeasure": "W",
                    }
                }
            },
        }
    )

    assert configuration.site_id == "site-1"
    assert configuration.things["thing-1"].type == "BATTERY"
    assert configuration.things["thing-1"].data_points["dp-1"].unit == "%"
    assert configuration.energy_flow_data_points["ef-1"].key == "POWER_GRID"


def test_local_energy_flow_parses_states_by_key() -> None:
    energy_flow = EnergyFlow.from_local_state(
        {
            "energyFlow": {
                "states": [
                    {
                        "dataPointId": "dp-1",
                        "key": "POWER_GRID",
                        "value": -1200,
                        "ts": 1_704_812_665_002,
                    }
                ]
            }
        }
    )

    assert energy_flow.states["POWER_GRID"].value == -1200


def test_cloud_energy_flow_normalizes_snake_case_keys() -> None:
    energy_flow = EnergyFlow.from_cloud(
        {
            "power_grid": {"value": -100, "time": "2026-09-24T17:00:00Z"},
            "state_of_charge": {"value": 45, "time": None},
        }
    )

    assert energy_flow.states["POWER_GRID"].value == -100
    assert energy_flow.states["STATE_OF_CHARGE"].value == 45
    assert energy_flow.states["POWER_GRID"].timestamp == datetime(2026, 9, 24, 17, tzinfo=UTC)


@pytest.mark.parametrize("payload", [[], {}, {"energyFlow": {"states": {}}}])
def test_invalid_local_envelope(payload):
    with pytest.raises(InvalidResponseError):
        EnergyFlow.from_local_state(payload)


def test_cloud_null_values_and_metadata():
    flow = EnergyFlow.from_cloud(
        {
            "power_grid": {"value": None, "time": None},
            "storages_online_count": 1,
        }
    )
    assert flow.states["POWER_GRID"].value is None
    assert "STORAGES_ONLINE_COUNT" not in flow.states


def test_negative_timestamp_is_uninitialized():
    assert State.from_api({"key": "VOLTAGE", "value": None, "ts": -1}).timestamp is None
