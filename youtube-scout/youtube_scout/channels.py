"""Filter and sort channel records, and the fields that depend on today's date."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Union

from .config import ScoutError
from .metrics import parse_datetime

Channels = Union[Dict[str, Dict], Iterable[Dict]]

#: ``relevance`` keeps search order; the rest are channel fields.
SORT_FIELDS = (
    "relevance",
    "median_views",
    "subscriber_count",
    "last_published",
    "channel_score",
    "views_to_subs_ratio",
    "likes_to_views_ratio",
)

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def _as_list(channels: Channels) -> List[Dict]:
    return list(channels.values() if isinstance(channels, dict) else channels)


def _within(value: float, low: Optional[float], high: Optional[float]) -> bool:
    return (low is None or value >= low) and (high is None or value <= high)


def filter_channels(
    channels: Channels,
    *,
    min_views: Optional[int] = None,
    max_views: Optional[int] = None,
    min_subscribers: Optional[int] = None,
    max_subscribers: Optional[int] = None,
    active_within_days: Optional[int] = None,
    min_videos: Optional[int] = None,
    max_videos: Optional[int] = None,
    min_score: Optional[int] = None,
) -> List[Dict]:
    """Channels matching every given bound (``None`` = no bound), order kept.

    Views are the channel's median views; videos are its total uploads.
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=active_within_days)
        if active_within_days
        else None
    )
    matches = []
    for channel in _as_list(channels):
        if not _within(channel.get("median_views", 0), min_views, max_views):
            continue
        if not _within(channel.get("subscriber_count", 0), min_subscribers, max_subscribers):
            continue
        if not _within(channel.get("total_videos", 0), min_videos, max_videos):
            continue
        if not _within(channel.get("channel_score", 0), min_score, None):
            continue
        if cutoff:
            last = parse_datetime(channel.get("last_published"))
            if last is None or last < cutoff:
                continue
        matches.append(channel)
    return matches


def sort_channels(
    channels: Channels, sort_by: str = "relevance", descending: bool = True
) -> List[Dict]:
    """Channels ordered by one of ``SORT_FIELDS``; channels missing the field go last."""
    items = _as_list(channels)
    if sort_by not in SORT_FIELDS:
        raise ScoutError(f"sort_by must be one of {list(SORT_FIELDS)}, not {sort_by!r}")
    if sort_by == "relevance":
        return items

    def key(channel: Dict):
        value = channel[sort_by]
        return (parse_datetime(value) or _EPOCH) if sort_by == "last_published" else value

    present = [c for c in items if c.get(sort_by) is not None]
    missing = [c for c in items if c.get(sort_by) is None]
    return sorted(present, key=key, reverse=descending) + missing


def with_recency(channel: Dict) -> Dict:
    """A copy of ``channel`` with ``days_since_last_published`` (``None`` if unknown)."""
    last = parse_datetime(channel.get("last_published"))
    days = (datetime.now(timezone.utc) - last).days if last else None
    return {**channel, "days_since_last_published": days}


def uploads_by_month(videos: List[Dict], months: int = 6) -> List[Dict]:
    """Uploads per calendar month for the last ``months`` months, oldest first."""
    counts = Counter(
        d.strftime("%Y-%m")
        for d in (parse_datetime(v.get("published_at")) for v in videos)
        if d
    )
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month
    keys = []
    for _ in range(months):
        keys.append(f"{year:04d}-{month:02d}")
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return [{"month": key, "uploads": counts.get(key, 0)} for key in reversed(keys)]
