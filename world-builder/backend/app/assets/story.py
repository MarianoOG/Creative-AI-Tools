"""Episodes, scenes and shots. The folders are the story structure; ``script.json`` holds the words.

    <world>/episodes/<episode>/script.json
    <world>/episodes/<episode>/<scene>/<shot images>

Folders decide which episodes and scenes exist; ``script.json`` decides their
order and content. A scene folder missing from the script is read as an empty
scene, and a script entry without a folder is dropped. A shot's frames are the
images in its scene folder whose name is the shot's id.

script.json::

    {
      "title": "...", "synopsis": "...",
      "scenes": [{
        "id": "scene1", "heading": "INT. KITCHEN - DAY", "summary": "...",
        "characters": ["fox"], "locations": ["kitchen"], "objects": ["lantern"],
        "shots": [{"id": "shot_1", "action": "...", "dialogue": [{"character": "fox", "line": "..."}]}]
      }]
    }
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List

from app.assets.library import images_in, parse_asset
from app.assets.prompt_manager import ASSET_DIRS
from app.assets.worlds import slugify, world_dir

SCRIPT_FILE = "script.json"

Script = Dict[str, Any]


def _natural(name: str) -> list:
    """Sort key that puts ``scene2`` before ``scene10``."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def _segment(parent: Path, name: str, what: str) -> Path:
    if not name or name != slugify(name):
        raise ValueError(f"not a usable {what} name: {name!r}")
    return parent / name


def episodes_dir(world: str) -> Path:
    return world_dir(world) / "episodes"


def episode_dir(world: str, episode: str) -> Path:
    return _segment(episodes_dir(world), episode, "episode")


def scene_dir(world: str, episode: str, scene: str) -> Path:
    return _segment(episode_dir(world, episode), scene, "scene")


def list_episodes(world: str) -> List[str]:
    directory = episodes_dir(world)
    if not directory.is_dir():
        return []
    return sorted((p.name for p in directory.iterdir() if p.is_dir()), key=_natural)


def _clean_shot(raw: Dict) -> Dict:
    return {
        "id": slugify(str(raw.get("id", ""))),
        "action": str(raw.get("action", "")),
        "dialogue": [
            {"character": str(d.get("character", "")), "line": str(d.get("line", ""))}
            for d in raw.get("dialogue", [])
            if str(d.get("line", "")).strip()
        ],
    }


def _clean_scene(raw: Dict, scene_id: str) -> Dict:
    shots, seen = [], set()
    for number, shot in enumerate(raw.get("shots", []), start=1):
        shot = _clean_shot(shot)
        # Ids name the frame files, so they must be unique and non-empty.
        while not shot["id"] or shot["id"] in seen:
            shot["id"] = f"shot_{number}"
            number += 1
        seen.add(shot["id"])
        shots.append(shot)
    return {
        "id": scene_id,
        "heading": str(raw.get("heading", "")),
        "summary": str(raw.get("summary", "")),
        **{folder: [str(name) for name in raw.get(folder, [])] for folder in ASSET_DIRS.values()},
        "shots": shots,
    }


def _normalise(world: str, episode: str, raw: Dict) -> Script:
    """Fit a script to the folders on disk: their scenes, in the script's order."""
    directory = episode_dir(world, episode)
    folders = {p.name for p in directory.iterdir() if p.is_dir()} if directory.is_dir() else set()
    by_id = {scene.get("id"): scene for scene in raw.get("scenes", []) if scene.get("id") in folders}
    order = list(by_id) + sorted(folders - set(by_id), key=_natural)
    return {
        "title": str(raw.get("title") or episode),
        "synopsis": str(raw.get("synopsis", "")),
        "scenes": [_clean_scene(by_id.get(scene_id, {}), scene_id) for scene_id in order],
    }


def read_script(world: str, episode: str) -> Script:
    directory = episode_dir(world, episode)
    if not directory.is_dir():
        raise ValueError(f"no episode called {episode!r}")
    path = directory / SCRIPT_FILE
    raw = json.loads(path.read_text()) if path.is_file() else {}
    return _normalise(world, episode, raw)


def save_script(world: str, episode: str, raw: Dict) -> Script:
    script = _normalise(world, episode, raw)
    (episode_dir(world, episode) / SCRIPT_FILE).write_text(json.dumps(script, indent=2, ensure_ascii=False) + "\n")
    return script


def with_frames(world: str, episode: str, script: Script) -> Script:
    """Attach each shot's images (newest first), and the scene's images no shot claims."""
    for scene in script["scenes"]:
        frames = [
            parse_asset(path, "shot", world) for path in images_in(scene_dir(world, episode, scene["id"]))
        ]
        frames.sort(key=lambda frame: frame["mtime"], reverse=True)
        ids = {shot["id"] for shot in scene["shots"]}
        for shot in scene["shots"]:
            shot["frames"] = [frame for frame in frames if frame["name"] == shot["id"]]
        scene["unassigned"] = [frame for frame in frames if frame["name"] not in ids]
    return script


def _new_dir(parent: Path, name: str, what: str) -> Path:
    slug = slugify(name)
    if not slug:
        raise ValueError(f"an {what} name needs at least one letter or digit")
    directory = parent / slug
    if directory.exists():
        raise ValueError(f"an {what} called {slug!r} already exists")
    directory.mkdir(parents=True)
    return directory


def create_episode(world: str, name: str) -> str:
    directory = _new_dir(episodes_dir(world), name, "episode")
    save_script(world, directory.name, {"title": name.strip()})
    return directory.name


def delete_episode(world: str, episode: str) -> None:
    """Delete an episode with all its scenes and shots. There is no undo."""
    directory = episode_dir(world, episode)
    if not directory.is_dir():
        raise ValueError(f"no episode called {episode!r}")
    shutil.rmtree(directory)


def create_scene(world: str, episode: str, name: str) -> str:
    script = read_script(world, episode)
    directory = _new_dir(episode_dir(world, episode), name, "scene")
    script["scenes"].append({"id": directory.name})
    save_script(world, episode, script)
    return directory.name


def delete_scene(world: str, episode: str, scene: str) -> None:
    """Delete a scene with all its shots. There is no undo."""
    directory = scene_dir(world, episode, scene)
    if not directory.is_dir():
        raise ValueError(f"no scene called {scene!r}")
    shutil.rmtree(directory)
    save_script(world, episode, read_script(world, episode))


def shot_description(scene: Dict, shot: Dict, reference_names: List[str]) -> str:
    """What a shot's frame should show. Dialogue is left out: it is never drawn."""
    lines = [scene["heading"], scene["summary"], shot["action"]]
    if reference_names:
        lines.append("The reference images show, in order: " + ", ".join(reference_names) + ".")
    return "\n".join(line for line in lines if line.strip())
