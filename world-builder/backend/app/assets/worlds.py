"""Worlds - the folder between ``assets/`` and the four asset-type directories.

A world is a setting: its own characters, objects, locations and scenes, kept
apart from every other project so a scene can never be composed out of designs
that were never meant to share a universe. On disk that is simply

    <DATA_DIR>/assets/<world>/<asset-type-dir>/<file>

The world is a *path segment*, never a token in the filename. Filenames already
encode name, style, uuid and provider and are parsed right to left; putting a
free-form world name in there too would make that parse ambiguous.

This module is the only place that knows the world layer exists. It deliberately
imports nothing from :mod:`app.assets.library` - the dependency runs the other
way, because ``list_assets`` needs :func:`list_worlds` to know where to look.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import List

from app.assets.generation import DEFAULT_WORLD, IMG_DIR
from app.assets.prompt_manager import ASSET_DIRS

#: Names a world may not take: they would be indistinguishable from the legacy
#: pre-world layout that :func:`ensure_migrated` looks for.
_RESERVED = set(ASSET_DIRS.values())


def slugify(name: str) -> str:
    """Reduce a typed name to something safe to use as a path segment.

    Shared by world names and asset names: both end up on disk, and
    ``save_image`` rejects path separators outright while ``Path(filename).stem``
    would quietly truncate ``fox.hero`` to ``fox``.
    """
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def world_dir(world: str) -> Path:
    """The folder for one world, refusing anything that could escape the library.

    ``world != slugify(world)`` is the whole guard: separators, dots and leading
    or trailing junk cannot survive the slug, so ``..`` and ``a/b`` are rejected
    before they ever reach the filesystem.
    """
    if not world or world != slugify(world):
        raise ValueError(f"not a usable world name: {world!r}")
    return IMG_DIR / world


def list_worlds() -> List[str]:
    """Every world on disk, alphabetically. Never empty - falls back to default.

    Uncached: it is one ``iterdir`` of a directory holding a handful of entries,
    and a stale list here would hide a world the user just created.
    """
    if not IMG_DIR.is_dir():
        return [DEFAULT_WORLD]
    worlds = sorted(
        path.name
        for path in IMG_DIR.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )
    return worlds or [DEFAULT_WORLD]


def create_world(name: str) -> str:
    """Make a new, empty world and return its slug.

    The directory is created on disk: worlds are enumerated by listing the
    library folder, so a world with no folder would not exist. The asset-type
    subdirectories stay absent until something is written - ``save_image``
    creates them.
    """
    world = slugify(name)
    if not world:
        raise ValueError("a world name needs at least one letter or digit")
    if world in _RESERVED:
        raise ValueError(f"{world!r} is reserved for the asset-type folders")

    directory = world_dir(world)
    if directory.exists():
        raise ValueError(f"a world called {world!r} already exists")
    directory.mkdir(parents=True)
    return world


def rename_world(world: str, new_name: str) -> str:
    """Rename a world in place and return the new slug.

    Only the segment above the assets changes, so every filename - and every
    piece of metadata encoded in it - is untouched.
    """
    target = slugify(new_name)
    if not target:
        raise ValueError("a world name needs at least one letter or digit")
    if target in _RESERVED:
        raise ValueError(f"{target!r} is reserved for the asset-type folders")
    if target == world:
        return world

    source = world_dir(world)
    if not source.is_dir():
        raise ValueError(f"no world called {world!r}")
    destination = world_dir(target)
    if destination.exists():
        raise ValueError(f"a world called {target!r} already exists")

    source.rename(destination)
    return target


def delete_world(world: str) -> None:
    """Delete a world and everything inside it. There is no undo - the data
    folder is not tracked by git."""
    directory = world_dir(world)
    if not directory.is_dir():
        raise ValueError(f"no world called {world!r}")
    if len(list_worlds()) <= 1:
        raise ValueError("the last world cannot be deleted")
    shutil.rmtree(directory)


def _destination(path: Path, target_world: str) -> Path:
    """Where ``path`` would land in ``target_world``, with every guard applied.

    Refuses a name already present in the target rather than suffixing it: a
    ``_2`` on the stem breaks the right-to-left filename parse and would degrade
    the file to a name-only asset in the gallery.
    """
    source = Path(path).resolve()
    root = IMG_DIR.resolve()
    if not source.is_file() or not source.is_relative_to(root):
        raise ValueError(f"not a library asset: {path}")
    if source.parent.name not in _RESERVED:
        raise ValueError(f"not inside an asset-type folder: {path}")

    directory = world_dir(target_world) / source.parent.name
    destination = directory / source.name
    if destination.resolve() == source:
        raise ValueError(f"already in {target_world}")
    if destination.exists():
        raise ValueError(f"a file called {source.name} is already in {target_world}")

    directory.mkdir(parents=True, exist_ok=True)
    return destination


def move_asset(path: Path, target_world: str) -> Path:
    """Move one asset into another world and return its new path."""
    destination = _destination(path, target_world)
    shutil.move(str(Path(path).resolve()), str(destination))
    return destination


def copy_asset(path: Path, target_world: str) -> Path:
    """Duplicate one asset into another world and return the new path."""
    destination = _destination(path, target_world)
    shutil.copy2(Path(path).resolve(), destination)
    return destination


def ensure_migrated() -> List[str]:
    """Move a pre-world ``assets/<asset-type>/`` tree into ``assets/default/``.

    Idempotent, and a precondition of every other function here: until it has
    run, :func:`list_worlds` reads ``assets/characters/`` as a world called
    "characters". The backend runs it once at startup. Returns the names of any files left behind because the target
    already held that name.
    """
    skipped: List[str] = []
    for dir_name in ASSET_DIRS.values():
        legacy = IMG_DIR / dir_name
        if not legacy.is_dir():
            continue

        target = IMG_DIR / DEFAULT_WORLD / dir_name
        target.mkdir(parents=True, exist_ok=True)
        for path in legacy.iterdir():
            if not path.is_file():
                continue
            destination = target / path.name
            if destination.exists():
                skipped.append(f"{dir_name}/{path.name}")
                continue
            shutil.move(str(path), str(destination))

        if not any(legacy.iterdir()):
            legacy.rmdir()
    return skipped


if __name__ == '__main__':
    left_behind = ensure_migrated()
    print(f"Worlds: {', '.join(list_worlds())}")
    if left_behind:
        print("Left in place (name already taken in default):")
        for name in left_behind:
            print(f"  {name}")
