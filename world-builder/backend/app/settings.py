"""Where the shared data folder is. Keys come from the environment (``backend/.env`` locally)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

#: Shared with the frontend, which opens the relative paths the API returns.
#: Defaults to ``data/`` at the repository root.
DATA_DIR = Path(os.environ.get("DATA_DIR") or Path(__file__).resolve().parents[3] / "data").resolve()


def relative(path: Path) -> str:
    """A path as the frontend sees it: relative to ``DATA_DIR``."""
    return path.resolve().relative_to(DATA_DIR).as_posix()


def resolve(relative_path: str) -> Path:
    """The inverse of :func:`relative`, refusing anything outside ``DATA_DIR``."""
    path = (DATA_DIR / relative_path).resolve()
    if not path.is_relative_to(DATA_DIR):
        raise ValueError(f"path escapes the data folder: {relative_path}")
    return path
