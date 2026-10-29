"""Settings and the package's one error type.

``YOUTUBE_API_KEY`` and ``YOUTUBE_SCOUT_DATA_DIR`` come from the environment;
``youtube-scout/.env`` is loaded first when present (real variables win).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_DIR / ".env")


class ScoutError(Exception):
    """Anything the caller should report: missing key, API failure, unknown search or channel."""


def api_key() -> str:
    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not key:
        raise ScoutError(
            "YOUTUBE_API_KEY is not set. Add it to youtube-scout/.env or the environment "
            "(get a key at https://console.cloud.google.com/)."
        )
    return key


def data_dir() -> Path:
    """Read on every call, so changing the variable at runtime takes effect."""
    return Path(os.getenv("YOUTUBE_SCOUT_DATA_DIR") or PROJECT_DIR / "data").expanduser()


def searches_dir() -> Path:
    return data_dir() / "searches"
