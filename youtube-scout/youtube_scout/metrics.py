"""Channel metrics, computed from the videos a channel record holds.

Ratios are percentages. Medians are used over averages so one viral video does
not skew a channel.
"""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, List, Optional


def parse_datetime(value: Any) -> Optional[datetime]:
    """An ISO 8601 string (or datetime) as an aware datetime; ``None`` if unusable."""
    if isinstance(value, datetime):
        moment = value
    elif value:
        try:
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _median(values: List[int]) -> int:
    return int(median(values)) if values else 0


def publish_interval_days(dates: List[datetime]) -> Optional[float]:
    """Average days between consecutive uploads; ``None`` with fewer than two dates."""
    if len(dates) < 2:
        return None
    ordered = sorted(dates, reverse=True)
    gaps = [(newer - older).days for newer, older in zip(ordered, ordered[1:])]
    return sum(gaps) / len(gaps)


def channel_score(
    interval_days: Optional[float],
    views_to_subs: float,
    likes_to_views: float,
    comments_to_views: float,
) -> int:
    """0-100: activity 30%, views-to-subscribers 35%, engagement 35%.

    Engagement is benchmarked against 4% likes and 0.5% comments per view
    (likes weigh 70%, comments 30%).
    """
    if interval_days is None or interval_days > 60:
        activity = 30
    elif interval_days > 30:
        activity = 50
    elif interval_days > 14:
        activity = 70
    elif interval_days > 7:
        activity = 85
    else:
        activity = 100

    if views_to_subs < 2:
        performance = 20
    elif views_to_subs < 5:
        performance = 40
    elif views_to_subs < 10:
        performance = 60
    elif views_to_subs < 20:
        performance = 80
    else:
        performance = 100

    like_score = min(100, likes_to_views / 4 * 100)
    comment_score = min(100, comments_to_views / 0.5 * 100)
    engagement = like_score * 0.7 + comment_score * 0.3

    return round(activity * 0.30 + performance * 0.35 + engagement * 0.35)


def compute_metrics(channel: Dict) -> Dict:
    """Set every derived metric on ``channel`` (in place) and return it."""
    videos = channel.get("videos", [])
    views = [v.get("views", 0) for v in videos]
    dates = [d for d in (parse_datetime(v.get("published_at")) for v in videos) if d]
    durations = [v["duration_seconds"] for v in videos if v.get("duration_seconds", 0) > 0]

    median_views = _median(views)
    median_likes = _median([v.get("likes", 0) for v in videos])
    median_comments = _median([v.get("comment_count", 0) for v in videos])
    subscribers = channel.get("subscriber_count", 0)
    interval = publish_interval_days(dates)
    views_to_subs = median_views / subscribers * 100 if subscribers else 0.0
    likes_to_views = median_likes / median_views * 100 if median_views else 0.0
    comments_to_views = median_comments / median_views * 100 if median_views else 0.0

    channel.update(
        median_views=median_views,
        average_views=round(sum(views) / len(views), 1) if views else 0.0,
        median_likes=median_likes,
        median_comments=median_comments,
        avg_duration=sum(durations) // len(durations) if durations else 0,
        publish_interval_days=round(interval, 1) if interval is not None else None,
        last_published=max(dates).isoformat() if dates else None,
        views_to_subs_ratio=round(views_to_subs, 2),
        likes_to_views_ratio=round(likes_to_views, 2),
        comments_to_views_ratio=round(comments_to_views, 2),
        channel_score=channel_score(interval, views_to_subs, likes_to_views, comments_to_views),
    )
    return channel
