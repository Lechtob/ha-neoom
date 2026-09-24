"""Local-first monitoring with a bounded cloud fallback."""

import logging
from dataclasses import dataclass
from datetime import timedelta
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from neoom_connect import BeaamLocalClient, EnergyFlow, NeoomCloudClient, SiteConfiguration, State
from neoom_connect.exceptions import (
    ApiUnavailableError,
    AuthenticationError,
    InvalidResponseError,
    NeoomConnectError,
    RateLimitError,
)

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

LOGGER = logging.getLogger(__name__)


@dataclass
class NeoomData:
    flow: EnergyFlow
    things: dict[str, dict[str, State]]
    source: str


class NeoomCoordinator(DataUpdateCoordinator[NeoomData]):
    """Poll locally; cloud readings never fill missing local energy counters."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.mode = entry.data[CONF_MODE]
        self.site_id = entry.data.get(CONF_SITE_ID)
        self.configuration: SiteConfiguration | None = None
        self.local_interval = entry.options.get("local_interval", 20)
        self.cloud_interval = entry.options.get("cloud_interval", 120)
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(
                seconds=(self.cloud_interval if self.mode == MODE_CLOUD else self.local_interval)
            ),
        )
        session = async_get_clientsession(hass)
        self.local = (
            BeaamLocalClient(
                entry.data[CONF_HOST], entry.data[CONF_LOCAL_TOKEN], session=session, timeout=10
            )
            if self.mode in {MODE_LOCAL, MODE_HYBRID}
            else None
        )
        self.cloud = (
            NeoomCloudClient(entry.data[CONF_CLOUD_TOKEN], session=session, timeout=20)
            if self.mode in {MODE_CLOUD, MODE_HYBRID}
            else None
        )
        self._next_cloud = 0.0
        self._cloud_cache: EnergyFlow | None = None

    async def _local_data(self) -> NeoomData:
        assert self.local is not None
        if self.configuration is None:
            configuration = await self.local.get_site_configuration()
            if self.site_id and configuration.site_id != self.site_id:
                raise InvalidResponseError("BEAAM belongs to a different site")
            self.configuration = configuration
            self.site_id = configuration.site_id
        flow = await self.local.get_site_state()
        things = {}
        # Sequential device reads avoid overwhelming small BEAAM installations.
        for thing_id in self.configuration.things:
            try:
                things[thing_id] = await self.local.get_thing_states(thing_id)
            except AuthenticationError:
                raise
            except NeoomConnectError:
                things[thing_id] = {}
        return NeoomData(flow, things, MODE_LOCAL)

    async def _cloud_data(self) -> NeoomData:
        assert self.cloud is not None and self.site_id
        now = monotonic()
        if now < self._next_cloud:
            if self._cloud_cache is None:
                raise ApiUnavailableError("Cloud retry interval has not elapsed")
            return NeoomData(self._cloud_cache, {}, MODE_CLOUD)
        self._next_cloud = now + self.cloud_interval
        self._cloud_cache = None
        try:
            self._cloud_cache = await self.cloud.get_latest_energy_flow(self.site_id)
        except RateLimitError as err:
            self._next_cloud = now + max(self.cloud_interval, err.retry_after)
            raise
        return NeoomData(self._cloud_cache, {}, MODE_CLOUD)

    async def _async_update_data(self) -> NeoomData:
        try:
            if self.local is not None:
                try:
                    return await self._local_data()
                except ApiUnavailableError:
                    if self.cloud is None:
                        raise
            return await self._cloud_data()
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed("Check the neoom API credentials") from err
        except NeoomConnectError as err:
            raise UpdateFailed(str(err)) from err
