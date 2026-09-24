"""Client for the local BEAAM API."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlsplit

from ._client import BaseClient, HttpSession
from .exceptions import CommandRejectedError
from .models import Command, CommandResult, EnergyFlow, SiteConfiguration, State, parse_states


class BeaamLocalClient(BaseClient):
    """Async client for a local BEAAM device."""

    def __init__(
        self,
        host: str,
        token: str,
        *,
        session: HttpSession | None = None,
        timeout: int = 30,
    ) -> None:
        super().__init__(normalize_host(host), token=token, session=session, timeout=timeout)

    async def get_site_configuration(self) -> SiteConfiguration:
        data = await self._request_json("GET", "/api/v1/site/configuration")
        return SiteConfiguration.from_api(data)

    async def get_site_state(self, keys: list[str] | None = None) -> EnergyFlow:
        data = await self._request_json("GET", "/api/v1/site/state", params=_keys_params(keys))
        return EnergyFlow.from_local_state(data)

    async def get_thing_states(
        self, thing_id: str, keys: list[str] | None = None
    ) -> dict[str, State]:
        data = await self._request_json(
            "GET", f"/api/v1/things/{quote(thing_id, safe='')}/states", params=_keys_params(keys)
        )
        return parse_states(data)

    async def get_thing_settings(self, thing_id: str) -> dict[str, Any]:
        data = await self._request_json("GET", f"/api/v1/things/{thing_id}/settings")
        return data.get("settings", {})

    async def call_thing_commands(
        self, thing_id: str, commands: list[Command]
    ) -> list[CommandResult]:
        payload = [command.to_api() for command in commands]
        data = await self._request_json("POST", f"/api/v1/things/{thing_id}/commands", json=payload)
        results = [CommandResult.from_api(item) for item in data]
        rejected = [result for result in results if result.status not in {"SUCCESSFUL", "PENDING"}]
        if rejected:
            first = rejected[0]
            raise CommandRejectedError(
                first.message or f"Command {first.key} was {first.status.lower()}"
            )
        return results

    async def update_thing_states(self, thing_id: str, states: list[Command]) -> None:
        payload = [state.to_api() for state in states]
        await self._request_json("POST", f"/api/v1/things/{thing_id}/states", json=payload)

    async def get_external_plant_controls(self) -> dict[str, Any]:
        return await self._request_json("GET", "/api/v1/externalPlantControls")

    async def get_external_plant_control_states(
        self,
        external_plant_control_id: str,
        *,
        keys: list[str] | None = None,
        liveness_update: bool = False,
    ) -> dict[str, State]:
        params = _keys_params(keys) or {}
        params["livenessUpdate"] = str(liveness_update).lower()
        data = await self._request_json(
            "GET",
            f"/api/v1/externalPlantControls/{external_plant_control_id}/states",
            params=params,
        )
        states = [State.from_api(item) for item in data.get("states", [])]
        return {state.key: state for state in states}


def _keys_params(keys: list[str] | None) -> dict[str, str] | None:
    if not keys:
        return None
    return {"keys": ",".join(keys)}


def normalize_host(host: str) -> str:
    """Validate the endpoint and preserve an explicitly selected HTTPS scheme."""
    url = urlsplit(host.strip() if "://" in host else f"http://{host.strip()}")
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
        or any(char.isspace() for char in url.netloc)
    ):
        raise ValueError("Expected a BEAAM host or HTTP(S) origin")
    port = url.port
    hostname = url.hostname.lower()
    if ":" in hostname:
        hostname = f"[{hostname}]"
    suffix = f":{port}" if port and port != {"http": 80, "https": 443}[url.scheme] else ""
    return f"{url.scheme}://{hostname}{suffix}"
