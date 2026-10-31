"""The asset library: the characters, locations and objects ``world.json`` lists, with their variations.

An asset is a name and a description, plus any number of named variations
(for a location, its fixed views), one of which is ``preferred``. A new asset
has none. Each variation points at one image in the asset-type folder, named
``{uuid8}-{name}-{variation}``, and at the uploaded reference images it was
rendered with (kept in the world's ``references/`` folder). Every change here
edits ``world.json`` only: no file is ever removed or renamed.

A *reference* is how scripts point at an image: ``name`` for an asset's
preferred variation, ``name:variation`` for a specific one.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from app.assets.prompt_manager import ASSET_DIRS
from app.assets.worlds import read_world, save_world, slugify, world_dir
from app.settings import relative

Asset = Dict

#: Uploaded reference images, kept so a variation can be regenerated with them.
REFERENCES_DIR = "references"

#: Held across each read-change-save of ``world.json``, so variations rendered in
#: parallel never drop each other. A thread lock: the backend runs one process.
_lock = threading.Lock()


def image_path(world: str, asset_type: str, variation: Dict) -> Path:
    return world_dir(world) / ASSET_DIRS[asset_type] / variation["image"]


def references_dir(world: str) -> Path:
    return world_dir(world) / REFERENCES_DIR


def reference_files(world: str, variation: Dict) -> List[Path]:
    """The uploads a variation was rendered with, those still on disk."""
    return [path for name in variation["references"] if (path := references_dir(world) / name).is_file()]


def variation_named(asset: Asset, name: Optional[str]) -> Optional[Dict]:
    return next((v for v in asset["variations"] if v["name"] == name), None)


def _view(world: str, asset_type: str, asset: Asset) -> Asset:
    """An asset as the API returns it: each variation with its file path and script reference, missing files left out."""
    variations = []
    for variation in asset["variations"]:
        path = image_path(world, asset_type, variation)
        if path.is_file():
            variations.append({
                **variation,
                "path": relative(path),
                "ref": f"{asset['name']}:{variation['name']}",
                "mtime": path.stat().st_mtime,
            })
    return {**asset, "asset_type": asset_type, "world": world, "variations": variations}


def list_assets(world: str, asset_type: Optional[str] = None) -> List[Asset]:
    """One world's assets in ``world.json`` order (one type, or all of them)."""
    data = read_world(world)
    return [
        _view(world, kind, asset)
        for kind, folder in ASSET_DIRS.items()
        if asset_type in (None, kind)
        for asset in data[folder]
    ]


def get_asset(world: str, asset_type: str, name: str) -> Optional[Asset]:
    return next((a for a in read_world(world)[ASSET_DIRS[asset_type]] if a["name"] == name), None)


def view_asset(world: str, asset_type: str, name: str) -> Asset:
    return _view(world, asset_type, get_asset(world, asset_type, name))


def _update(world: str, asset_type: str, name: str, change: Callable[[Asset], None]) -> None:
    """Re-read ``world.json``, apply ``change`` to one asset and save. Re-reading keeps edits made during a render."""
    with _lock:
        data = read_world(world)
        asset = next((a for a in data[ASSET_DIRS[asset_type]] if a["name"] == name), None)
        if asset is None:
            raise ValueError(f"no {asset_type} called {name!r}")
        change(asset)
        save_world(world, data)


def create_asset(world: str, asset_type: str, name: str, description: str) -> Asset:
    """A new asset with its name and description and no variations yet."""
    data = read_world(world)
    assets = data[ASSET_DIRS[asset_type]]
    if any(a["name"] == name for a in assets):
        raise ValueError(f"a {asset_type} called {name!r} already exists")
    assets.append({"name": name, "description": description, "preferred": None, "variations": []})
    save_world(world, data)
    return view_asset(world, asset_type, name)


def edit_asset(
    world: str,
    asset_type: str,
    name: str,
    new_name: Optional[str] = None,
    description: Optional[str] = None,
    preferred: Optional[str] = None,
) -> str:
    """Rename an asset, change its description, or pick its preferred variation. Returns its (new) name.

    A rename does not touch the image files; scripts that point at the old name are updated by the caller.
    """
    new_name = slugify(new_name) if new_name is not None else name
    if not new_name:
        raise ValueError("a name needs at least one letter or digit")
    if new_name != name and get_asset(world, asset_type, new_name) is not None:
        raise ValueError(f"a {asset_type} called {new_name!r} already exists")

    def change(asset: Asset) -> None:
        if preferred is not None:
            if variation_named(asset, preferred) is None:
                raise ValueError(f"{name!r} has no variation called {preferred!r}")
            asset["preferred"] = preferred
        if description is not None:
            asset["description"] = description.strip()
        asset["name"] = new_name

    _update(world, asset_type, name, change)
    return new_name


def put_variation(world: str, asset_type: str, name: str, variation: Dict) -> Asset:
    """Add a variation, or replace the one with the same name (a regenerate). The first one becomes preferred."""
    def change(asset: Asset) -> None:
        existing = variation_named(asset, variation["name"])
        if existing is not None:
            existing.update(variation)
        else:
            asset["variations"].append(variation)
        asset["preferred"] = asset["preferred"] or variation["name"]

    _update(world, asset_type, name, change)
    return view_asset(world, asset_type, name)


def remove_asset(world: str, asset_type: str, name: str) -> None:
    """Drop an asset with every variation from ``world.json``. The files stay."""
    data = read_world(world)
    folder = ASSET_DIRS[asset_type]
    if not any(a["name"] == name for a in data[folder]):
        raise ValueError(f"no {asset_type} called {name!r}")
    data[folder] = [a for a in data[folder] if a["name"] != name]
    save_world(world, data)


def remove_variation(world: str, asset_type: str, name: str, variation: str) -> None:
    """Drop one variation from ``world.json``; if it was preferred, the first one left is. The file stays."""
    def change(asset: Asset) -> None:
        if variation_named(asset, variation) is None:
            raise ValueError(f"{name!r} has no variation called {variation!r}")
        asset["variations"] = [v for v in asset["variations"] if v["name"] != variation]
        if asset["preferred"] == variation:
            asset["preferred"] = asset["variations"][0]["name"] if asset["variations"] else None

    _update(world, asset_type, name, change)


def reference_paths(world: str, asset_type: str) -> Dict[str, Path]:
    """Reference (``name`` for the preferred image, ``name:variation``) -> its image, for one type."""
    paths: Dict[str, Path] = {}
    for asset in read_world(world)[ASSET_DIRS[asset_type]]:
        for variation in asset["variations"]:
            path = image_path(world, asset_type, variation)
            if path.is_file():
                paths[f"{asset['name']}:{variation['name']}"] = path
                if variation["name"] == asset["preferred"]:
                    paths[asset["name"]] = path
    return paths
