#!/usr/bin/env python3
"""Small, read-only tools for the YouTube Data API v3.

Each function makes one kind of API call and returns plain dicts and lists.
Every command prints JSON, so a script, an agent or a Claude session can read it.

    python yt.py channel @handle                 # a channel's profile and stats
    python yt.py uploads @handle -n 10           # its latest videos with stats
    python yt.py search "stop motion" --days 14  # recent videos for a query
    python yt.py creators "stop motion"          # the channels behind those videos
    python yt.py comments VIDEO_ID -n 100        # top-level comments, each with a link
    python yt.py videos ID1 ID2                  # stats for given videos
    python yt.py channels UC1 UC2                # profiles for given channel ids
    python yt.py featured @handle                # channels it features
    python yt.py subscriptions @handle           # channels it subscribes to (if public)
    python yt.py band 500 5000 < creators.json   # keep channels in a subscriber range

The API key comes from YOUTUBE_API_KEY (the environment, or a .env file in the
current folder or next to this file). Quota units used are printed to stderr.
Nothing is saved to disk.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://www.googleapis.com/youtube/v3"

# Quota units per call: https://developers.google.com/youtube/v3/determine_quota_cost
COST = {"search": 100, "channels": 1, "playlistItems": 1, "videos": 1,
        "commentThreads": 1, "channelSections": 1, "subscriptions": 1}

units_used = 0  # Total quota units spent by this process


class YouTubeError(Exception):
    """A problem to show the user: missing key, API error, unknown channel."""


# --- The one place that talks to the API ------------------------------------

def _key() -> str:
    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not key:
        for env in (Path.cwd() / ".env", Path(__file__).resolve().parent / ".env"):
            if env.exists():
                for line in env.read_text().splitlines():
                    name, _, value = line.partition("=")
                    if name.strip() == "YOUTUBE_API_KEY" and value.strip():
                        return value.strip().strip("'\"")
        raise YouTubeError("YOUTUBE_API_KEY is not set. Put it in .env or the environment "
                           "(get one at https://console.cloud.google.com/apis/credentials).")
    return key


def get(method: str, **params) -> dict:
    """One GET request to the API. Every other function goes through here."""
    global units_used
    params = {k: v for k, v in params.items() if v is not None}
    url = f"{API}/{method}?" + urllib.parse.urlencode({**params, "key": _key()})
    units_used += COST[method]  # Charged even when the call fails
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            error = json.load(exc).get("error", {})
        except ValueError:
            error = {}
        reason = (error.get("errors") or [{}])[0].get("reason", "")
        raise YouTubeError(f"{method}: HTTP {exc.code} {reason} {error.get('message', '')}".strip()) from exc
    except urllib.error.URLError as exc:
        raise YouTubeError(f"{method}: network error: {exc.reason}") from exc
    return data


# --- Shaping API items into flat dicts --------------------------------------

def _channel(item: dict) -> dict:
    snippet, stats = item.get("snippet", {}), item.get("statistics", {})
    hidden = stats.get("hiddenSubscriberCount", False)
    return {
        "channel_id": item["id"],
        "title": snippet.get("title", ""),
        "handle": snippet.get("customUrl", ""),
        "url": f"https://www.youtube.com/channel/{item['id']}",
        "description": snippet.get("description", ""),
        "country": snippet.get("country", ""),
        "language": snippet.get("defaultLanguage", ""),
        "created_at": snippet.get("publishedAt", ""),
        "subscribers": None if hidden else int(stats.get("subscriberCount", 0)),
        "videos": int(stats.get("videoCount", 0)),
        "views": int(stats.get("viewCount", 0)),
        "made_for_kids": item.get("status", {}).get("madeForKids", False),
        "uploads_playlist": item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", ""),
    }


def _video(item: dict) -> dict:
    snippet, stats = item.get("snippet", {}), item.get("statistics", {})
    return {
        "video_id": item["id"],
        "title": snippet.get("title", ""),
        "url": f"https://www.youtube.com/watch?v={item['id']}",
        "channel_id": snippet.get("channelId", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "published_at": snippet.get("publishedAt", ""),
        "description": snippet.get("description", ""),
        "tags": snippet.get("tags", []),
        "duration": item.get("contentDetails", {}).get("duration", ""),
        "views": int(stats.get("viewCount", 0)),
        "likes": int(stats.get("likeCount", 0)),
        "comments": int(stats.get("commentCount", 0)),
    }


# --- Tools -------------------------------------------------------------------

def _ref(ref: str) -> str:
    """A channel id or @handle from an id, handle or channel URL."""
    ref = ref.strip().rstrip("/")
    match = re.search(r"youtube\.com/(?:channel/(UC[\w-]+)|(@[\w.-]+))", ref)
    return (match.group(1) or match.group(2)) if match else ref


def _channel_id(ref: str) -> str:
    """A channel id, looking up a handle only when needed (0 or 1 unit)."""
    ref = _ref(ref)
    return ref if ref.startswith("UC") else channel(ref)["channel_id"]


def channel(ref: str) -> dict:
    """A channel by id (UC...), @handle or channel URL. 1 unit."""
    ref = _ref(ref)
    if ref.startswith("UC"):
        found = channels([ref])
    else:
        data = get("channels", part="snippet,statistics,contentDetails,status", forHandle=ref.lstrip("@"))
        found = [_channel(item) for item in data.get("items", [])]
    if not found:
        raise YouTubeError(f"Channel not found: {ref}")
    return found[0]


def channels(ids: list[str]) -> list[dict]:
    """Many channels by id. 1 unit per 50 ids."""
    ids = list(dict.fromkeys(ids))
    out = []
    for start in range(0, len(ids), 50):
        data = get("channels", part="snippet,statistics,contentDetails,status",
                   id=",".join(ids[start:start + 50]), maxResults=50)
        out += [_channel(item) for item in data.get("items", [])]
    return out


def videos(ids: list[str]) -> list[dict]:
    """Many videos by id, with views, likes and comment counts. 1 unit per 50 ids."""
    ids = list(dict.fromkeys(ids))
    out = []
    for start in range(0, len(ids), 50):
        data = get("videos", part="snippet,statistics,contentDetails", id=",".join(ids[start:start + 50]))
        out += [_video(item) for item in data.get("items", [])]
    return out


def uploads(ref: str, n: int = 10) -> list[dict]:
    """A channel's latest n uploads (max 50), newest first, with stats. 3 units."""
    playlist = channel(ref)["uploads_playlist"]
    data = get("playlistItems", part="contentDetails", playlistId=playlist, maxResults=min(n, 50))
    ids = [item["contentDetails"]["videoId"] for item in data.get("items", [])]
    return sorted(videos(ids), key=lambda v: v["published_at"], reverse=True)


def search(query: str, n: int = 25, days: int | None = None, lang: str | None = None,
           order: str = "relevance", region: str | None = None) -> list[dict]:
    """Videos for a query (one page, max 50). order: relevance, date, viewCount, rating. 100 units."""
    after = None
    if days:
        after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = get("search", part="snippet", q=query, type="video", maxResults=min(n, 50), order=order,
               publishedAfter=after, relevanceLanguage=lang, regionCode=region)
    return [
        {
            "video_id": item["id"]["videoId"],
            "title": item["snippet"]["title"],
            "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
            "channel_id": item["snippet"]["channelId"],
            "channel_title": item["snippet"]["channelTitle"],
            "published_at": item["snippet"]["publishedAt"],
        }
        for item in data.get("items", [])
    ]


def creators(query: str, n: int = 25, **search_args) -> list[dict]:
    """The channels behind a search, each with the titles it matched. 101 units."""
    hits = search(query, n, **search_args)
    found = {c["channel_id"]: {**c, "matched_videos": []} for c in channels([h["channel_id"] for h in hits])}
    for hit in hits:
        if hit["channel_id"] in found:
            found[hit["channel_id"]]["matched_videos"].append(hit["title"])
    return list(found.values())


def comments(video_id: str, n: int = 100, order: str = "relevance") -> list[dict]:
    """Top-level comments of a video: text, a link to the comment, likes, replies. 1 unit per 100.

    Author names and ids are left out. Returns [] when comments are turned off.
    """
    out, token = [], None
    while len(out) < n:
        try:
            data = get("commentThreads", part="snippet", videoId=video_id, maxResults=min(n - len(out), 100),
                       order=order, textFormat="plainText", pageToken=token)
        except YouTubeError as exc:
            if "commentsDisabled" in str(exc):
                return []
            raise
        for thread in data.get("items", []):
            top = thread["snippet"]["topLevelComment"]["snippet"]
            comment_id = thread["snippet"]["topLevelComment"].get("id", thread.get("id", ""))
            out.append({"comment_id": comment_id,
                        "url": f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}",
                        "text": top.get("textOriginal", ""), "likes": top.get("likeCount", 0),
                        "replies": thread["snippet"].get("totalReplyCount", 0),
                        "published_at": top.get("publishedAt", "")})
        token = data.get("nextPageToken")
        if not token:
            break
    return out[:n]


def featured(ref: str) -> list[str]:
    """Channel ids a channel features on its page. 1 unit (+1 for a handle)."""
    data = get("channelSections", part="contentDetails", channelId=_channel_id(ref))
    ids = [cid for s in data.get("items", []) for cid in s.get("contentDetails", {}).get("channels", [])]
    return list(dict.fromkeys(ids))


def subscriptions(ref: str, n: int = 50) -> list[str]:
    """Channel ids a channel subscribes to, if its list is public ([] if private). 1 unit (+1 for a handle)."""
    try:
        data = get("subscriptions", part="snippet", channelId=_channel_id(ref), maxResults=min(n, 50))
    except YouTubeError as exc:
        if "subscriptionForbidden" in str(exc):
            return []
        raise
    return [item["snippet"]["resourceId"]["channelId"] for item in data.get("items", [])]


def band(chans: list[dict], min_subs: int, max_subs: int, include_kids: bool = False) -> list[dict]:
    """Keep channels whose subscriber count is in [min_subs, max_subs]. No API call.

    Drops channels that hide their count, have no videos, or (unless asked) are made for kids.
    """
    return [c for c in chans
            if c["subscribers"] is not None and min_subs <= c["subscribers"] <= max_subs
            and c["videos"] > 0 and (include_kids or not c["made_for_kids"])]


# --- Command line ------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="yt", description="Read-only YouTube Data API tools. Prints JSON.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("channel").add_argument("ref", help="channel id, @handle or URL")
    for name in ("featured", "subscriptions"):
        sub.add_parser(name).add_argument("ref")
    s = sub.add_parser("uploads")
    s.add_argument("ref")
    s.add_argument("-n", type=int, default=10)
    for name in ("videos", "channels"):
        sub.add_parser(name).add_argument("ids", nargs="+")
    for name in ("search", "creators"):
        s = sub.add_parser(name)
        s.add_argument("query")
        s.add_argument("-n", type=int, default=25)
        s.add_argument("--days", type=int, help="only videos from the last N days")
        s.add_argument("--lang", help="relevance language, e.g. en, es")
        s.add_argument("--order", default="relevance", choices=["relevance", "date", "viewCount", "rating"])
        s.add_argument("--region", help="region code, e.g. US, MX")
    s = sub.add_parser("comments")
    s.add_argument("video_id")
    s.add_argument("-n", type=int, default=100)
    s.add_argument("--order", default="relevance", choices=["relevance", "time"])
    s = sub.add_parser("band", help="filter channel JSON from stdin by subscribers")
    s.add_argument("min_subs", type=int)
    s.add_argument("max_subs", type=int)
    s.add_argument("--include-kids", action="store_true")
    a = p.parse_args(argv)

    try:
        if a.cmd == "channel":
            result = channel(a.ref)
        elif a.cmd == "uploads":
            result = uploads(a.ref, a.n)
        elif a.cmd == "videos":
            result = videos(a.ids)
        elif a.cmd == "channels":
            result = channels(a.ids)
        elif a.cmd in ("search", "creators"):
            fn = search if a.cmd == "search" else creators
            result = fn(a.query, a.n, days=a.days, lang=a.lang, order=a.order, region=a.region)
        elif a.cmd == "comments":
            result = comments(a.video_id, a.n, a.order)
        elif a.cmd == "featured":
            result = featured(a.ref)
        elif a.cmd == "subscriptions":
            result = subscriptions(a.ref)
        else:
            result = band(json.load(sys.stdin), a.min_subs, a.max_subs, a.include_kids)
    except YouTubeError as exc:
        print(f"yt: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()
    print(f"yt: {units_used} quota units used", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
