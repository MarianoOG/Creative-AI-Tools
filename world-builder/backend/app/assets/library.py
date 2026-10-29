"""Asset Library - read the img/ tree as the one source of truth.

There is no database. Every generated file already carries its own metadata in
its name (``{name}_{style}_{uuid8}_{provider}``) and its world in the folder
above its type (``assets/<world>/<asset-type-dir>/``), so the listing is a
directory walk plus a filename parse. It is not cached: a world holds a few
hundred files at most, and an uncached walk can never show a stale library.

Files written before the uuid was introduced use ``{name}_{style}_{provider}``
and still parse - :func:`parse_stem` simply reports ``uid=None`` for them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.assets.generation import IMG_DIR
from app.assets.prompt_manager import ASSET_DIRS, REFERENCE_STYLE_SLUG, STYLES
from app.assets.worlds import list_worlds
from app.settings import relative

#: Extensions the two providers can produce, plus webp for uploaded material.
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

#: The three types a scene can draw on as references. Scenes are excluded: a
#: scene is a finished frame, not a design sheet to build another frame from.
REFERENCE_TYPES = ("character", "object", "location")

#: The uuid slug appended by ``generate_asset``. No style key ends in an 8-char
#: hex run (`2d`, `cel`, `clay`, `storybook`, `1930s`, ...), so this pattern
#: cleanly separates the current naming scheme from the legacy one.
_UID_RE = re.compile(r"^[0-9a-f]{8}$")

#: Every token that can occupy the style slot of a filename: the style keys plus
#: the slug a styleless (``style=None``) render is written under, which is not a
#: key of ``STYLES`` and so has to be added by hand. Longest first, so
#: `watercolor_storybook` is matched before `storybook` could ever be considered
#: a style on its own.
_STYLES_BY_LENGTH = sorted({*STYLES, REFERENCE_STYLE_SLUG}, key=len, reverse=True)

_PROVIDERS = ("openai", "gemini")


@dataclass(frozen=True)
class Asset:
    """One image on disk, with everything its filename encodes."""

    path: Path
    asset_type: str
    #: The folder above the asset type. Read off the path, never off the name.
    world: str
    name: str
    style: str
    provider: str
    uid: Optional[str]
    mtime: float

    @property
    def label(self) -> str:
        """One-line description for captions and multiselect options."""
        parts = [self.name] + [p for p in (self.style, self.provider) if p]
        return " · ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """The API shape: the path relative to the data folder, plus the label."""
        return {
            "path": relative(self.path),
            "asset_type": self.asset_type,
            "world": self.world,
            "name": self.name,
            "style": self.style,
            "provider": self.provider,
            "uid": self.uid,
            "mtime": self.mtime,
            "label": self.label,
        }


def parse_stem(
    stem: str, asset_type: str, world: str, path: Path, mtime: float
) -> Asset:
    """Read ``{name}_{style}_{uuid8}_{provider}`` back into an :class:`Asset`.

    Parsed right to left, because the name is the only part that may itself
    contain underscores. Anything that does not fit - a hand-dropped file, a
    scheme from the future - degrades to a name-only asset rather than being
    hidden from the gallery.

    ``world`` is passed in rather than parsed: it lives in the path, which is
    exactly what keeps this parse unambiguous for legacy uuid-less filenames.
    """
    remainder = stem
    provider = ""
    uid: Optional[str] = None
    style = ""

    for candidate in _PROVIDERS:
        if remainder.endswith(f"_{candidate}"):
            provider = candidate
            remainder = remainder[: -len(candidate) - 1]
            break

    head, _, tail = remainder.rpartition("_")
    if head and _UID_RE.match(tail):
        uid = tail
        remainder = head

    for candidate in _STYLES_BY_LENGTH:
        if remainder.endswith(f"_{candidate}"):
            style = candidate
            remainder = remainder[: -len(candidate) - 1]
            break

    return Asset(
        path=path,
        asset_type=asset_type,
        world=world,
        name=remainder or stem,
        style=style,
        provider=provider,
        uid=uid,
        mtime=mtime,
    )


def list_assets(
    asset_type: Optional[str] = None, world: Optional[str] = None
) -> List[Asset]:
    """Every asset on disk, newest first. ``None`` means every type / every world."""
    types = [asset_type] if asset_type else list(ASSET_DIRS)
    worlds = [world] if world else list_worlds()
    assets: List[Asset] = []
    for world_name in worlds:
        for type_name in types:
            directory = IMG_DIR / world_name / ASSET_DIRS[type_name]
            if not directory.is_dir():
                continue
            for path in directory.iterdir():
                if path.suffix.lower() not in IMAGE_SUFFIXES or not path.is_file():
                    continue
                assets.append(
                    parse_stem(
                        path.stem, type_name, world_name, path, path.stat().st_mtime
                    )
                )
    return sorted(assets, key=lambda a: a.mtime, reverse=True)


def delete_asset(path: Path) -> None:
    """Delete one generated image, refusing anything outside the library."""
    resolved = path.resolve()
    if not resolved.is_relative_to(IMG_DIR.resolve()):
        raise ValueError(f"refusing to delete outside the image directory: {path}")
    resolved.unlink()


def filter_assets(
    assets: List[Asset],
    asset_type: Optional[str] = None,
    style: Optional[str] = None,
    provider: Optional[str] = None,
    world: Optional[str] = None,
) -> List[Asset]:
    """Narrow a listing. ``None`` on any field means "no constraint"."""
    return [
        asset
        for asset in assets
        if (asset_type is None or asset.asset_type == asset_type)
        and (style is None or asset.style == style)
        and (provider is None or asset.provider == provider)
        and (world is None or asset.world == world)
    ]


def facets(assets: List[Asset]) -> Dict[str, List[str]]:
    """The filter options a listing actually contains, for the library's selects."""
    return {
        "asset_type": [t for t in ASSET_DIRS if any(a.asset_type == t for a in assets)],
        "style": sorted({a.style for a in assets if a.style}),
        "provider": sorted({a.provider for a in assets if a.provider}),
    }
