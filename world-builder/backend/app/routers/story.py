"""Episodes, scenes and storyboard shots of a world. Scripts come back with each shot's frames attached."""

from __future__ import annotations

from typing import Callable, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.assets import story
from app.assets.generation import generate_asset
from app.assets.library import newest_by_name
from app.assets.prompt_manager import ASSET_DIRS
from app.assets.worlds import list_worlds, read_style
from app.routers.assets import check_render_options, save_renders

router = APIRouter(prefix="/worlds/{world}/episodes", tags=["story"])


class Name(BaseModel):
    name: str


class RenderOptions(BaseModel):
    aspect_ratio: str = "landscape"
    quality: str = "low"
    provider: str = "both"


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
    return story.with_frames(world, episode, _call(story.read_script, world, episode))


@router.put("/{episode}")
def put_script(world: str, episode: str, script: Dict) -> Dict:
    """Save the script. Scenes are matched to their folders by ``id``; it never creates or deletes one."""
    _check_world(world)
    _call(story.read_script, world, episode)  # 400 if the episode does not exist
    return story.with_frames(world, episode, _call(story.save_script, world, episode, script))


@router.post("/{episode}/scenes", status_code=201)
def post_scene(world: str, episode: str, body: Name) -> Dict:
    _check_world(world)
    return {"name": _call(story.create_scene, world, episode, body.name)}


@router.delete("/{episode}/scenes/{scene}", status_code=204)
def remove_scene(world: str, episode: str, scene: str) -> None:
    """Deletes every shot in the scene."""
    _check_world(world)
    _call(story.delete_scene, world, episode, scene)


@router.post("/{episode}/scenes/{scene}/shots/{shot}/generate")
def generate_shot(world: str, episode: str, scene: str, shot: str, options: RenderOptions) -> Dict:
    """Render one shot's frame in the world's style, from the scene's characters, locations and objects."""
    _check_world(world)
    check_render_options(options.aspect_ratio, options.quality, options.provider)
    script = _call(story.read_script, world, episode)
    scene_data = next((s for s in script["scenes"] if s["id"] == scene), None)
    if scene_data is None:
        raise HTTPException(404, f"no scene called {scene!r}")
    shot_data = next((s for s in scene_data["shots"] if s["id"] == shot), None)
    if shot_data is None:
        raise HTTPException(404, f"no shot called {shot!r} - save the storyboard first")

    names, references = [], []
    for asset_type, folder in ASSET_DIRS.items():
        available = newest_by_name(world, asset_type)
        for name in scene_data[folder]:
            if name in available:
                names.append(f"{name} ({asset_type})")
                references.append(available[name])

    description = story.shot_description(scene_data, shot_data, names)
    if not description.strip():
        raise HTTPException(422, "Describe the shot (or the scene) before generating it.")
    style = read_style(world)
    if not style:
        raise HTTPException(422, "This world has no style yet - write one in style.txt (sidebar).")

    results = generate_asset(
        "shot",
        shot,
        description,
        style,
        story.scene_dir(world, episode, scene),
        references=references,
        aspect_ratio=options.aspect_ratio,
        quality=options.quality,
        provider=options.provider,
    )
    return save_renders(results, "shot", world)
