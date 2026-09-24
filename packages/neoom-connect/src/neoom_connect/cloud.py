"""Client for the neoom CONNECT cloud API."""

from __future__ import annotations

from urllib.parse import quote

from ._client import BaseClient, HttpSession
from .exceptions import InvalidResponseError
from .models import EnergyFlow, Site


class NeoomCloudClient(BaseClient):
    """Async client for the public ntuity cloud API."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://api.ntuity.io/v1",
        session: HttpSession | None = None,
        timeout: int = 30,
    ) -> None:
        super().__init__(base_url, token=token, session=session, timeout=timeout)

    async def get_sites(self) -> list[Site]:
        data = await self._request_json("GET", "/sites/")
        if not isinstance(data, dict) or not isinstance(data.get("sites"), list):
            raise InvalidResponseError("Missing sites list")
        try:
            return [Site.from_cloud(site) for site in data["sites"]]
        except (KeyError, TypeError, AttributeError) as err:
            raise InvalidResponseError("Invalid site") from err

    async def get_site(self, site_id: str) -> Site:
        data = await self._request_json("GET", f"/sites/{site_id}")
        return Site.from_cloud(data)

    async def get_latest_energy_flow(self, site_id: str) -> EnergyFlow:
        data = await self._request_json(
            "GET", f"/sites/{quote(site_id, safe='')}/energy-flow/latest"
        )
        return EnergyFlow.from_cloud(data)
