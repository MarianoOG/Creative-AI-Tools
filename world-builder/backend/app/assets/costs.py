"""Per-world cost log: one append-only JSON Lines file recording what every render billed.

Every image and video goes through Runware, whose ``includeCost`` flag reports
the exact amount it charged, so new entries are exact. Entries from before
(when OpenAI and Gemini were called directly) may be marked ``estimated``.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.assets.worlds import world_dir

COST_LOG_FILE = "cost_log.jsonl"

#: Guards appends from parallel renders, the same way ``library._lock`` guards ``world.json``.
_lock = threading.Lock()


def _log_path(world: str) -> Path:
    return world_dir(world) / COST_LOG_FILE


def record(world: str, asset_type: str, label: str, provider: str, usd: Optional[float], estimated: bool) -> None:
    """Append one render's cost to the world's log. A silent no-op if ``usd`` could not be determined."""
    if usd is None:
        return
    entry = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "asset_type": asset_type,
        "label": label,
        "provider": provider,
        "usd": round(usd, 6),
        "estimated": estimated,
    }
    with _lock:
        path = _log_path(world)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            handle.write(json.dumps(entry) + "\n")


def read_log(world: str) -> List[Dict]:
    """Every entry in the world's cost log, oldest first."""
    path = _log_path(world)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def total(world: str) -> float:
    return sum(entry["usd"] for entry in read_log(world))
