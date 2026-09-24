"""Set up a site using local BEAAM, cloud, or both."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from neoom_connect import BeaamLocalClient, NeoomCloudClient
from neoom_connect.exceptions import AuthenticationError, InvalidResponseError, NeoomConnectError
from neoom_connect.local import normalize_host

from .const import (
    CONF_CLOUD_TOKEN,
    CONF_LOCAL_TOKEN,
    CONF_MODE,
    CONF_SITE_ID,
    DOMAIN,
    MODE_CLOUD,
    MODE_HYBRID,
    MODE_LOCAL,
)

PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class NeoomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Select a real site and prevent duplicate connections across modes."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._sites: dict[str, str] = {}
        self._local_site: str | None = None
        self._reauth_entry = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NeoomOptionsFlow()

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._data[CONF_MODE] = user_input[CONF_MODE]
            if user_input[CONF_MODE] == MODE_CLOUD:
                return await self.async_step_cloud()
            return await self.async_step_local()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MODE, default=MODE_LOCAL): vol.In(
                        {
                            MODE_LOCAL: "Local BEAAM",
                            MODE_CLOUD: "Cloud",
                            MODE_HYBRID: "Hybrid",
                        }
                    ),
                }
            ),
        )

    async def async_step_local(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                host = normalize_host(user_input[CONF_HOST])
                client = BeaamLocalClient(
                    host,
                    user_input[CONF_LOCAL_TOKEN],
                    session=async_get_clientsession(self.hass),
                    timeout=10,
                )
                config = await client.get_site_configuration()
                if self._reauth_entry and self._reauth_entry.data.get(CONF_SITE_ID) not in {
                    None,
                    config.site_id,
                }:
                    return self.async_abort(reason="wrong_site")
                self._local_site = config.site_id
                self._data.update(user_input)
                self._data[CONF_HOST] = host
                self._data[CONF_SITE_ID] = config.site_id
                if self._data[CONF_MODE] == MODE_HYBRID:
                    return await self.async_step_cloud()
                return await self._finish(config.site_id, "neoom BEAAM")
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except InvalidResponseError:
                errors["base"] = "invalid_response"
            except NeoomConnectError:
                errors["base"] = "cannot_connect"
            except ValueError:
                errors[CONF_HOST] = "invalid_host"
        return self.async_show_form(
            step_id="local",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self._data.get(CONF_HOST, "")): str,
                    vol.Required(CONF_LOCAL_TOKEN): PASSWORD,
                }
            ),
        )

    async def async_step_cloud(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                client = NeoomCloudClient(
                    user_input[CONF_CLOUD_TOKEN], session=async_get_clientsession(self.hass)
                )
                sites = await client.get_sites()
                self._sites = {site.id: site.name or site.id for site in sites}
                self._data.update(user_input)
                if not self._sites:
                    errors["base"] = "no_sites"
                elif self._local_site and self._local_site not in self._sites:
                    errors["base"] = "site_mismatch"
                else:
                    return await self.async_step_site()
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except InvalidResponseError:
                errors["base"] = "invalid_response"
            except NeoomConnectError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="cloud",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CLOUD_TOKEN): PASSWORD,
                }
            ),
        )

    async def async_step_site(self, user_input=None):
        sites = self._sites
        if self._local_site:
            sites = {self._local_site: sites[self._local_site]}
        if self._reauth_entry and self._reauth_entry.data.get(CONF_SITE_ID):
            original = self._reauth_entry.data[CONF_SITE_ID]
            if original not in sites:
                return self.async_abort(reason="wrong_site")
            sites = {original: sites[original]}
        if user_input is not None:
            site_id = user_input[CONF_SITE_ID]
            if site_id not in sites:
                return self.async_abort(reason="wrong_site")
            return await self._finish(site_id, sites[site_id])
        return self.async_show_form(
            step_id="site",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SITE_ID, default=next(iter(sites))): vol.In(sites),
                }
            ),
        )

    async def _finish(self, site_id, title):
        self._data[CONF_SITE_ID] = site_id
        if self._reauth_entry:
            return self.async_update_reload_and_abort(self._reauth_entry, data=self._data)
        await self.async_set_unique_id(site_id)
        self._abort_if_unique_id_configured()
        for entry in self._async_current_entries():
            if entry.data.get(CONF_SITE_ID) == site_id:
                return self.async_abort(reason="already_configured")
            if (
                entry.data.get(CONF_HOST)
                and self._data.get(CONF_HOST)
                and normalize_host(entry.data[CONF_HOST]) == self._data[CONF_HOST]
            ):
                return self.async_abort(reason="already_configured")
        return self.async_create_entry(title=title, data=self._data)

    async def async_step_reauth(self, entry_data):
        self._reauth_entry = self._get_reauth_entry()
        self._data = dict(self._reauth_entry.data)
        if self._data[CONF_MODE] == MODE_CLOUD:
            return await self.async_step_cloud()
        return await self.async_step_local()

    async def async_step_reconfigure(self, user_input=None):
        """Validate replacement connection settings without changing site identity."""
        entry = self._get_reconfigure_entry()
        mode = entry.data[CONF_MODE]
        errors = {}
        if user_input is not None:
            updates = dict(user_input)
            # Empty password fields retain the existing secret; never echo it in the form.
            for key in (CONF_LOCAL_TOKEN, CONF_CLOUD_TOKEN):
                if not updates.get(key):
                    updates.pop(key, None)
            data = {**entry.data, **updates}
            try:
                if mode != MODE_CLOUD:
                    updates[CONF_HOST] = normalize_host(data[CONF_HOST])
                    local = BeaamLocalClient(
                        updates[CONF_HOST],
                        data[CONF_LOCAL_TOKEN],
                        session=async_get_clientsession(self.hass),
                        timeout=10,
                    )
                    site = await local.get_site_configuration()
                    if site.site_id != entry.data[CONF_SITE_ID]:
                        return self.async_abort(reason="wrong_site")
                if mode != MODE_LOCAL:
                    cloud = NeoomCloudClient(
                        data[CONF_CLOUD_TOKEN], session=async_get_clientsession(self.hass)
                    )
                    sites = await cloud.get_sites()
                    if entry.data[CONF_SITE_ID] not in {site.id for site in sites}:
                        return self.async_abort(reason="wrong_site")
                return self.async_update_reload_and_abort(entry, data_updates=updates)
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except InvalidResponseError:
                errors["base"] = "invalid_response"
            except NeoomConnectError:
                errors["base"] = "cannot_connect"
            except ValueError:
                errors[CONF_HOST] = "invalid_host"
        fields = {}
        if mode != MODE_CLOUD:
            fields[vol.Required(CONF_HOST, default=entry.data[CONF_HOST])] = str
            fields[vol.Optional(CONF_LOCAL_TOKEN)] = PASSWORD
        if mode != MODE_LOCAL:
            fields[vol.Optional(CONF_CLOUD_TOKEN)] = PASSWORD
        return self.async_show_form(
            step_id="reconfigure", data_schema=vol.Schema(fields), errors=errors
        )


class NeoomOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "local_interval",
                        default=self.config_entry.options.get("local_interval", 20),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                    vol.Required(
                        "cloud_interval",
                        default=self.config_entry.options.get("cloud_interval", 120),
                    ): vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
                }
            ),
        )
