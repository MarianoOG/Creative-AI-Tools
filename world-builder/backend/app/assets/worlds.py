"""Worlds: the folders under ``DATA_DIR``, each holding one setting's assets.

    <DATA_DIR>/<world>/<asset-type-dir>/<file>
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import List

from app.settings import DATA_DIR

#: The world listed when there is none on disk yet.
DEFAULT_WORLD = "default"


def slugify(name: str) -> str:
    """Reduce a typed name to a safe path segment (used for worlds and asset names)."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def world_dir(world: str) -> Path:
    """The folder for one world. Anything that is not already a slug (``..``, ``a/b``) is refused."""
    if not world or world != slugify(world):
        raise ValueError(f"not a usable world name: {world!r}")
    return DATA_DIR / world


def list_worlds() -> List[str]:
    """Every world on disk, alphabetically. Never empty: falls back to the default world."""
    if not DATA_DIR.is_dir():
        return [DEFAULT_WORLD]
    worlds = sorted(p.name for p in DATA_DIR.iterdir() if p.is_dir() and not p.name.startswith("."))
    return worlds or [DEFAULT_WORLD]


def _new_world_dir(name: str) -> Path:
    world = slugify(name)
    if not world:
        raise ValueError("a world name needs at least one letter or digit")
    directory = world_dir(world)
    if directory.exists():
        raise ValueError(f"a world called {world!r} already exists")
    return directory


def create_world(name: str) -> str:
    """Make a new, empty world and return its slug."""
    directory = _new_world_dir(name)
    directory.mkdir(parents=True)
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
