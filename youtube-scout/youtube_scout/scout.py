"""The high-level operations: search, read a saved search, inspect one creator."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from .channels import filter_channels, sort_channels, uploads_by_month, with_recency
from .config import ScoutError
from .metrics import compute_metrics
from .store import find_search, load_search, save_search
from .youtube_api import YouTubeClient

DEFAULT_MAX_RESULTS = 1000


def search(
    keyword: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    use_cache: bool = True,
    client: Optional[YouTubeClient] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Dict:
    """Find the channels behind the videos YouTube returns for ``keyword``, and save them.

    With ``use_cache`` the newest saved search for the same keyword is returned
    instead of spending quota again. Returns the saved record
    ``{id, keyword, created_at, channels: {channel_id: channel}}``, channels in
    relevance order. No filtering happens here: filter the saved result.
    """
    keyword = keyword.strip()
    if not keyword:
        raise ScoutError("Enter a search term.")
    progress = on_progress or (lambda message: None)

    if use_cache:
        cached = find_search(keyword)
        if cached is not None:
            progress(f"Using saved search {cached['id']}")
            return cached

    client = client or YouTubeClient()
    progress("Searching for videos...")
    hits = client.search_videos(keyword, max_results)
    if not hits:
        raise ScoutError(f"No videos found for {keyword!r}")
    progress(f"Found {len(hits)} videos; fetching video statistics...")
    videos = client.get_videos(list(dict.fromkeys(h["video_id"] for h in hits)))
    channel_ids = list(dict.fromkeys(h["channel_id"] for h in hits))
    progress(f"Fetching statistics for {len(channel_ids)} channels...")
    channel_stats = client.get_channels(channel_ids)

    channels: Dict[str, Dict] = {}
    seen = set()
    for hit in hits:
        video, stats = videos.get(hit["video_id"]), channel_stats.get(hit["channel_id"])
        if video is None or stats is None or hit["video_id"] in seen:
            continue
        seen.add(hit["video_id"])
        channels.setdefault(hit["channel_id"], {**stats, "videos": []})["videos"].append(video)
    if not channels:
        raise ScoutError(f"No channels found for {keyword!r}")
    for channel in channels.values():
        compute_metrics(channel)

    record = save_search(keyword, channels)
    progress(f"Found {len(channels)} creators; saved as {record['id']}")
    return record


def get_channels(
    search_id: str,
    *,
    sort_by: str = "relevance",
    descending: bool = True,
    limit: Optional[int] = None,
    min_views: Optional[int] = None,
    max_views: Optional[int] = None,
    min_subscribers: Optional[int] = None,
    max_subscribers: Optional[int] = None,
    active_within_days: Optional[int] = None,
    min_videos: Optional[int] = None,
    max_videos: Optional[int] = None,
    min_score: Optional[int] = None,
) -> List[Dict]:
    """A saved search's channels, filtered, sorted and cut to ``limit``. Costs no quota.

    See ``filter_channels`` for the bounds and ``SORT_FIELDS`` for ``sort_by``.
    Each channel also gets ``days_since_last_published``.
    """
    channels = filter_channels(
        load_search(search_id)["channels"],
        min_views=min_views,
        max_views=max_views,
        min_subscribers=min_subscribers,
        max_subscribers=max_subscribers,
        active_within_days=active_within_days,
        min_videos=min_videos,
        max_videos=max_videos,
        min_score=min_score,
    )
    ordered = sort_channels(channels, sort_by, descending)
    return [with_recency(channel) for channel in ordered[:limit]]


def get_creator(
    channel: str,
    *,
    search_id: Optional[str] = None,
    max_videos: int = 50,
    client: Optional[YouTubeClient] = None,
) -> Dict:
    """One channel's stats, metrics and video history.

    ``channel`` is a channel id, or a ``@handle`` when no ``search_id`` is given.
    With ``search_id`` the stats and metrics come from that saved search (its
    ``videos`` are the ones the search found); without it they are fetched, and
    the metrics are computed over the latest uploads. ``latest_videos`` holds up
    to ``max_videos`` (max 50) newest uploads, ``uploads_by_month`` their count
    per month over the last six months. ``max_videos=0`` skips both, and with a
    ``search_id`` then needs no API call at all.
    """
    if search_id:
        record = load_search(search_id)["channels"].get(channel)
        if record is None:
            raise ScoutError(f"Channel {channel!r} is not in search {search_id!r}")
    else:
        client = client or YouTubeClient()
        stats = client.get_channel(channel)
        if stats is None:
            raise ScoutError(f"No channel {channel!r}")
        record = {**stats, "videos": []}

    latest: List[Dict] = []
    if max_videos > 0 and record.get("uploads_playlist_id"):
        client = client or YouTubeClient()
        latest = client.get_latest_videos(record["uploads_playlist_id"], max_videos)

    if not search_id:
        record["videos"] = latest
        compute_metrics(record)

    return {
        **with_recency(record),
        "latest_videos": latest,
        "uploads_by_month": uploads_by_month(latest),
    }
