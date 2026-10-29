"""Thin client for the YouTube Data API v3 that returns plain, JSON-ready dicts.

Quota (default 10,000 units a day): ``search.list`` costs 100 units per page of
up to 50 results; ``videos.list``, ``channels.list`` and ``playlistItems.list``
cost 1 unit per call of up to 50 ids.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import ScoutError
from .config import api_key as env_api_key

BATCH_SIZE = 50  # The API's maximum ids (or results) per call

_DURATION_RE = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_duration(value: str) -> int:
    """ISO 8601 duration (``PT1H2M3S``) to seconds; 0 when missing or unparseable."""
    match = _DURATION_RE.match(value or "")
    if not match:
        return 0
    days, hours, minutes, seconds = (int(group or 0) for group in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def iso_datetime(value: str) -> Optional[str]:
    """A YouTube timestamp (``...Z``) as ISO 8601 with an explicit UTC offset."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


class YouTubeClient:
    """One client per thread: the underlying ``httplib2`` connection is not thread-safe."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._youtube = build(
            "youtube", "v3", developerKey=api_key or env_api_key(), cache_discovery=False
        )

    @staticmethod
    def _execute(request: Any) -> Dict:
        try:
            return request.execute()
        except HttpError as exc:
            raise ScoutError(f"YouTube API error: {exc}") from exc

    def search_videos(self, keyword: str, max_results: int = 1000) -> List[Dict]:
        """Video hits for ``keyword`` in relevance order: ``[{video_id, channel_id}]``."""
        hits: List[Dict] = []
        page_token = None
        while len(hits) < max_results:
            response = self._execute(
                self._youtube.search().list(
                    q=keyword,
                    part="id,snippet",
                    type="video",
                    order="relevance",
                    maxResults=min(BATCH_SIZE, max_results - len(hits)),
                    pageToken=page_token,
                )
            )
            items = response.get("items", [])
            hits.extend(
                {"video_id": item["id"]["videoId"], "channel_id": item["snippet"]["channelId"]}
                for item in items
            )
            page_token = response.get("nextPageToken")
            if not page_token or not items:
                break
            time.sleep(0.1)
        return hits[:max_results]

    def get_videos(self, video_ids: List[str]) -> Dict[str, Dict]:
        """Video records by id (unknown or private ids are left out)."""
        videos: Dict[str, Dict] = {}
        for start in range(0, len(video_ids), BATCH_SIZE):
            response = self._execute(
                self._youtube.videos().list(
                    part="statistics,snippet,contentDetails",
                    id=",".join(video_ids[start:start + BATCH_SIZE]),
                )
            )
            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                videos[item["id"]] = {
                    "video_id": item["id"],
                    "title": snippet.get("title", ""),
                    "url": f"https://www.youtube.com/watch?v={item['id']}",
                    "published_at": iso_datetime(snippet.get("publishedAt", "")),
                    "views": int(stats.get("viewCount", 0)),
                    "likes": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                    "duration_seconds": parse_duration(
                        item.get("contentDetails", {}).get("duration", "")
                    ),
                }
        return videos

    def get_channels(self, channel_ids: List[str]) -> Dict[str, Dict]:
        """Channel records (stats and profile, no videos) by id."""
        channels: Dict[str, Dict] = {}
        for start in range(0, len(channel_ids), BATCH_SIZE):
            response = self._execute(
                self._youtube.channels().list(
                    part="statistics,snippet,contentDetails",
                    id=",".join(channel_ids[start:start + BATCH_SIZE]),
                )
            )
            for item in response.get("items", []):
                channels[item["id"]] = _channel_record(item)
        return channels

    def get_channel(self, channel: str) -> Optional[Dict]:
        """One channel by id (``UC...``) or handle (``@name``); ``None`` if not found."""
        if channel.startswith("@"):
            response = self._execute(
                self._youtube.channels().list(
                    part="statistics,snippet,contentDetails", forHandle=channel
                )
            )
            items = response.get("items", [])
            return _channel_record(items[0]) if items else None
        return self.get_channels([channel]).get(channel)

    def get_latest_videos(self, uploads_playlist_id: str, max_results: int = 50) -> List[Dict]:
        """A channel's newest uploads (at most 50), newest first."""
        if not uploads_playlist_id or max_results <= 0:
            return []
        response = self._execute(
            self._youtube.playlistItems().list(
                part="contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=min(BATCH_SIZE, max_results),
            )
        )
        ids = [item["contentDetails"]["videoId"] for item in response.get("items", [])]
        videos = self.get_videos(ids)
        return [videos[video_id] for video_id in ids if video_id in videos]


def _channel_record(item: Dict) -> Dict:
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    return {
        "channel_id": item["id"],
        "channel_name": snippet.get("title", ""),
        "channel_url": f"https://www.youtube.com/channel/{item['id']}",
        "custom_url": snippet.get("customUrl", ""),
        "description": snippet.get("description", ""),
        "country": snippet.get("country", ""),
        "created_at": iso_datetime(snippet.get("publishedAt", "")),
        "thumbnail_url": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
        "subscriber_count": int(stats.get("subscriberCount", 0)),
        "total_videos": int(stats.get("videoCount", 0)),
        "total_channel_views": int(stats.get("viewCount", 0)),
        "uploads_playlist_id": item.get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads", ""),
    }
