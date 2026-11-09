"""Episodes, scenes and storyboard shots of a world. Scripts come back with each shot's frames attached."""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.assets import library, story, video
from app.assets.generation import FINAL_PROVIDERS, FINAL_QUALITY, FINAL_RESOLUTION, generate_image
from app.assets.prompt_manager import ASSET_DIRS
from app.assets.worlds import read_style, read_world
from app.routers.common import call, check_world, provider_errors

router = APIRouter(prefix="/worlds/{world}/episodes", tags=["story"])


class Name(BaseModel):
    name: str


class NewEpisode(BaseModel):
    title: str
    synopsis: str = ""
    aspect_ratio: str = "landscape"


class FinalFrame(BaseModel):
    #: The final frame's model (``openai``, ``gemini`` or ``runware``); the episode's last one when left out.
    provider: Optional[str] = None


@router.get("")
def get_episodes(world: str) -> Dict:
    """Every episode of the world with its title and size."""
    check_world(world)
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
def post_episode(world: str, body: NewEpisode) -> Dict:
    """A new episode: a title, a synopsis and an aspect ratio, with no scenes yet. Its name comes from the title."""
    check_world(world)
    if not body.title.strip():
        raise HTTPException(422, "Give the episode a title.")
    return {"name": call(story.create_episode, world, body.title, body.synopsis, body.aspect_ratio)}


@router.delete("/{episode}", status_code=204)
def remove_episode(world: str, episode: str) -> None:
    """Deletes every scene and shot in the episode."""
    check_world(world)
    call(story.delete_episode, world, episode)


@router.get("/{episode}")
def get_script(world: str, episode: str) -> Dict:
    check_world(world)
    return story.with_images(world, episode, call(story.read_script, world, episode))


@router.put("/{episode}")
def put_script(world: str, episode: str, script: Dict) -> Dict:
    """Save the script. Scenes are matched to their folders by ``id``; it never creates or deletes one."""
    check_world(world)
    call(story.read_script, world, episode)  # 400 if the episode does not exist
    return story.with_images(world, episode, call(story.save_script, world, episode, script))


@router.post("/{episode}/scenes", status_code=201)
def post_scene(world: str, episode: str, body: Name) -> Dict:
    check_world(world)
    return {"name": call(story.create_scene, world, episode, body.name)}


@router.delete("/{episode}/scenes/{scene}", status_code=204)
def remove_scene(world: str, episode: str, scene: str) -> None:
    """Deletes every shot in the scene."""
    check_world(world)
    call(story.delete_scene, world, episode, scene)


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


def _cast(world: str, scene: Dict) -> List[str]:
    """One line per character, location and object the scene lists, in that order."""
    world_data = read_world(world)
    cast = []
    for asset_type, folder in ASSET_DIRS.items():
        assets = {asset["name"]: asset for asset in world_data[folder]}
        cast += [_cast_line(assets, reference, asset_type) for reference in scene[folder]]
    return cast


def _final_references(world: str, scene: Dict) -> tuple[List, List[str]]:
    """A final frame's references: each design the scene lists, with one label per image."""
    paths, labels = [], []
    for asset_type, folder in ASSET_DIRS.items():
        designs = library.reference_paths(world, asset_type)
        for reference in scene[folder]:
            if reference in designs and designs[reference] not in paths:
                paths.append(designs[reference])
                labels.append(f"{reference.replace(':', ' ').replace('_', ' ')} ({asset_type} design)")
    return paths, labels


def _find_shot(script: Dict, scene: str, shot: str) -> tuple[Dict, Dict]:
    scene_data = next((s for s in script["scenes"] if s["id"] == scene), None)
    if scene_data is None:
        raise HTTPException(404, f"no scene called {scene!r}")
    shot_data = next((s for s in scene_data["shots"] if s["id"] == shot), None)
    if shot_data is None:
        raise HTTPException(404, f"no shot called {shot!r} - save the script first")
    return scene_data, shot_data


@router.post("/{episode}/scenes/{scene}/shots/{shot}/generate")
def generate_shot(world: str, episode: str, scene: str, shot: str, body: Optional[FinalFrame] = None) -> Dict:
    """Render a shot's final frame, replacing the one it had (whose file stays on disk).

    It uses OpenAI (medium quality), Gemini or Runware (Flux 2 Klein) at 1K, the size of the video, in the episode's
    aspect ratio and the world's style. It is sent the image of every
    character, location and object the scene lists, as well as their
    descriptions and the shot's text.
    """
    body = body or FinalFrame()
    check_world(world)
    script = call(story.read_script, world, episode)
    scene_data, shot_data = _find_shot(script, scene, shot)

    description = story.shot_description(scene_data, shot_data, _cast(world, scene_data))
    if not description.strip():
        raise HTTPException(422, "Describe the shot (or the scene) before generating it.")
    style = read_style(world)
    if not style:
        raise HTTPException(422, "This world has no style yet - write one in Manage worlds.")
    provider = body.provider or script["final_provider"]
    if provider not in FINAL_PROVIDERS:
        raise HTTPException(422, f"a final frame's provider must be one of {list(FINAL_PROVIDERS)}")
    references, labels = _final_references(world, scene_data)
    if labels:
        description += "\n\nReference images, in order:\n" + "\n".join(
            f"{number}. {label}" for number, label in enumerate(labels, start=1)
        )

    with provider_errors(provider):
        path = generate_image(
            world,
            "final",
            f"{shot}-final",
            description,
            style,
            story.scene_dir(world, episode, scene),
            provider=provider,
            references=references,
            clause="final",
            aspect_ratio=script["aspect_ratio"],
            quality=FINAL_QUALITY,
            resolution=FINAL_RESOLUTION,
        )
    return story.with_images(world, episode, story.set_shot_image(world, episode, scene, shot, path, "final", provider))


@router.post("/{episode}/scenes/{scene}/shots/{shot}/video")
def generate_shot_video(world: str, episode: str, scene: str, shot: str) -> Dict:
    """Render a shot's video from its final frame, replacing the one it had (whose file stays on disk).

    It uses Runware's MiniMax H3 Fast at 768p for the shot's ``duration``, starting
    from the shot's final frame and prompted with the shot's text (the scene's
    heading, summary and cast, and the shot's type and action), its ``camera``
    move and the world's style. No dialogue or voices.
    """
    check_world(world)
    script = story.with_images(world, episode, call(story.read_script, world, episode))
    scene_data, shot_data = _find_shot(script, scene, shot)
    if not shot_data["final_path"]:
        raise HTTPException(422, "This shot has no final frame yet - generate it on the Storyboard first.")
    description = story.shot_description(scene_data, shot_data, _cast(world, scene_data))
    if not description.strip():
        raise HTTPException(422, "Describe the shot (or the scene) before generating its video.")
    style = read_style(world)
    if not style:
        raise HTTPException(422, "This world has no style yet - write one in Manage worlds.")

    folder = story.scene_dir(world, episode, scene)
    end_frame = None
    if shot_data["end_on_next"]:
        # The next shot in story order (the last shot has none), if it has a final frame.
        ordered = [(s, sh) for s in script["scenes"] for sh in s["shots"]]
        position = next(i for i, (s, sh) in enumerate(ordered) if sh is shot_data)
        if position + 1 < len(ordered):
            next_scene, next_shot = ordered[position + 1]
            if next_shot["final"] and next_shot["final_path"]:
                end_frame = story.scene_dir(world, episode, next_scene["id"]) / next_shot["final"]
    with provider_errors("runware"):
        path = video.generate_video(
            world, f"{shot}-video", description, style, folder / shot_data["final"], folder,
            duration=shot_data["duration"], camera=shot_data["camera"], end_frame=end_frame,
        )
    return story.with_images(world, episode, story.set_shot_image(world, episode, scene, shot, path, "video"))
