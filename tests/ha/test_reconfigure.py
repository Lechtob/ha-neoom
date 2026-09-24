"""Reconfiguration keeps the site, registry and stored secrets stable."""

from dataclasses import replace
from unittest.mock import patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from neoom_connect import Site
from neoom_connect.exceptions import ApiUnavailableError, AuthenticationError, InvalidResponseError


async def start(hass, entry, mode="local"):
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, "mode": mode, "cloud_token": "cloud-secret"},
        options={"local_interval": 30, "cloud_interval": 180},
    )
    return await hass.config_entries.flow.async_init(
        "neoom", context={"source": "reconfigure", "entry_id": entry.entry_id}
    )


@pytest.mark.parametrize("mode", ["local", "cloud", "hybrid"])
async def test_reconfigure_preserves_identity_and_unspecified_keys(hass, clients, entry, mode):
    form = await start(hass, entry, mode)
    assert form["step_id"] == "reconfigure"
    assert "local-secret" not in str(form["data_schema"])
    assert "cloud-secret" not in str(form["data_schema"])
    payload = {} if mode == "cloud" else {"host": "new-beaam.test/", "local_token": ""}
    if mode != "local":
        payload["cloud_token"] = ""
    with patch("custom_components.neoom.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(form["flow_id"], payload)
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert hass.config_entries.async_get_entry(entry.entry_id) is entry
    assert entry.unique_id == "site-1"
    assert entry.data["site_id"] == "site-1"
    assert entry.data["local_token"] == "local-secret"
    assert entry.data["cloud_token"] == "cloud-secret"
    assert entry.options == {"local_interval": 30, "cloud_interval": 180}
    if mode != "cloud":
        assert entry.data["host"] == "http://new-beaam.test"


@pytest.mark.parametrize("mode", ["local", "cloud", "hybrid"])
async def test_reconfigure_rejects_wrong_site(hass, clients, entry, mode):
    form = await start(hass, entry, mode)
    before = dict(entry.data)
    if mode == "local":
        clients[0].get_site_configuration.return_value = replace(
            clients[0].get_site_configuration.return_value, site_id="another-site"
        )
    else:
        clients[1].get_sites.return_value = [Site("another-site")]
    payload = {} if mode == "cloud" else {"host": "new.test"}
    result = await hass.config_entries.flow.async_configure(form["flow_id"], payload)
    assert result["reason"] == "wrong_site"
    assert dict(entry.data) == before


@pytest.mark.parametrize("mode", ["local", "cloud", "hybrid"])
@pytest.mark.parametrize(
    "error,expected",
    [
        (ApiUnavailableError("offline"), "cannot_connect"),
        (AuthenticationError("invalid"), "invalid_auth"),
        (InvalidResponseError("bad payload"), "invalid_response"),
    ],
)
async def test_failed_validation_never_saves(hass, clients, entry, mode, error, expected):
    form = await start(hass, entry, mode)
    before = dict(entry.data)
    if mode == "local":
        clients[0].get_site_configuration.side_effect = error
    else:
        clients[1].get_sites.side_effect = error
    payload = {"cloud_token": "replacement"} if mode == "cloud" else {"host": "new.test"}
    result = await hass.config_entries.flow.async_configure(form["flow_id"], payload)
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": expected}
    assert dict(entry.data) == before


async def test_reconfigure_replaces_keys_after_both_validations(hass, clients, entry):
    form = await start(hass, entry, "hybrid")
    with patch("custom_components.neoom.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"],
            {
                "host": "https://beaam.test",
                "local_token": "new-local",
                "cloud_token": "new-cloud",
            },
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["local_token"] == "new-local"
    assert entry.data["cloud_token"] == "new-cloud"
    assert entry.data["host"] == "https://beaam.test"


async def test_invalid_host_does_not_save(hass, clients, entry):
    form = await start(hass, entry)
    before = dict(entry.data)
    result = await hass.config_entries.flow.async_configure(form["flow_id"], {"host": "ftp://bad"})
    assert result["errors"] == {"host": "invalid_host"}
    assert dict(entry.data) == before
