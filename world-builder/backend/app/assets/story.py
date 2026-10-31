"""Episodes, scenes and shots. The folders are the story structure; ``script.json`` holds the words.

    <world>/episodes/<episode>/script.json
    <world>/episodes/<episode>/<scene>/<shot images>

Folders decide which episodes and scenes exist; ``script.json`` decides their
order and content. A scene folder missing from the script is read as an empty
scene, and a script entry without a folder is dropped. Each shot has one image,
the file in its scene folder that ``image`` names; regenerating points it at a
new file and leaves the old one on disk. The episode's ``provider`` and
``aspect_ratio`` are used for every shot in it.

A shot can also have a ``final``: its high-fidelity frame, the finished image
the storyboard frame plans, saved in the same scene folder as
``{uuid8}-{shot}-final``. ``final_provider`` is the model the last high-fidelity
pass of the episode used (OpenAI or Gemini).

script.json::

    {
      "title": "...", "synopsis": "...", "provider": "runware", "aspect_ratio": "landscape", "final_provider": "gemini",
      "scenes": [{
        "id": "scene1", "heading": "INT. KITCHEN - DAY", "summary": "...",
        "characters": ["fox", "fox:older"], "locations": ["kitchen"], "objects": ["lantern"],
        "shots": [{"id": "shot_1", "action": "...", "image": "1a2b3c4d-shot_1.png", "final": "5e6f7a8b-shot_1-final.jpg"}]
      }]
    }

Scripts from before ``image`` existed get their shot's newest frame on read.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.assets.generation import ASPECT_RATIOS, DEFAULT_FINAL_PROVIDER, DEFAULT_SHOT_PROVIDER, FINAL_PROVIDERS, PROVIDERS
from app.assets.prompt_manager import ASSET_DIRS
from app.assets.worlds import images_in, legacy_name, move_to_deleted, slugify, subfolders, world_dir
from app.settings import relative

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
        "action": str(raw.get("action", "")),
        "image": Path(str(image)).name if image else None,
        "final": Path(str(raw["final"])).name if raw.get("final") else None,
    }


def _clean_scene(raw: Dict, scene_id: str, folder: Path) -> Dict:
    shots, seen = [], set()
    for number, shot in enumerate(raw.get("shots", []), start=1):
        shot = _clean_shot(shot, folder)
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
    folders = set(subfolders(directory))
    by_id = {scene.get("id"): scene for scene in raw.get("scenes", []) if scene.get("id") in folders}
    order = list(by_id) + sorted(folders - set(by_id), key=_natural)
    return {
        "title": str(raw.get("title") or episode),
        "synopsis": str(raw.get("synopsis", "")),
        "provider": raw.get("provider") if raw.get("provider") in PROVIDERS else DEFAULT_SHOT_PROVIDER,
        "aspect_ratio": raw.get("aspect_ratio") if raw.get("aspect_ratio") in ASPECT_RATIOS else "landscape",
        "final_provider": raw.get("final_provider") if raw.get("final_provider") in FINAL_PROVIDERS else DEFAULT_FINAL_PROVIDER,
        "scenes": [_clean_scene(by_id.get(scene_id, {}), scene_id, directory / scene_id) for scene_id in order],
    }


def read_script(world: str, episode: str) -> Script:
    directory = episode_dir(world, episode)
    if not directory.is_dir():
        raise ValueError(f"no episode called {episode!r}")
    path = directory / SCRIPT_FILE
    raw = json.loads(path.read_text()) if path.is_file() else {}
    return _normalise(world, episode, raw)


def save_script(world: str, episode: str, raw: Dict) -> Script:
    """Save a script. A shot or setting the client left out keeps what is on disk, so a page that only edits text never drops an image."""
    current = read_script(world, episode)
    frames = {
        (scene["id"], shot["id"]): {"image": shot["image"], "final": shot["final"]}
        for scene in current["scenes"] for shot in scene["shots"]
    }
    raw = {
        **{key: current[key] for key in ("provider", "aspect_ratio", "final_provider")},
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
    (episode_dir(world, episode) / SCRIPT_FILE).write_text(json.dumps(script, indent=2, ensure_ascii=False) + "\n")
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


def set_shot_image(world: str, episode: str, scene: str, shot: str, image: Path, field: str = "image") -> Script:
    """Point a shot's ``image`` (or ``final``) at a new file. The previous file stays in the scene folder."""
    script = read_script(world, episode)
    for scene_data in script["scenes"]:
        for shot_data in scene_data["shots"]:
            if scene_data["id"] == scene and shot_data["id"] == shot:
                shot_data[field] = image.name
    return save_script(world, episode, script)


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
    """Hide an episode with all its scenes and shots: its folder moves into ``episodes/.deleted/``."""
    directory = episode_dir(world, episode)
    if not directory.is_dir():
        raise ValueError(f"no episode called {episode!r}")
    move_to_deleted(directory)


def create_scene(world: str, episode: str, name: str) -> str:
    script = read_script(world, episode)
    directory = _new_dir(episode_dir(world, episode), name, "scene")
    script["scenes"].append({"id": directory.name})
    save_script(world, episode, script)
    return directory.name


def delete_scene(world: str, episode: str, scene: str) -> None:
    """Hide a scene with all its shots: its folder moves into the episode's ``.deleted/``."""
    directory = scene_dir(world, episode, scene)
    if not directory.is_dir():
        raise ValueError(f"no scene called {scene!r}")
    move_to_deleted(directory)
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


def shot_description(scene: Dict, shot: Dict, cast: List[str]) -> str:
    """What a shot's frame should show, with ``cast`` (one line per character, location or object)."""
    lines = [scene["heading"], scene["summary"], shot["action"]]
    if cast:
        lines.append("In this scene:\n" + "\n".join(f"- {line}" for line in cast))
    return "\n".join(line for line in lines if line.strip())
