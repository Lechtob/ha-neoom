"""Shared HTTP client primitives."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Protocol, Self

import aiohttp

from .exceptions import (
    ApiError,
    ApiUnavailableError,
    AuthenticationError,
    InvalidResponseError,
    NotFoundError,
    RateLimitError,
)


class HttpResponse(Protocol):
    status: int

    async def json(self) -> Any: ...

    async def text(self) -> str: ...


class HttpRequestContext(Protocol):
    async def __aenter__(self) -> HttpResponse: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class HttpSession(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> HttpRequestContext: ...

    async def close(self) -> None: ...


class BaseClient:
    """Small aiohttp-compatible base client."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str,
        session: HttpSession | None = None,
        timeout: int = 30,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._session = session
        self._own_session = False
        self._timeout = timeout

    async def __aenter__(self) -> Self:
        if self._session is None:
            import aiohttp

            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout)
            )
            self._own_session = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        if self._own_session and self._session is not None:
            await self._session.close()
        self._session = None
        self._own_session = False

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> Any:
        if self._session is None:
            await self.__aenter__()

        assert self._session is not None
        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        kwargs: dict[str, Any] = {
            "headers": headers,
            "timeout": aiohttp.ClientTimeout(total=self._timeout),
            "allow_redirects": False,
        }
        if params:
            kwargs["params"] = params
        if json is not None:
            kwargs["json"] = json

        try:
            async with self._session.request(method, url, **kwargs) as response:
                if response.status in {401, 403}:
                    raise AuthenticationError("Authentication failed", status=response.status)
                if response.status == 404:
                    raise NotFoundError("Resource not found", status=response.status)
                if response.status == 429:
                    retry = getattr(response, "headers", {}).get("Retry-After", "120")
                    raise RateLimitError(int(retry) if str(retry).isdigit() else 120)
                if response.status >= 500:
                    raise ApiUnavailableError("API is unavailable", status=response.status)
                if response.status >= 300:
                    raise ApiError("Unexpected API response", status=response.status)
                if response.status == 204:
                    return None
                try:
                    return await response.json()
                except (ValueError, aiohttp.ContentTypeError) as err:
                    raise InvalidResponseError("API did not return valid JSON") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ApiUnavailableError("Could not reach API") from err
