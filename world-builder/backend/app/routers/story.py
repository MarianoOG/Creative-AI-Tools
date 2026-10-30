"""Episodes, scenes and storyboard shots of a world. Scripts come back with each shot's frames attached."""

from __future__ import annotations

from typing import Callable, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.assets import story
from app.assets.generation import SHOT_QUALITY, generate_image
from app.assets.prompt_manager import ASSET_DIRS
from app.assets.worlds import list_worlds, read_style, read_world

router = APIRouter(prefix="/worlds/{world}/episodes", tags=["story"])


class Name(BaseModel):
    name: str


def _call(fn: Callable, *args):
    try:
        return fn(*args)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _check_world(world: str) -> None:
    if world not in list_worlds():
        raise HTTPException(404, f"no world called {world!r}")


@router.get("")
def get_episodes(world: str) -> Dict:
    """Every episode of the world with its title and size."""
    _check_world(world)
    episodes: List[Dict] = []
    for name in story.list_episodes(world):
        script = story.read_script(world, name)
        episodes.append({
            "name": name,
            "title": script["title"],
            "synopsis": script["synopsis"],
            "scene_count": len(script["scenes"]),
            "shot_count": sum(len(scene["shots"]) for scene in script["scenes"]),
        })
    return {"episodes": episodes}


@router.post("", status_code=201)
def post_episode(world: str, body: Name) -> Dict:
    _check_world(world)
    return {"name": _call(story.create_episode, world, body.name)}


@router.delete("/{episode}", status_code=204)
def remove_episode(world: str, episode: str) -> None:
    """Deletes every scene and shot in the episode."""
    _check_world(world)
    _call(story.delete_episode, world, episode)


@router.get("/{episode}")
def get_script(world: str, episode: str) -> Dict:
    _check_world(world)
    return story.with_images(world, episode, _call(story.read_script, world, episode))


@router.put("/{episode}")
def put_script(world: str, episode: str, script: Dict) -> Dict:
    """Save the script. Scenes are matched to their folders by ``id``; it never creates or deletes one."""
    _check_world(world)
    _call(story.read_script, world, episode)  # 400 if the episode does not exist
    return story.with_images(world, episode, _call(story.save_script, world, episode, script))


@router.post("/{episode}/scenes", status_code=201)
def post_scene(world: str, episode: str, body: Name) -> Dict:
    _check_world(world)
    return {"name": _call(story.create_scene, world, episode, body.name)}


@router.delete("/{episode}/scenes/{scene}", status_code=204)
def remove_scene(world: str, episode: str, scene: str) -> None:
    """Deletes every shot in the scene."""
    _check_world(world)
    _call(story.delete_scene, world, episode, scene)




def _cast_line(assets: Dict[str, Dict], reference: str, asset_type: str) -> str:
    """One line of a shot's cast: the asset's name and description, and the variation's change if one is named."""
    name, _, variation = reference.partition(":")
    asset = assets.get(name, {})
    parts = [asset.get("description", "").strip()]
    change = next((v["description"] for v in asset.get("variations", []) if v["name"] == variation), "")
    if change.strip():
        parts.append(f"{variation}: {change.strip()}")
    details = ". ".join(part for part in parts if part)
    label = f"{name.replace('_', ' ')} ({asset_type})"
    return f"{label}: {details}" if details else label


@router.post("/{episode}/scenes/{scene}/shots/{shot}/generate")
def generate_shot(world: str, episode: str, scene: str, shot: str) -> Dict:
    """Render a shot's one image, replacing the one it had (whose file stays on disk).

    Uses the episode's provider and aspect ratio and the world's style, always as
    a low detailed view at low quality and low resolution. No images are sent:
    the characters, locations and objects the scene lists go in as their
    descriptions.
    """
    _check_world(world)
    script = _call(story.read_script, world, episode)
    scene_data = next((s for s in script["scenes"] if s["id"] == scene), None)
    if scene_data is None:
        raise HTTPException(404, f"no scene called {scene!r}")
    shot_data = next((s for s in scene_data["shots"] if s["id"] == shot), None)
    if shot_data is None:
        raise HTTPException(404, f"no shot called {shot!r} - save the storyboard first")

    world_data = read_world(world)
    cast = []
    for asset_type, folder in ASSET_DIRS.items():
        assets = {asset["name"]: asset for asset in world_data[folder]}
        cast += [_cast_line(assets, reference, asset_type) for reference in scene_data[folder]]

    description = story.shot_description(scene_data, shot_data, cast)
    if not description.strip():
        raise HTTPException(422, "Describe the shot (or the scene) before generating it.")
    style = read_style(world)
    if not style:
        raise HTTPException(422, "This world has no style yet - write one in the sidebar.")

    try:
        path = generate_image(
            "shot",
            shot,
            description,
            style,
            story.scene_dir(world, episode, scene),
            provider=script["provider"],
            aspect_ratio=script["aspect_ratio"],
            quality=SHOT_QUALITY,
        )
    except Exception as exc:  # any provider failure: the client gets the reason
        raise HTTPException(502, f"{script['provider']}: {exc}") from exc
    return story.with_images(world, episode, story.set_shot_image(world, episode, scene, shot, path))
