"""YouTube Data API v3 calls, returning plain dicts.

The API key comes from ``YOUTUBE_API_KEY`` (``youtube-scout/.env`` is loaded first).
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BATCH_SIZE = 50  # The API's maximum ids or results per call
_DURATION_RE = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")

# The API service, built on first use. Tests can replace it with a fake.
service: Any = None


class ScoutError(Exception):
    """A problem to report to the user: missing key, API error, nothing found."""


def _api() -> Any:
    global service
    if service is None:
        key = os.getenv("YOUTUBE_API_KEY", "").strip()
        if not key:
            raise ScoutError(
                "YOUTUBE_API_KEY is not set. Add it to youtube-scout/.env or the environment "
                "(get a key at https://console.cloud.google.com/)."
            )
        service = build("youtube", "v3", developerKey=key, cache_discovery=False)
    return service


def _execute(request: Any) -> dict:
    try:
        return request.execute()
    except HttpError as exc:
        raise ScoutError(f"YouTube API error: {exc}") from exc


def _iso(value: str) -> str | None:
    """A YouTube timestamp (``...Z``) as ISO 8601 with an explicit UTC offset."""
    try:
        return datetime.fromisoformat(value).isoformat() if value else None
    except ValueError:
        return None


def _seconds(duration: str) -> int:
    """An ISO 8601 duration (``PT1H2M3S``) in seconds; 0 if unparseable."""
    match = _DURATION_RE.match(duration or "")
    if not match:
        return 0
    days, hours, minutes, seconds = (int(group or 0) for group in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def search_videos(keyword: str, max_results: int) -> list[dict]:
    """Video hits in relevance order: ``[{video_id, channel_id}]``."""
    hits: list[dict] = []
    page_token = None
    while len(hits) < max_results:
        response = _execute(
            _api().search().list(
                q=keyword,
                part="id,snippet",
                type="video",
                order="relevance",
                maxResults=min(BATCH_SIZE, max_results - len(hits)),
                pageToken=page_token,
            )
        )
        items = response.get("items", [])
        hits += [
            {"video_id": item["id"]["videoId"], "channel_id": item["snippet"]["channelId"]}
            for item in items
        ]
        page_token = response.get("nextPageToken")
        if not page_token or not items:
            break
    return hits[:max_results]


def get_videos(video_ids: list[str]) -> dict[str, dict]:
    """Videos by id; unknown or private ids are left out."""
    videos = {}
    for start in range(0, len(video_ids), BATCH_SIZE):
        response = _execute(
            _api().videos().list(
                part="statistics,snippet,contentDetails",
                id=",".join(video_ids[start:start + BATCH_SIZE]),
            )
        )
        for item in response.get("items", []):
            snippet, stats = item.get("snippet", {}), item.get("statistics", {})
            videos[item["id"]] = {
                "video_id": item["id"],
                "title": snippet.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={item['id']}",
                "published_at": _iso(snippet.get("publishedAt", "")),
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
                "duration_seconds": _seconds(item.get("contentDetails", {}).get("duration", "")),
            }
    return videos


def get_channels(channel_ids: list[str] | None = None, handle: str | None = None) -> dict[str, dict]:
    """Channel profiles and stats by id, looked up by ids or by one ``@handle``."""
    if handle:
        batches = [{"forHandle": handle}]
    else:
        batches = [
            {"id": ",".join(channel_ids[start:start + BATCH_SIZE])}
            for start in range(0, len(channel_ids or []), BATCH_SIZE)
        ]
    channels = {}
    for batch in batches:
        response = _execute(_api().channels().list(part="statistics,snippet,contentDetails", **batch))
        for item in response.get("items", []):
            snippet, stats = item.get("snippet", {}), item.get("statistics", {})
            channels[item["id"]] = {
                "channel_id": item["id"],
                "channel_name": snippet.get("title", ""),
                "channel_url": f"https://www.youtube.com/channel/{item['id']}",
                "custom_url": snippet.get("customUrl", ""),
                "description": snippet.get("description", ""),
                "country": snippet.get("country", ""),
                "created_at": _iso(snippet.get("publishedAt", "")),
                "thumbnail_url": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
                "subscriber_count": int(stats.get("subscriberCount", 0)),
                "total_videos": int(stats.get("videoCount", 0)),
                "total_channel_views": int(stats.get("viewCount", 0)),
                "uploads_playlist_id": item.get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads", ""),
            }
    return channels


def get_latest_videos(uploads_playlist_id: str, max_results: int) -> list[dict]:
    """A channel's newest uploads (at most 50), newest first."""
    if not uploads_playlist_id or max_results <= 0:
        return []
    response = _execute(
        _api().playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=min(BATCH_SIZE, max_results),
        )
    )
    ids = [item["contentDetails"]["videoId"] for item in response.get("items", [])]
    videos = get_videos(ids)
    return [videos[video_id] for video_id in ids if video_id in videos]
