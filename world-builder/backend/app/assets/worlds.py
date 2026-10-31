"""Worlds: the folders under ``WORLDS_DIR``, each holding one setting's ``world.json``, images and episodes.

    <WORLDS_DIR>/<world>/world.json             style, characters, locations, objects
    <WORLDS_DIR>/<world>/<asset-type-dir>/<file>
    <WORLDS_DIR>/<world>/episodes/...            (see story.py)

``world.json`` decides which assets exist, the way ``script.json`` decides the
scenes: an image in a folder that it does not name is an orphan and is never
shown. A world from before ``world.json`` gets one on first read, built from its
``style.txt`` and the newest file of each asset name.

Nothing in the app ever removes a file: deleting a world, an episode or a scene
moves its folder into a hidden ``.deleted/`` folder next to it.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.assets.prompt_manager import ASSET_DIRS, LEGACY_STYLE_SLUGS, LOCATION_VIEWS
from app.settings import WORLDS_DIR

#: The world listed when there is none on disk yet.
DEFAULT_WORLD = "default"
WORLD_FILE = "world.json"
#: Where the style lived before ``world.json``. Only read, to bootstrap.
LEGACY_STYLE_FILE = "style.txt"
#: The variation name a pre-``world.json`` character or object file gets.
LEGACY_VARIATION = "original"
#: Where deleted worlds, episodes and scenes are moved, inside their parent folder.
DELETED_DIR = ".deleted"

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

World = Dict[str, Any]

_UID_RE = re.compile(r"^[0-9a-f]{8}$")
#: Longest first, so `watercolor_storybook` wins over a shorter suffix.
_STYLES_BY_LENGTH = sorted(LEGACY_STYLE_SLUGS, key=len, reverse=True)
_LEGACY_PROVIDERS = ("openai", "gemini")


def slugify(name: str) -> str:
    """Reduce a typed name to a safe path segment (used for worlds, episodes, scenes, assets and variations)."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def world_dir(world: str) -> Path:
    """The folder for one world. Anything that is not already a slug (``..``, ``a/b``) is refused."""
    if not world or world != slugify(world):
        raise ValueError(f"not a usable world name: {world!r}")
    return WORLDS_DIR / world


def list_worlds() -> List[str]:
    """Every world on disk, alphabetically. Never empty: falls back to the default world."""
    if not WORLDS_DIR.is_dir():
        return [DEFAULT_WORLD]
    return subfolders(WORLDS_DIR) or [DEFAULT_WORLD]


def subfolders(directory: Path) -> List[str]:
    """The visible folders in ``directory`` (not ``.deleted`` or other hidden ones), alphabetically."""
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.iterdir() if p.is_dir() and not p.name.startswith("."))


def move_to_deleted(directory: Path) -> None:
    """"Delete" a folder by moving it into ``.deleted/`` beside it, under a unique name. No file is removed."""
    trash = directory.parent / DELETED_DIR
    trash.mkdir(exist_ok=True)
    directory.rename(trash / f"{directory.name}-{uuid.uuid4().hex[:8]}")


def images_in(directory: Path) -> List[Path]:
    if not directory.is_dir():
        return []
    return [p for p in directory.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES and p.is_file()]


def first_variation(asset_type: str) -> str:
    return next(iter(LOCATION_VIEWS)) if asset_type == "location" else LEGACY_VARIATION


def legacy_name(path: Path) -> Tuple[str, str]:
    """``(name, provider)`` of a file named before ``world.json``: ``{name}[_{style}][_{uuid8}]_{provider}``.

    Read right to left, since only the name may contain underscores.
    """
    remainder = path.stem
    provider = next((p for p in _LEGACY_PROVIDERS if remainder.endswith(f"_{p}")), "")
    if provider:
        remainder = remainder[: -len(provider) - 1]
    head, _, tail = remainder.rpartition("_")
    if head and _UID_RE.match(tail):
        remainder = head
    style = next((s for s in _STYLES_BY_LENGTH if remainder.endswith(f"_{s}")), "")
    if style:
        remainder = remainder[: -len(style) - 1]
    return remainder or path.stem, provider


def _bootstrap(directory: Path) -> World:
    """A ``world.json`` for a world from before it: its ``style.txt`` and the newest file per asset name."""
    style_path = directory / LEGACY_STYLE_FILE
    world: World = {"style": style_path.read_text().strip() if style_path.is_file() else ""}
    for asset_type, folder in ASSET_DIRS.items():
        newest: Dict[str, Tuple[Path, str]] = {}
        for path in sorted(images_in(directory / folder), key=lambda p: p.stat().st_mtime):
            name, provider = legacy_name(path)
            newest[slugify(name) or name] = (path, provider)
        world[folder] = [
            {
                "name": name,
                "description": "",
                "variations": [{
                    "name": first_variation(asset_type),
                    "description": "",
                    "provider": provider,
                    "image": path.name,
                }],
            }
            for name, (path, provider) in sorted(newest.items())
        ]
    return world


def _clean_variation(raw: Dict) -> Optional[Dict]:
    name, image = slugify(str(raw.get("name", ""))), str(raw.get("image", ""))
    if not name or not image or Path(image).name != image:
        return None
    return {
        "name": name,
        "description": str(raw.get("description", "")),
        "provider": str(raw.get("provider", "")),
        "image": image,
        "references": [str(r) for r in raw.get("references", []) if str(r) and Path(str(r)).name == str(r)],
    }


def _clean_asset(raw: Dict) -> Optional[Dict]:
    name = slugify(str(raw.get("name", "")))
    variations, seen = [], set()
    for variation in raw.get("variations", []):
        variation = _clean_variation(variation)
        if variation and variation["name"] not in seen:
            seen.add(variation["name"])
            variations.append(variation)
    if not name:
        return None
    names = [v["name"] for v in variations]
    # The preferred variation is always one that exists; ``None`` only while there are none.
    preferred = raw.get("preferred") if raw.get("preferred") in names else (names[0] if names else None)
    return {
        "name": name,
        "description": str(raw.get("description", "")),
        "preferred": preferred,
        "variations": variations,
    }


def _normalise(raw: Dict) -> World:
    world: World = {"style": str(raw.get("style", "")).strip()}
    for folder in ASSET_DIRS.values():
        assets, seen = [], set()
        for asset in raw.get(folder, []):
            asset = _clean_asset(asset)
            if asset and asset["name"] not in seen:
                seen.add(asset["name"])
                assets.append(asset)
        world[folder] = assets
    return world


def write_json(path: Path, data: Any) -> None:
    """Write ``data`` to ``path`` atomically, so a request reading it while a render saves never sees half a file."""
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def read_world(world: str) -> World:
    """The world's ``world.json``, written first if the world predates it."""
    directory = world_dir(world)
    path = directory / WORLD_FILE
    if path.is_file():
        return _normalise(json.loads(path.read_text()))
    if not directory.is_dir():
        return _normalise({})
    return save_world(world, _bootstrap(directory))


def save_world(world: str, raw: Dict) -> World:
    data = _normalise(raw)
    directory = world_dir(world)
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / WORLD_FILE, data)
    return data


def read_style(world: str) -> str:
    """The world's visual style, or ``""`` if it has none yet."""
    return read_world(world)["style"]


def write_style(world: str, style: str) -> None:
    save_world(world, {**read_world(world), "style": style})


def _new_world_dir(name: str) -> Path:
    world = slugify(name)
    if not world:
        raise ValueError("a world name needs at least one letter or digit")
    directory = world_dir(world)
    if directory.exists():
        raise ValueError(f"a world called {world!r} already exists")
    return directory


def create_world(name: str, style: str = "") -> str:
    """Make a new world with its ``world.json`` and return its slug."""
    directory = _new_world_dir(name)
    directory.mkdir(parents=True)
    save_world(directory.name, {"style": style})
    return directory.name


def rename_world(world: str, new_name: str) -> str:
    """Rename a world in place and return the new slug."""
    if slugify(new_name) == world:
        return world
    source = world_dir(world)
    if not source.is_dir():
        raise ValueError(f"no world called {world!r}")
    destination = _new_world_dir(new_name)
    source.rename(destination)
    return destination.name


def delete_world(world: str) -> None:
    """Hide a world: its folder moves into ``.deleted/``."""
    directory = world_dir(world)
    if not directory.is_dir():
        raise ValueError(f"no world called {world!r}")
    if len(list_worlds()) <= 1:
        raise ValueError("the last world cannot be deleted")
    move_to_deleted(directory)
