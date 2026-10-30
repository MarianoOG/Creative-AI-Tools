"""Worlds: the folders under ``WORLDS_DIR``, each holding one setting's style, assets and episodes.

    <WORLDS_DIR>/<world>/style.txt
    <WORLDS_DIR>/<world>/<asset-type-dir>/<file>
    <WORLDS_DIR>/<world>/episodes/...            (see story.py)
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import List

from app.assets.prompt_manager import ASSET_DIRS
from app.settings import WORLDS_DIR

#: The world listed when there is none on disk yet.
DEFAULT_WORLD = "default"
STYLE_FILE = "style.txt"


def slugify(name: str) -> str:
    """Reduce a typed name to a safe path segment (used for worlds, episodes, scenes and asset names)."""
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
    worlds = sorted(p.name for p in WORLDS_DIR.iterdir() if p.is_dir() and not p.name.startswith("."))
    return worlds or [DEFAULT_WORLD]


def read_style(world: str) -> str:
    """The world's visual style, or ``""`` if it has none yet."""
    path = world_dir(world) / STYLE_FILE
    return path.read_text().strip() if path.is_file() else ""


def write_style(world: str, style: str) -> None:
    directory = world_dir(world)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / STYLE_FILE).write_text(style.strip() + "\n")


def _new_world_dir(name: str) -> Path:
    world = slugify(name)
    if not world:
        raise ValueError("a world name needs at least one letter or digit")
    directory = world_dir(world)
    if directory.exists():
        raise ValueError(f"a world called {world!r} already exists")
    return directory


def create_world(name: str, style: str = "") -> str:
    """Make a new world with its style file and return its slug."""
    directory = _new_world_dir(name)
    directory.mkdir(parents=True)
    write_style(directory.name, style)
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
    """Delete a world and everything in it. There is no undo."""
    directory = world_dir(world)
    if not directory.is_dir():
        raise ValueError(f"no world called {world!r}")
    if len(list_worlds()) <= 1:
        raise ValueError("the last world cannot be deleted")
    shutil.rmtree(directory)


def transfer_asset(path: Path, target_world: str, copy: bool = False) -> Path:
    """Move (or copy) a library file into the same asset-type folder of another world.

    A name already taken in the target is refused rather than suffixed, which
    would break the filename parse.
    """
    if path.parent.name not in ASSET_DIRS.values():
        raise ValueError("only characters, objects and locations move between worlds")
    destination = world_dir(target_world) / path.parent.name / path.name
    if destination == path:
        raise ValueError(f"already in {target_world}")
    if destination.exists():
        raise ValueError(f"a file called {path.name} is already in {target_world}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if copy:
        shutil.copy2(path, destination)
    else:
        shutil.move(path, destination)
    return destination
