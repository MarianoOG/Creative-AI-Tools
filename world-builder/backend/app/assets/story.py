"""Episodes, scenes and shots. The folders are the story structure; ``script.json`` holds the words.

    <world>/episodes/<episode>/script.json
    <world>/episodes/<episode>/<scene>/<shot images>

Folders decide which episodes and scenes exist; ``script.json`` decides their
order and content. A scene folder missing from the script is read as an empty
scene, and a script entry without a folder is dropped. The episode's
``aspect_ratio`` is used for every shot in it.

A shot's ``final`` is its frame, saved in its scene folder as
``{uuid8}-{shot}-final``; regenerating points it at a new file and leaves the
old one on disk. ``image`` names an older storyboard preview, kept as it is;
nothing renders one any more. ``final_provider`` is the model the last
pass of the episode used (one of ``FINAL_PROVIDERS``).

A shot's ``id`` is its place in the scene (``shot1``, ``shot2``...), set on
every read and save, so shots cannot be named. Removing one moves the later
ones up, each keeping its frames.

A shot's ``type`` is its framing, one of ``SHOT_TYPES`` (or ``null`` when not
picked); it leads the shot's description (:func:`shot_description`).

script.json::

    {
      "title": "...", "synopsis": "...", "aspect_ratio": "landscape", "final_provider": "gemini",
      "scenes": [{
        "id": "scene1", "heading": "INT. KITCHEN - DAY", "summary": "...",
        "characters": ["fox", "fox:older"], "locations": ["kitchen"], "objects": ["lantern"],
        "shots": [{"id": "shot1", "type": "Wide shot", "action": "...", "image": "1a2b3c4d-shot1.png", "final": "5e6f7a8b-shot1-final.jpg"}]
      }]
    }

Scripts from before ``image`` existed get their shot's newest frame on read.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.assets.generation import ASPECT_RATIOS, DEFAULT_FINAL_PROVIDER, FINAL_PROVIDERS
from app.assets.prompt_manager import ASSET_DIRS
from app.assets.worlds import (
    child_dir, existing_dir, images_in, legacy_name, move_to_deleted, new_child_dir, slugify, subfolders, world_dir,
    write_json,
)
from app.settings import relative

SCRIPT_FILE = "script.json"

#: The framings a shot can have, from the widest to the tightest.
SHOT_TYPES = [
    "Establishing shot", "Panorama", "Extreme wide shot", "Wide shot", "Full shot", "Medium wide shot",
    "Medium shot", "Medium close-up", "Close-up", "Extreme close-up", "Detail shot",
    "Over-the-shoulder shot", "Two shot", "Point-of-view shot", "Low angle shot", "High angle shot",
    "Aerial shot",
]

Script = Dict[str, Any]

#: Held across each read-change-save of a ``script.json``, so shots rendered in
#: parallel never drop each other's frame. A thread lock: the backend runs one process.
_lock = threading.RLock()


def _natural(name: str) -> list:
    """Sort key that puts ``scene2`` before ``scene10``."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def episodes_dir(world: str) -> Path:
    return world_dir(world) / "episodes"


def episode_dir(world: str, episode: str) -> Path:
    return child_dir(episodes_dir(world), episode, "episode")


def scene_dir(world: str, episode: str, scene: str) -> Path:
    return child_dir(episode_dir(world, episode), scene, "scene")


def list_episodes(world: str) -> List[str]:
    return sorted(subfolders(episodes_dir(world)), key=_natural)


def _legacy_frame(folder: Path, shot_id: str) -> Optional[str]:
    """The newest image named after the shot, for scripts from before ``image``."""
    frames = [path for path in images_in(folder) if legacy_name(path)[0] == shot_id]
    return max(frames, key=lambda path: path.stat().st_mtime).name if frames else None


def _clean_shot(raw: Dict, folder: Path) -> Dict:
    shot_id = slugify(str(raw.get("id", "")))
    image = raw["image"] if "image" in raw else _legacy_frame(folder, shot_id)
    return {
        "id": shot_id,
        "type": raw.get("type") if raw.get("type") in SHOT_TYPES else None,
        "action": str(raw.get("action", "")),
        "image": Path(str(image)).name if image else None,
        "final": Path(str(raw["final"])).name if raw.get("final") else None,
    }


def _clean_scene(raw: Dict, scene_id: str, folder: Path) -> Dict:
    shots = [_clean_shot(shot, folder) for shot in raw.get("shots", [])]
    # Shots are not named: each one's id is its place in the scene.
    for number, shot in enumerate(shots, start=1):
        shot["id"] = f"shot{number}"
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
    folders = set(subfolders(directory))
    by_id = {scene.get("id"): scene for scene in raw.get("scenes", []) if scene.get("id") in folders}
    order = list(by_id) + sorted(folders - set(by_id), key=_natural)
    return {
        "title": str(raw.get("title") or episode),
        "synopsis": str(raw.get("synopsis", "")),
        "aspect_ratio": raw.get("aspect_ratio") if raw.get("aspect_ratio") in ASPECT_RATIOS else "landscape",
        "final_provider": raw.get("final_provider") if raw.get("final_provider") in FINAL_PROVIDERS else DEFAULT_FINAL_PROVIDER,
        "scenes": [_clean_scene(by_id.get(scene_id, {}), scene_id, directory / scene_id) for scene_id in order],
    }


def read_script(world: str, episode: str) -> Script:
    path = existing_dir(episode_dir(world, episode), "episode") / SCRIPT_FILE
    raw = json.loads(path.read_text()) if path.is_file() else {}
    return _normalise(world, episode, raw)


def save_script(world: str, episode: str, raw: Dict) -> Script:
    """Save a script. A shot or setting the client left out keeps what is on disk, so a page that only edits text never drops an image."""
    with _lock:
        current = read_script(world, episode)
        frames = {
            (scene["id"], shot["id"]): {"image": shot["image"], "final": shot["final"]}
            for scene in current["scenes"] for shot in scene["shots"]
        }
        raw = {
            "aspect_ratio": current["aspect_ratio"],
            "final_provider": current["final_provider"],
            **raw,
            "scenes": [
                {**scene, "shots": [
                    {**frames.get((scene.get("id"), slugify(str(shot.get("id", "")))), {}), **shot}
                    for shot in scene.get("shots", [])
                ]}
                for scene in raw.get("scenes", current["scenes"])
            ],
        }
        script = _normalise(world, episode, raw)
        write_json(episode_dir(world, episode) / SCRIPT_FILE, script)
        return script


def with_images(world: str, episode: str, script: Script) -> Script:
    """Give each shot the data-relative ``path`` of its image and ``final_path`` of its final, ``None`` if missing."""
    for scene in script["scenes"]:
        folder = scene_dir(world, episode, scene["id"])
        for shot in scene["shots"]:
            for field, key in (("image", "path"), ("final", "final_path")):
                path = folder / shot[field] if shot[field] else None
                shot[key] = relative(path) if path and path.is_file() else None
    return script


def set_shot_image(world: str, episode: str, scene: str, shot: str, image: Path, field: str = "image",
                   final_provider: Optional[str] = None) -> Script:
    """Point a shot's ``image`` (or ``final``) at a new file, and set the episode's ``final_provider`` if given.

    The previous file stays in the scene folder.
    """
    with _lock:
        script = read_script(world, episode)
        for scene_data in script["scenes"]:
            for shot_data in scene_data["shots"]:
                if scene_data["id"] == scene and shot_data["id"] == shot:
                    shot_data[field] = image.name
        if final_provider:
            script["final_provider"] = final_provider
        return save_script(world, episode, script)


def _new_dir(parent: Path, name: str, what: str) -> Path:
    directory = new_child_dir(parent, name, what)
    directory.mkdir(parents=True)
    return directory


def create_episode(world: str, title: str, synopsis: str = "", aspect_ratio: str = "landscape") -> str:
    """A new, empty episode named after its title."""
    directory = _new_dir(episodes_dir(world), title, "episode")
    save_script(world, directory.name, {"title": title.strip(), "synopsis": synopsis.strip(), "aspect_ratio": aspect_ratio})
    return directory.name


def delete_episode(world: str, episode: str) -> None:
    """Hide an episode with all its scenes and shots: its folder moves into ``episodes/.deleted/``."""
    move_to_deleted(existing_dir(episode_dir(world, episode), "episode"))


def create_scene(world: str, episode: str, name: str) -> str:
    script = read_script(world, episode)
    directory = _new_dir(episode_dir(world, episode), name, "scene")
    script["scenes"].append({"id": directory.name})
    save_script(world, episode, script)
    return directory.name


def delete_scene(world: str, episode: str, scene: str) -> None:
    """Hide a scene with all its shots: its folder moves into the episode's ``.deleted/``."""
    move_to_deleted(existing_dir(scene_dir(world, episode, scene), "scene"))
    save_script(world, episode, read_script(world, episode))


def rename_references(world: str, folder: str, old: str, new: str) -> None:
    """Point every scene reference to asset ``old`` (``old`` and ``old:variation``) in one ``folder`` at ``new``."""
    for episode in list_episodes(world):
        script = read_script(world, episode)
        changed = False
        for scene in script["scenes"]:
            renamed = [new + ref[len(old):] if ref == old or ref.startswith(f"{old}:") else ref for ref in scene[folder]]
            changed |= renamed != scene[folder]
            scene[folder] = renamed
        if changed:
            save_script(world, episode, script)


def _action(shot: Dict) -> str:
    return f"{shot['type']}: {shot['action']}" if shot["type"] else shot["action"]


def shot_description(scene: Dict, shot: Dict, cast: List[str]) -> str:
    """What a shot's final frame should show, with ``cast`` (one line per character, location or object)."""
    lines = [scene["heading"], scene["summary"], _action(shot)]
    if cast:
        lines.append("In this scene:\n" + "\n".join(f"- {line}" for line in cast))
    return "\n".join(line for line in lines if line.strip())
