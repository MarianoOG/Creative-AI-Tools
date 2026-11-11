"""A quota-aware, read-only client for the official YouTube Data API v3.

Only ``GET`` requests to ``https://www.googleapis.com/youtube/v3`` are made, for
the methods in ``COSTS``. Every call is charged against a per-day ledger in
``state/quota-<day>.json`` *before* it is sent; a call that would take the day's
usage past the stop limit (80% of the daily quota by default) raises
``QuotaStop`` instead.

The transport is swappable: tests use recorded fixtures and never reach the
network.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Protocol

import requests

from .errors import ApiError, QuotaStop, ScoutError
from .state import quota_day, read_json, write_json

API_ROOT = "https://www.googleapis.com/youtube/v3"

#: Quota units per call (https://developers.google.com/youtube/v3/determine_quota_cost).
COSTS: dict[str, int] = {
    "search": 100,
    "channels": 1,
    "playlistItems": 1,
    "videos": 1,
    "commentThreads": 1,
    "channelSections": 1,
    "subscriptions": 1,
}


class Transport(Protocol):
    def get(self, method: str, params: dict[str, Any]) -> dict: ...


class HttpTransport:
    """Real HTTP calls with the user's own API key."""

    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()

    def get(self, method: str, params: dict[str, Any]) -> dict:
        try:
            response = self.session.get(
                f"{API_ROOT}/{method}", params={**params, "key": self.api_key}, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise ScoutError(f"Network error calling YouTube {method}: {exc}") from exc
        if response.status_code != 200:
            reason, message = "unknown", response.text[:200]
            try:
                error = response.json().get("error", {})
                message = error.get("message", message)
                reason = (error.get("errors") or [{}])[0].get("reason", reason)
            except ValueError:
                pass
            raise ApiError(response.status_code, reason, message)
        return response.json()


class QuotaLedger:
    """Units used per method today, persisted so separate runs share the budget."""

    def __init__(self, state_dir: Path, limit: int, day: str | None = None):
        self.limit = limit
        self.day = day or quota_day()
        self.path = state_dir / f"quota-{self.day}.json"
        data = read_json(self.path, {})
        self.by_method: Counter = Counter(data.get("by_method", {}))
        self.session: Counter = Counter()  # This process only, for the run summary

    @property
    def used(self) -> int:
        return sum(self.by_method.values())

    def charge(self, method: str) -> None:
        cost = COSTS[method]
        if self.used + cost > self.limit:
            raise QuotaStop(
                f"Stopping: {method} would use {cost} units and today's usage is {self.used} "
                f"of the {self.limit}-unit limit."
            )
        self.by_method[method] += cost
        self.session[method] += cost
        write_json(self.path, {"day": self.day, "limit": self.limit, "by_method": dict(self.by_method)})


class YouTube:
    """The read-only API methods the scout needs. Each returns parsed JSON."""

    def __init__(self, transport: Transport, ledger: QuotaLedger):
        self.transport = transport
        self.ledger = ledger

    def _get(self, method: str, **params: Any) -> dict:
        if method not in COSTS:
            raise ScoutError(f"Unsupported API method: {method}")
        self.ledger.charge(method)
        return self.transport.get(method, {k: v for k, v in params.items() if v is not None})

    # search.list, 100 units ------------------------------------------------
    def search_recent_videos(
        self, query: str, published_after: str, language: str | None, max_results: int = 50
    ) -> list[dict]:
        """One page of the newest videos for ``query``: ``[{video_id, channel_id, title}]``."""
        data = self._get(
            "search",
            part="snippet",
            q=query,
            type="video",
            order="date",
            publishedAfter=published_after,
            relevanceLanguage=language,
            maxResults=max_results,
        )
        return [
            {
                "video_id": item["id"].get("videoId", ""),
                "channel_id": item["snippet"].get("channelId", ""),
                "title": item["snippet"].get("title", ""),
            }
            for item in data.get("items", [])
            if item.get("snippet", {}).get("channelId")
        ]

    # channels.list, 1 unit per 50 ids ---------------------------------------
    def channels(self, channel_ids: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        ids = list(dict.fromkeys(i for i in channel_ids if i))
        for start in range(0, len(ids), 50):
            data = self._get(
                "channels",
                part="snippet,statistics,contentDetails,status,brandingSettings",
                id=",".join(ids[start:start + 50]),
                maxResults=50,
            )
            for item in data.get("items", []):
                out[item["id"]] = item
        return out

    # playlistItems.list, 1 unit ---------------------------------------------
    def recent_uploads(self, uploads_playlist_id: str, max_results: int) -> list[dict]:
        """Newest uploads: ``[{video_id, title, published_at}]``, newest first."""
        if not uploads_playlist_id or max_results <= 0:
            return []
        try:
            data = self._get(
                "playlistItems",
                part="snippet,contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=min(max_results, 50),
            )
        except ApiError as exc:
            if exc.status == 404:  # No public uploads
                return []
            raise
        videos = []
        for item in data.get("items", []):
            snippet, details = item.get("snippet", {}), item.get("contentDetails", {})
            if snippet.get("title") in ("Private video", "Deleted video"):
                continue
            videos.append(
                {
                    "video_id": details.get("videoId", ""),
                    "title": snippet.get("title", ""),
                    "published_at": details.get("videoPublishedAt") or snippet.get("publishedAt", ""),
                }
            )
        return sorted(videos, key=lambda v: v["published_at"], reverse=True)

    # commentThreads.list, 1 unit per page of up to 100 -----------------------
    def comment_pages(self, video_id: str, max_pages: int = 1):
        """Yield pages of raw comment threads. Callers must extract and discard."""
        token = None
        for _ in range(max_pages):
            try:
                data = self._get(
                    "commentThreads",
                    part="snippet",
                    videoId=video_id,
                    maxResults=100,
                    order="relevance",
                    textFormat="plainText",
                    pageToken=token,
                )
            except ApiError as exc:
                if exc.status in (403, 404):  # Comments disabled or video gone
                    return
                raise
            yield data.get("items", [])
            token = data.get("nextPageToken")
            if not token:
                return

    # channelSections.list, 1 unit -------------------------------------------
    def featured_channels(self, channel_id: str) -> list[str]:
        try:
            data = self._get("channelSections", part="contentDetails", channelId=channel_id)
        except ApiError as exc:
            if exc.status in (403, 404):
                return []
            raise
        ids: list[str] = []
        for section in data.get("items", []):
            ids += section.get("contentDetails", {}).get("channels", []) or []
        return list(dict.fromkeys(ids))

    # subscriptions.list, 1 unit; only public subscription lists --------------
    def public_subscriptions(self, channel_id: str, max_results: int = 50) -> list[str]:
        try:
            data = self._get(
                "subscriptions", part="snippet", channelId=channel_id, maxResults=min(max_results, 50)
            )
        except ApiError as exc:
            if exc.status in (403, 404):  # subscriptionForbidden: the list is private
                return []
            raise
        return [
            item["snippet"]["resourceId"]["channelId"]
            for item in data.get("items", [])
            if item.get("snippet", {}).get("resourceId", {}).get("channelId")
        ]
