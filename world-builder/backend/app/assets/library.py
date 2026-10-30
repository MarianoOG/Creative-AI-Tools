"""The asset library: the file tree under ``WORLDS_DIR`` is the store, re-read on every listing.

Each file's metadata is in its name, ``{name}_{uuid8}_{provider}``, and its
world and type are the folders above it. Older files carry a style slot
(``{name}_{style}_{uuid8}_{provider}``) or no uuid, and still parse.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.assets.prompt_manager import ASSET_DIRS, LEGACY_STYLE_SLUGS
from app.assets.worlds import list_worlds
from app.settings import WORLDS_DIR, relative, resolve

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

_UID_RE = re.compile(r"^[0-9a-f]{8}$")
#: Longest first, so `watercolor_storybook` wins over a shorter suffix.
_STYLES_BY_LENGTH = sorted(LEGACY_STYLE_SLUGS, key=len, reverse=True)
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
        "provider": provider,
        "uid": uid,
        "mtime": path.stat().st_mtime,
        "label": " · ".join(part for part in (name, provider) if part),
    }


def images_in(directory: Path) -> List[Path]:
    if not directory.is_dir():
        return []
    return [p for p in directory.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES and p.is_file()]


def is_asset(path: Path) -> bool:
    """Whether ``path`` (resolved) is an image in a world's asset-type folder or in a scene folder."""
    if not path.is_relative_to(WORLDS_DIR) or not path.is_file():
        return False
    parts = path.relative_to(WORLDS_DIR).parts
    asset_file = len(parts) == 3 and parts[1] in ASSET_DIRS.values()
    shot_file = len(parts) == 5 and parts[1] == "episodes"
    return (asset_file or shot_file) and path.suffix.lower() in IMAGE_SUFFIXES


def list_assets(world: Optional[str] = None, asset_type: Optional[str] = None) -> List[Asset]:
    """Every character, object and location of one world (or of every world), newest first."""
    assets = [
        parse_asset(path, kind, world_name)
        for world_name in ([world] if world else list_worlds())
        for kind, dir_name in ASSET_DIRS.items()
        if asset_type in (None, kind)
        for path in images_in(WORLDS_DIR / world_name / dir_name)
    ]
    return sorted(assets, key=lambda asset: asset["mtime"], reverse=True)


def newest_by_name(world: str, asset_type: str) -> Dict[str, Path]:
    """Asset name -> its newest file, so a reference is sent once and not once per provider."""
    newest: Dict[str, Path] = {}
    for asset in reversed(list_assets(world, asset_type)):
        newest[asset["name"]] = resolve(asset["path"])
    return newest
