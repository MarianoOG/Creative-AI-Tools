"""Search channels by keyword, filter and sort them, and inspect one creator."""

from collections import Counter
from datetime import datetime, timedelta, timezone

from . import youtube_api as api
from .metrics import compute_metrics, parse_datetime
from .youtube_api import ScoutError

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


def search(keyword: str, max_results: int = 1000) -> dict:
    """The channels behind the top ``max_results`` videos for ``keyword``.

    Returns ``{keyword, channels}``: channels in relevance order, each with its
    profile, the ``videos`` the search found and their metrics.
    """
    keyword = keyword.strip()
    if not keyword:
        raise ScoutError("Enter a search term.")
    hits = api.search_videos(keyword, max_results)
    if not hits:
        raise ScoutError(f"No videos found for {keyword!r}")
    videos = api.get_videos(list(dict.fromkeys(h["video_id"] for h in hits)))
    profiles = api.get_channels(list(dict.fromkeys(h["channel_id"] for h in hits)))

    channels: dict[str, dict] = {}
    seen = set()
    for hit in hits:
        video, profile = videos.get(hit["video_id"]), profiles.get(hit["channel_id"])
        if video and profile and hit["video_id"] not in seen:
            seen.add(hit["video_id"])
            channels.setdefault(hit["channel_id"], {**profile, "videos": []})["videos"].append(video)
    if not channels:
        raise ScoutError(f"No channels found for {keyword!r}")
    return {"keyword": keyword, "channels": [compute_metrics(c) for c in channels.values()]}


def _within(value: float, low: float | None, high: float | None = None) -> bool:
    return (low is None or value >= low) and (high is None or value <= high)


def _active_within(channel: dict, days: int) -> bool:
    last = parse_datetime(channel["last_published"])
    return last is not None and last >= datetime.now(timezone.utc) - timedelta(days=days)


def filter_channels(
    channels: list[dict],
    *,
    min_views: int | None = None,
    max_views: int | None = None,
    min_subscribers: int | None = None,
    max_subscribers: int | None = None,
    active_within_days: int | None = None,
    min_videos: int | None = None,
    max_videos: int | None = None,
    min_score: int | None = None,
) -> list[dict]:
    """Channels within every given bound (inclusive), order kept.

    Views are median views; videos are the channel's total uploads.
    """
    return [
        c
        for c in channels
        if _within(c["median_views"], min_views, max_views)
        and _within(c["subscriber_count"], min_subscribers, max_subscribers)
        and _within(c["total_videos"], min_videos, max_videos)
        and _within(c["channel_score"], min_score)
        and (active_within_days is None or _active_within(c, active_within_days))
    ]


def sort_channels(channels: list[dict], sort_by: str = "relevance", descending: bool = True) -> list[dict]:
    """Channels ordered by one of ``SORT_FIELDS``; those missing the field go last."""
    if sort_by not in SORT_FIELDS:
        raise ScoutError(f"sort_by must be one of {list(SORT_FIELDS)}, not {sort_by!r}")
    if sort_by == "relevance":
        return list(channels)
    key = parse_datetime if sort_by == "last_published" else (lambda value: value)
    present = [c for c in channels if c.get(sort_by) is not None]
    missing = [c for c in channels if c.get(sort_by) is None]
    return sorted(present, key=lambda c: key(c[sort_by]), reverse=descending) + missing


def uploads_by_month(videos: list[dict], months: int = 6) -> list[dict]:
    """Uploads per calendar month over the last ``months`` months, oldest first."""
    counts = Counter(
        d.strftime("%Y-%m") for d in (parse_datetime(v["published_at"]) for v in videos) if d
    )
    now = datetime.now(timezone.utc)
    keys = []
    for back in range(months - 1, -1, -1):
        year, month = divmod(now.year * 12 + now.month - 1 - back, 12)
        keys.append(f"{year:04d}-{month + 1:02d}")
    return [{"month": key, "uploads": counts[key]} for key in keys]


def get_creator(channel: str, max_videos: int = 50) -> dict:
    """One channel (id or ``@handle``) with metrics over its latest uploads.

    ``videos`` holds up to ``max_videos`` (max 50) newest uploads, and
    ``uploads_by_month`` their count per month over the last six months.
    """
    if channel.startswith("@"):
        found = api.get_channels(handle=channel)
    else:
        found = api.get_channels([channel])
    if not found:
        raise ScoutError(f"No channel {channel!r}")
    record = next(iter(found.values()))
    latest = api.get_latest_videos(record["uploads_playlist_id"], max_videos)
    return {**compute_metrics({**record, "videos": latest}), "uploads_by_month": uploads_by_month(latest)}
