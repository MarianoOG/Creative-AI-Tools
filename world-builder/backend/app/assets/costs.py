"""Per-world cost log: one append-only JSON Lines file recording what every render billed.

Runware's ``includeCost`` flag reports the exact amount it charged for that
image, so a Runware entry is exact. OpenAI and Gemini report token usage but
no dollar figure, so their entries are computed here from each provider's
published per-token rate (standard, non-batch tier, checked 2026-11-08) and
marked ``estimated``. Update the rates below if a provider changes its
pricing - nothing else needs to change.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.assets.worlds import world_dir

COST_LOG_FILE = "cost_log.jsonl"

#: Guards appends from parallel renders, the same way ``library._lock`` guards ``world.json``.
_lock = threading.Lock()

#: USD per 1,000,000 tokens.
_OPENAI_RATES = {"text_input": 5.00, "image_input": 8.00, "image_output": 30.00}
_GEMINI_RATES = {"input": 1.50, "output_text": 7.50, "output_image": 30.00}


def _log_path(world: str) -> Path:
    return world_dir(world) / COST_LOG_FILE


def openai_cost(usage: Any) -> Optional[float]:
    """Estimated USD for one OpenAI image render from its reported token usage, or ``None`` if there is none."""
    if usage is None:
        return None
    in_details = usage.input_tokens_details
    text_in = in_details.text_tokens if in_details else usage.input_tokens
    image_in = in_details.image_tokens if in_details else 0
    return (
        text_in * _OPENAI_RATES["text_input"]
        + image_in * _OPENAI_RATES["image_input"]
        + usage.output_tokens * _OPENAI_RATES["image_output"]
    ) / 1_000_000


def _modality_tokens(entries: Optional[List[Any]], modality: str) -> int:
    return sum(
        getattr(entry, "tokens", 0) or 0 for entry in entries or [] if getattr(entry, "modality", None) == modality
    )


def gemini_cost(usage: Any) -> Optional[float]:
    """Estimated USD for one Gemini image render from its reported token usage, or ``None`` if there is none."""
    if usage is None:
        return None
    input_tokens = usage.total_input_tokens or 0
    output_tokens = usage.total_output_tokens or 0
    image_out = _modality_tokens(usage.output_tokens_by_modality, "image")
    other_out = max(output_tokens - image_out, 0) + (usage.total_thought_tokens or 0)
    return (
        input_tokens * _GEMINI_RATES["input"]
        + other_out * _GEMINI_RATES["output_text"]
        + image_out * _GEMINI_RATES["output_image"]
    ) / 1_000_000


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
