"""Configuration uses API site identity and validates credentials."""

from unittest.mock import patch

import pytest
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from neoom_connect.exceptions import ApiUnavailableError, AuthenticationError, InvalidResponseError


async def start(hass, mode):
    result = await hass.config_entries.flow.async_init("neoom", context={"source": "user"})
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"mode": mode})


async def test_local_config_flow(hass, clients):
    result = await start(hass, "local")
    with patch("custom_components.neoom.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "BEAAM.test/",
                "local_token": "secret",
            },
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == "http://beaam.test"
    assert result["result"].unique_id == "site-1"


async def test_cloud_site_selection(hass, clients):
    result = await start(hass, "cloud")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"cloud_token": "secret"}
    )
    assert result["step_id"] == "site"
    with patch("custom_components.neoom.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"site_id": "site-2"}
        )
        await hass.async_block_till_done()
    assert result["title"] == "Office"
    assert result["data"]["site_id"] == "site-2"


async def test_hybrid_rejects_unrelated_cloud_site(hass, clients):
    clients[1].get_sites.return_value = []
    result = await start(hass, "hybrid")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "beaam.test",
            "local_token": "secret",
        },
    )
    from neoom_connect import Site

    clients[1].get_sites.return_value = [Site("other")]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"cloud_token": "secret"}
    )
    assert result["errors"] == {"base": "site_mismatch"}


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (AuthenticationError("bad key"), "invalid_auth"),
        (ApiUnavailableError("offline"), "cannot_connect"),
        (InvalidResponseError("bad schema"), "invalid_response"),
    ],
)
async def test_local_errors(hass, clients, error, message):
    clients[0].get_site_configuration.side_effect = error
    result = await start(hass, "local")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "beaam.test",
            "local_token": "secret",
        },
    )
    assert result["errors"] == {"base": message}


async def test_duplicate_site_across_modes(hass, clients, entry):
    entry.add_to_hass(hass)
    result = await start(hass, "cloud")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"cloud_token": "secret"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"site_id": "site-1"}
    )
    assert result["reason"] == "already_configured"


async def test_options_reject_invalid_interval(hass, entry):
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"local_interval": 0, "cloud_interval": 10},
        )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "local_interval": 30,
            "cloud_interval": 300,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == {"local_interval": 30, "cloud_interval": 300}


async def test_reauth_preserves_entry_id(hass, clients, entry):
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        "neoom",
        context={
            "source": "reauth",
            "entry_id": entry.entry_id,
        },
        data=dict(entry.data),
    )
    with patch("custom_components.neoom.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "new-beaam.test",
                "local_token": "replacement-secret",
            },
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.data["local_token"] == "replacement-secret"
    assert hass.config_entries.async_get_entry(entry.entry_id) is entry


async def test_reauth_rejects_another_site(hass, clients, entry):
    from dataclasses import replace

    clients[0].get_site_configuration.return_value = replace(
        clients[0].get_site_configuration.return_value, site_id="other"
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        "neoom",
        context={
            "source": "reauth",
            "entry_id": entry.entry_id,
        },
        data=dict(entry.data),
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "other.test",
            "local_token": "replacement-secret",
        },
    )
    assert result["reason"] == "wrong_site"
    assert entry.data["local_token"] == "local-secret"


async def test_cloud_empty_sites(hass, clients):
    clients[1].get_sites.return_value = []
    result = await start(hass, "cloud")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "cloud_token": "secret",
        },
    )
    assert result["errors"] == {"base": "no_sites"}
