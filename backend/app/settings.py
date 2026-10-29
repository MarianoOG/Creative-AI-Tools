"""Process-wide settings: where the shared data lives and where the keys come from.

``DATA_DIR`` is the one folder the backend and the frontend share. The backend
reads and writes it; the frontend mounts it read-only and opens whatever path
the API hands back, so every path that crosses the API is relative to it.

Keys are read from the environment. ``backend/.env`` is loaded for local runs;
under docker compose the same file arrives as ``env_file`` and this is a no-op.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BACKEND_DIR / ".env")

#: Defaults to ``<repo>/data`` so a local ``uvicorn`` run and a local
#: ``streamlit run`` meet in the same place without any configuration.
DATA_DIR = Path(os.environ.get("DATA_DIR", BACKEND_DIR.parent / "data")).resolve()

ASSETS_DIR = DATA_DIR / "assets"
YOUTUBE_DIR = DATA_DIR / "youtube"


def relative(path: Path) -> str:
    """A path as the frontend should see it: relative to ``DATA_DIR``."""
    return Path(path).resolve().relative_to(DATA_DIR).as_posix()


def resolve(relative_path: str) -> Path:
    """The inverse of :func:`relative`, refusing anything outside ``DATA_DIR``."""
    path = (DATA_DIR / relative_path).resolve()
    if not path.is_relative_to(DATA_DIR):
        raise ValueError(f"path escapes the data folder: {relative_path}")
    return path
