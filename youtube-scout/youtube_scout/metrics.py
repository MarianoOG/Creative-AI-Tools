"""Channel metrics, computed from a channel's ``videos``.

Ratios are percentages. Medians keep one viral video from skewing a channel.
"""

from datetime import datetime, timezone
from statistics import median


def parse_datetime(value: str | None) -> datetime | None:
    """An ISO 8601 string as an aware datetime; ``None`` if missing or invalid."""
    try:
        moment = datetime.fromisoformat(value) if value else None
    except ValueError:
        return None
    if moment and moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _median(values: list[int]) -> int:
    return int(median(values)) if values else 0


def channel_score(
    interval_days: float | None, views_to_subs: float, likes_to_views: float, comments_to_views: float
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


def compute_metrics(channel: dict) -> dict:
    """Add every metric to ``channel`` (in place) and return it."""
    videos = channel.get("videos", [])
    views = [v["views"] for v in videos]
    dates = sorted((d for d in (parse_datetime(v["published_at"]) for v in videos) if d), reverse=True)
    durations = [v["duration_seconds"] for v in videos if v["duration_seconds"] > 0]

    median_views = _median(views)
    median_likes = _median([v["likes"] for v in videos])
    median_comments = _median([v["comment_count"] for v in videos])
    subscribers = channel.get("subscriber_count", 0)
    gaps = [(newer - older).days for newer, older in zip(dates, dates[1:])]
    interval = sum(gaps) / len(gaps) if gaps else None
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
        last_published=dates[0].isoformat() if dates else None,
        days_since_last_published=(datetime.now(timezone.utc) - dates[0]).days if dates else None,
        views_to_subs_ratio=round(views_to_subs, 2),
        likes_to_views_ratio=round(likes_to_views, 2),
        comments_to_views_ratio=round(comments_to_views, 2),
        channel_score=channel_score(interval, views_to_subs, likes_to_views, comments_to_views),
    )
    return channel
