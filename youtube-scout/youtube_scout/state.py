"""Small JSON state files under ``state/``, written atomically, and data retention.

Nothing here holds raw API responses, comment text or commenters. The files are:

* ``quota-<day>.json``: units used per API method on one quota day
* ``run-<date>.json``: the checkpoint of one run, so a crashed run resumes and a
  finished run re-renders without new API calls
* ``keywords.json``: when each keyword was last searched (rotation)
* ``frontier.json``: channels to expand from on the next run (snowball)
* ``reported.json``: channel ids already reported, so they are not repeated
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# YouTube's daily quota resets at midnight Pacific Time.
QUOTA_TZ = ZoneInfo("America/Los_Angeles")
_DATED = re.compile(r"(\d{4}-\d{2}-\d{2})")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def quota_day(now: datetime | None = None) -> str:
    return (now or utc_now()).astimezone(QUOTA_TZ).date().isoformat()


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, data) -> None:
    """Write via a temp file and rename, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def purge_old_files(directories: list[Path], retention_days: int, today: date | None = None) -> list[Path]:
    """Delete dated files (name contains YYYY-MM-DD) older than ``retention_days``."""
    today = today or utc_now().date()
    cutoff = today - timedelta(days=retention_days)
    removed = []
    for directory in directories:
        if not directory.exists():
            continue
        for path in directory.iterdir():
            match = _DATED.search(path.name)
            if not path.is_file() or not match:
                continue
            try:
                stamp = date.fromisoformat(match.group(1))
            except ValueError:
                continue
            if stamp < cutoff:
                path.unlink()
                removed.append(path)
    return removed


def prune_dated_map(mapping: dict[str, str], keep_days: int, today: date | None = None) -> dict[str, str]:
    """Drop entries of ``{key: 'YYYY-MM-DD'}`` older than ``keep_days``."""
    today = today or utc_now().date()
    cutoff = (today - timedelta(days=keep_days)).isoformat()
    return {key: day for key, day in mapping.items() if day >= cutoff}
