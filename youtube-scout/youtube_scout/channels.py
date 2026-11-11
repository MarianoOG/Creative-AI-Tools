"""Channel profiles from ``channels.list`` and the eligibility filters.

Filters run cheapest first: everything that ``channels.list`` alone can decide
is checked before spending a ``playlistItems.list`` call on recent uploads.
Rejected channels are only counted by reason; nothing else about them is kept,
and in particular nothing about made-for-kids channels or channels that look
run by a minor.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta

from .config import Config
from .state import utc_now

_MINOR_PATTERNS = [
    # "I'm 12", "I am 14 years old", "13yo", "tengo 12 años"
    r"\b(i'?m|i am|im)\s+(1[0-7]|[5-9])\b(?!\s*(k|m|%|\+|subs|subscribers|hours|videos|minutes|min))",
    r"\b(1[0-7]|[5-9])\s*(years?\s*old|yrs?\s*old|y/?o)\b",
    r"\btengo\s+(1[0-7]|[5-9])\s*a(ñ|n)os\b",
    r"\b(1[0-7]|[5-9])\s*a(ñ|n)os\s+de\s+edad\b",
    r"\b(kid|teen|child)\s+youtuber\b",
    r"\byoutuber\s+(kid|niñ[oa]|infantil)\b",
    r"\bniñ[oa]\s+youtuber\b",
    r"\b(managed|run|ran|monitored|supervised)\s+by\s+(my\s+)?(mom|mum|dad|parents?|mother|father)\b",
    r"\b(mis\s+pap[aá]s|mi\s+mam[aá]|mi\s+pap[aá])\s+(manejan?|administran?|supervisan?)\b",
    r"\b(middle|elementary|primary)\s+school(er)?\b",
    r"\b(\d+)(th|st|nd|rd)\s+grader?\b",
]
_MINOR_RE = re.compile("|".join(f"(?:{p})" for p in _MINOR_PATTERNS), re.I)


def looks_like_minor(*texts: str) -> bool:
    return any(_MINOR_RE.search(text or "") for text in texts)


def id_hash(channel_id: str) -> str:
    """A one-way id, so a resumed run can skip rejected channels without storing them."""
    return hashlib.sha256(channel_id.encode()).hexdigest()[:16]


def profile(item: dict) -> dict:
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    branding = item.get("brandingSettings", {}).get("channel", {})
    hidden = bool(stats.get("hiddenSubscriberCount"))
    return {
        "channel_id": item["id"],
        "title": snippet.get("title", ""),
        "url": f"https://www.youtube.com/channel/{item['id']}",
        "description": snippet.get("description", ""),
        "country": snippet.get("country", "") or branding.get("country", ""),
        "published_at": snippet.get("publishedAt", ""),
        "hidden_subscribers": hidden,
        "subscriber_count": None if hidden else int(stats.get("subscriberCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
        "uploads_playlist": item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", ""),
        "made_for_kids": bool(item.get("status", {}).get("madeForKids")),
        "language": (snippet.get("defaultLanguage") or branding.get("defaultLanguage") or "")[:2].lower(),
    }


def size_band(cfg: Config, my_subscribers: int | None) -> tuple[int, int]:
    band = cfg.size_band
    if band.is_absolute:
        return band.min_subscribers, band.max_subscribers
    if my_subscribers is None:
        raise ValueError("my subscriber count is needed for a multiplier band")
    return int(my_subscribers * band.min_multiplier), int(my_subscribers * band.max_multiplier)


def profile_reject_reason(p: dict, band: tuple[int, int], cfg: Config) -> str | None:
    """Why a channel fails on its profile alone, or ``None``."""
    if p["made_for_kids"]:
        return "made for kids"
    if looks_like_minor(p["title"], p["description"]):
        return "looks run by a minor"
    if p["hidden_subscribers"]:
        return "hidden subscriber count"
    if not band[0] <= p["subscriber_count"] <= band[1]:
        return "outside size band"
    if p["video_count"] < 1:
        return "no public videos"
    if p["language"] and p["language"] not in cfg.languages:
        return "language"
    return None


def parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def uploads_reject_reason(uploads: list[dict], cfg: Config, now: datetime | None = None) -> str | None:
    if not uploads:
        return "no public videos"
    last = parse_time(uploads[0]["published_at"])
    if last is None or last < (now or utc_now()) - timedelta(days=cfg.last_upload_within_days):
        return "inactive"
    if looks_like_minor(*(u["title"] for u in uploads)):
        return "looks run by a minor"
    return None
