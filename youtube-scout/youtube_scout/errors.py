"""Errors the CLI reports to the user as a clear message and a non-zero exit."""


class ScoutError(Exception):
    """A problem to show the user: missing key, bad config, API error."""


class QuotaStop(ScoutError):
    """The next API call would cross the daily quota limit; stop calling."""


class ApiError(ScoutError):
    """The YouTube Data API answered with an error status."""

    def __init__(self, status: int, reason: str, message: str = ""):
        super().__init__(f"YouTube API error {status} ({reason}): {message}".rstrip(": "))
        self.status = status
        self.reason = reason
