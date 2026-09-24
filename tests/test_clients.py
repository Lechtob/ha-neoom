from __future__ import annotations

from typing import Any

import pytest
from neoom_connect import BeaamLocalClient, Command, NeoomCloudClient
from neoom_connect.exceptions import AuthenticationError, CommandRejectedError


class FakeResponse:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    async def json(self) -> Any:
        return self._payload

    async def text(self) -> str:
        return str(self._payload)


class FakeRequestContext:
    def __init__(self, response: FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> FakeResponse:
        return self._response

    async def __aexit__(self, *_: Any) -> None:
        return None


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.responses: dict[tuple[str, str], FakeResponse] = {}

    def add(self, method: str, url: str, status: int, payload: Any) -> None:
        self.responses[(method, url)] = FakeResponse(status, payload)

    def request(self, method: str, url: str, **kwargs: Any) -> FakeRequestContext:
        self.calls.append((method, url, kwargs))
        return FakeRequestContext(self.responses[(method, url)])

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_cloud_client_get_sites() -> None:
    session = FakeSession()
    session.add(
        "GET",
        "https://api.ntuity.io/v1/sites/",
        200,
        {"sites": [{"id": "site-1", "name": "Home"}]},
    )

    client = NeoomCloudClient("token", session=session)
    sites = await client.get_sites()

    assert sites[0].id == "site-1"
    assert session.calls[0][2]["headers"]["Authorization"] == "Bearer token"


@pytest.mark.asyncio
async def test_local_client_get_site_state() -> None:
    session = FakeSession()
    session.add(
        "GET",
        "http://192.0.2.10/api/v1/site/state",
        200,
        {
            "energyFlow": {
                "states": [
                    {
                        "dataPointId": "dp-1",
                        "key": "POWER_STORAGE",
                        "value": 300,
                        "ts": 1_704_812_665_002,
                    }
                ]
            }
        },
    )

    client = BeaamLocalClient("192.0.2.10", "local-token", session=session)
    energy_flow = await client.get_site_state()

    assert energy_flow.states["POWER_STORAGE"].value == 300


@pytest.mark.asyncio
async def test_local_client_sends_command_payload() -> None:
    session = FakeSession()
    session.add(
        "POST",
        "http://192.0.2.10/api/v1/things/battery-1/commands",
        200,
        [{"key": "TARGET_POWER", "status": "SUCCESSFUL"}],
    )

    client = BeaamLocalClient("192.0.2.10", "local-token", session=session)
    results = await client.call_thing_commands("battery-1", [Command("TARGET_POWER", 500)])

    assert results[0].status == "SUCCESSFUL"
    assert session.calls[0][2]["json"] == [{"key": "TARGET_POWER", "value": 500}]


@pytest.mark.asyncio
async def test_local_client_raises_for_rejected_command() -> None:
    session = FakeSession()
    session.add(
        "POST",
        "http://192.0.2.10/api/v1/things/battery-1/commands",
        200,
        [{"key": "TARGET_POWER", "status": "REJECTED", "message": "out of range"}],
    )

    client = BeaamLocalClient("192.0.2.10", "local-token", session=session)

    with pytest.raises(CommandRejectedError):
        await client.call_thing_commands("battery-1", [Command("TARGET_POWER", 999999)])


@pytest.mark.asyncio
async def test_client_maps_401_to_authentication_error() -> None:
    session = FakeSession()
    session.add("GET", "https://api.ntuity.io/v1/sites/", 401, {"message": "nope"})

    client = NeoomCloudClient("bad-token", session=session)

    with pytest.raises(AuthenticationError):
        await client.get_sites()
