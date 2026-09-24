"""Transport boundary failures and caller-owned session contracts."""

from unittest.mock import AsyncMock

import aiohttp
import pytest
from neoom_connect import BeaamLocalClient, NeoomCloudClient
from neoom_connect.exceptions import (
    ApiError,
    ApiUnavailableError,
    AuthenticationError,
    InvalidResponseError,
    RateLimitError,
)
from neoom_connect.local import normalize_host
from test_clients import FakeSession


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (403, AuthenticationError),
        (429, RateLimitError),
        (500, ApiUnavailableError),
        (503, ApiUnavailableError),
        (302, ApiError),
    ],
)
async def test_status_mapping(status, error):
    session = FakeSession()
    session.add("GET", "https://api.ntuity.io/v1/sites/", status, {"token": "private"})
    with pytest.raises(error) as caught:
        await NeoomCloudClient("secret", session=session).get_sites()
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("error", [TimeoutError(), aiohttp.ClientConnectionError()])
async def test_transport_failures_are_library_errors(error):
    class Session:
        def request(self, *args, **kwargs):
            raise error

    with pytest.raises(ApiUnavailableError):
        await NeoomCloudClient("secret", session=Session()).get_sites()


async def test_external_session_timeout_and_ownership():
    session = FakeSession()
    session.close = AsyncMock()
    session.add("GET", "https://beaam.test/api/v1/site/state", 200, {"energyFlow": {"states": []}})
    async with BeaamLocalClient(
        "https://beaam.test", "secret", session=session, timeout=3
    ) as client:
        await client.get_site_state()
    assert session.calls[0][2]["timeout"].total == 3
    assert session.calls[0][2]["allow_redirects"] is False
    session.close.assert_not_called()


async def test_invalid_json_is_not_a_connectivity_failure():
    session = FakeSession()
    session.add("GET", "https://api.ntuity.io/v1/sites/", 200, {})
    session.responses[("GET", "https://api.ntuity.io/v1/sites/")].json = AsyncMock(
        side_effect=ValueError("bad JSON")
    )
    with pytest.raises(InvalidResponseError):
        await NeoomCloudClient("secret", session=session).get_sites()


@pytest.mark.parametrize(
    "host", ["http://user:pass@host", "http://host/api", "ftp://host", "host:bad"]
)
def test_invalid_host(host):
    with pytest.raises(ValueError):
        normalize_host(host)


def test_host_normalization():
    assert normalize_host("https://BEAAM.test:443/") == "https://beaam.test"
    assert normalize_host("192.0.2.1") == "http://192.0.2.1"
