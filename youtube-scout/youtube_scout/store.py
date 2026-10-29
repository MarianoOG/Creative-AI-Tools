"""Saved searches - one JSON file per search under ``<data dir>/searches/``.

A search spends quota, so its full result (channels, their videos and metrics)
is kept: filtering, sorting and reopening it later cost no API call. The file
format is ``{id, keyword, created_at, channels: {channel_id: channel}}``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .config import ScoutError, searches_dir
from .metrics import compute_metrics

#: Search ids are generated here and are safe filenames; anything else is refused.
_ID_RE = re.compile(r"^[0-9TZ]{16}_[a-z0-9_]*$")


def save_search(keyword: str, channels: Dict[str, Dict]) -> Dict:
    """Write one search and return its record."""
    now = datetime.now(timezone.utc)
    slug = re.sub(r"[^a-z0-9]+", "_", keyword.lower()).strip("_")[:40]
    folder = searches_dir()
    folder.mkdir(parents=True, exist_ok=True)
    search_id = base_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{slug}"
    suffix = 1
    while (folder / f"{search_id}.json").exists():  # same keyword within one second
        suffix += 1
        search_id = f"{base_id}_{suffix}"
    record = {
        "id": search_id,
        "keyword": keyword,
        "created_at": now.isoformat(),
        "channels": channels,
    }
    (folder / f"{record['id']}.json").write_text(
        json.dumps(record, ensure_ascii=False), encoding="utf-8"
    )
    return record


def load_search(search_id: str) -> Dict:
    """One saved search with its channels. Raises ``ScoutError`` if unknown."""
    path = searches_dir() / f"{search_id}.json"
    if not _ID_RE.match(search_id) or not path.is_file():
        raise ScoutError(f"No saved search {search_id!r}")
    record = json.loads(path.read_text(encoding="utf-8"))
    for channel in record["channels"].values():
        _upgrade(channel)
    return record


def list_searches() -> List[Dict]:
    """Every saved search, newest first: ``[{id, keyword, created_at, count}]``."""
    folder = searches_dir()
    if not folder.is_dir():
        return []
    searches = []
    for path in sorted(folder.glob("*.json"), reverse=True):
        record = json.loads(path.read_text(encoding="utf-8"))
        searches.append(
            {
                "id": record["id"],
                "keyword": record["keyword"],
                "created_at": record["created_at"],
                "count": len(record["channels"]),
            }
        )
    return searches


def find_search(keyword: str) -> Optional[Dict]:
    """The newest saved search for ``keyword`` (case-insensitive), or ``None``."""
    wanted = keyword.strip().casefold()
    for summary in list_searches():
        if summary["keyword"].strip().casefold() == wanted:
            return load_search(summary["id"])
    return None


def _upgrade(channel: Dict) -> None:
    """Bring files saved by older versions up to the current shape (a no-op otherwise)."""
    for item in [channel, *channel.get("videos", [])]:
        for key in ("channel_url", "url"):
            if item.get(key, "").startswith("youtube.com/"):
                item[key] = f"https://www.{item[key]}"
    compute_metrics(channel)
