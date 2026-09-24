"""Exception hierarchy for py-neoom-connect."""


class NeoomConnectError(Exception):
    """Base error for this package."""


class ApiError(NeoomConnectError):
    """Raised for unexpected API responses."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class AuthenticationError(ApiError):
    """Raised when credentials are invalid or missing."""


class NotFoundError(ApiError):
    """Raised when a requested resource does not exist."""


class ApiUnavailableError(ApiError):
    """Raised when the API is temporarily unavailable."""


class CommandRejectedError(ApiError):
    """Raised when the BEAAM API rejects a command."""


class InvalidResponseError(ApiError):
    """The API returned malformed data."""


class RateLimitError(ApiUnavailableError):
    """The API requested a pause before the next request."""

    def __init__(self, retry_after: int = 120) -> None:
        super().__init__("API rate limit reached", status=429)
        self.retry_after = retry_after
