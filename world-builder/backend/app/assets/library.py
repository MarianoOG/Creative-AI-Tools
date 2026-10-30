"""The asset library: the file tree under ``DATA_DIR`` is the store, re-read on every listing.

Each file's metadata is in its name, ``{name}_{style}_{uuid8}_{provider}``, and
its world and type are the two folders above it. Older files without the uuid
still parse.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.assets.prompt_manager import ASSET_DIRS, REFERENCE_STYLE_SLUG, STYLES
from app.assets.worlds import list_worlds
from app.settings import DATA_DIR, relative

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

#: The types a scene can use as references.
REFERENCE_TYPES = ("character", "object", "location")

_UID_RE = re.compile(r"^[0-9a-f]{8}$")
#: Longest first, so `watercolor_storybook` wins over a shorter suffix.
_STYLES_BY_LENGTH = sorted({*STYLES, REFERENCE_STYLE_SLUG}, key=len, reverse=True)
_PROVIDERS = ("openai", "gemini")

Asset = Dict[str, Any]


def parse_asset(path: Path, asset_type: str, world: str) -> Asset:
    """Read a file's metadata off its name, right to left (only the name may contain underscores).

    A name that does not fit the scheme becomes a name-only asset rather than being hidden.
    """
    remainder = path.stem
    provider = next((p for p in _PROVIDERS if remainder.endswith(f"_{p}")), "")
    if provider:
        remainder = remainder[: -len(provider) - 1]

    uid: Optional[str] = None
    head, _, tail = remainder.rpartition("_")
    if head and _UID_RE.match(tail):
        uid, remainder = tail, head

    style = next((s for s in _STYLES_BY_LENGTH if remainder.endswith(f"_{s}")), "")
    if style:
        remainder = remainder[: -len(style) - 1]

    name = remainder or path.stem
    return {
        "path": relative(path),
        "asset_type": asset_type,
        "world": world,
        "name": name,
        "style": style,
        "provider": provider,
        "uid": uid,
        "mtime": path.stat().st_mtime,
        "label": " · ".join(part for part in (name, style, provider) if part),
    }


def is_asset(path: Path) -> bool:
    """Whether ``path`` (resolved) is a file in a world's asset-type folder."""
    parts = path.relative_to(DATA_DIR).parts
    return len(parts) == 3 and parts[1] in ASSET_DIRS.values() and path.is_file()


def list_assets(world: Optional[str] = None) -> List[Asset]:
    """Every asset of one world (or of every world), newest first."""
    assets = [
        parse_asset(path, asset_type, world_name)
        for world_name in ([world] if world else list_worlds())
        for asset_type, dir_name in ASSET_DIRS.items()
        if (DATA_DIR / world_name / dir_name).is_dir()
        for path in (DATA_DIR / world_name / dir_name).iterdir()
        if path.suffix.lower() in IMAGE_SUFFIXES and path.is_file()
    ]
    return sorted(assets, key=lambda asset: asset["mtime"], reverse=True)


def facets(assets: List[Asset]) -> Dict[str, List[str]]:
    """The filter options a listing actually contains."""
    return {
        "asset_type": [t for t in ASSET_DIRS if any(a["asset_type"] == t for a in assets)],
        "style": sorted({a["style"] for a in assets if a["style"]}),
        "provider": sorted({a["provider"] for a in assets if a["provider"]}),
    }
