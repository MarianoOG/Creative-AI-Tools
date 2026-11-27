"""Episodes of a world: their Fountain scripts, saving and syncing them, and rendering their shots."""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.assets import library, story, video
from app.assets.generation import ASPECT_RATIOS, FINAL_PROVIDERS, FINAL_QUALITY, FINAL_RESOLUTION, generate_image
from app.assets.prompt_manager import ASSET_DIRS
from app.assets.worlds import read_style, read_world
from app.routers.common import call, check_world, provider_errors

router = APIRouter(prefix="/worlds/{world}/episodes", tags=["story"])


class NewEpisode(BaseModel):
    title: str
    synopsis: str = ""
    aspect_ratio: str = "landscape"


class ScriptText(BaseModel):
    #: The script as the editor shows it (the app's notes, if any, are ignored).
    text: str


class Settings(BaseModel):
    aspect_ratio: Optional[str] = None
    final_provider: Optional[str] = None


class ShotEdit(BaseModel):
    duration: Optional[int] = None
    end_on_next: Optional[bool] = None
    characters: Optional[List[str]] = None
    objects: Optional[List[str]] = None


class SceneEdit(BaseModel):
    locations: List[str]


class Version(BaseModel):
    version: str


class FinalFrame(BaseModel):
    #: The final frame's model (``openai``, ``gemini`` or ``runware``); the episode's last one when left out.
    provider: Optional[str] = None


@router.get("")
def get_episodes(world: str) -> Dict:
    """Every episode of the world with its title and size."""
    check_world(world)
    return {"episodes": call(story.list_summaries, world)}


@router.post("", status_code=201)
def post_episode(world: str, body: NewEpisode) -> Dict:
    """A new episode: a title, a synopsis and an aspect ratio, and a sample scene to write over."""
    check_world(world)
    if not body.title.strip():
        raise HTTPException(422, "Give the episode a title.")
    if body.aspect_ratio not in ASPECT_RATIOS:
        raise HTTPException(422, f"aspect_ratio must be one of {list(ASPECT_RATIOS)}")
    return {"name": call(story.create_episode, world, body.title, body.synopsis, body.aspect_ratio)}


@router.delete("/{episode}", status_code=204)
def remove_episode(world: str, episode: str) -> None:
    """Hides the episode with every file in it."""
    check_world(world)
    call(story.delete_episode, world, episode)


@router.get("/{episode}")
def get_episode(world: str, episode: str) -> Dict:
    """The episode: its text (without the app's notes), scenes and shots with their tags and files, lint and problems."""
    check_world(world)
    return call(story.read_episode, world, episode)


@router.post("/{episode}/preview")
def preview(world: str, episode: str, body: ScriptText) -> Dict:
    """What saving ``text`` would change, its lint and its screenplay preview. Nothing is written; no AI."""
    check_world(world)
    return call(story.preview, world, episode, body.text)


@router.put("/{episode}/text")
def put_text(world: str, episode: str, body: ScriptText) -> Dict:
    """Save the edited script. Ids carry over to the scenes and shots they match; new and changed ones are tagged and
    checked by the text model. The previous file is kept as a version."""
    check_world(world)
    return call(story.save_text, world, episode, body.text)


@router.get("/{episode}/reprocess")
def reprocess_preview(world: str, episode: str) -> Dict:
    """What Reprocess would fill in."""
    check_world(world)
    return call(story.reprocess_preview, world, episode)


@router.post("/{episode}/reprocess")
def reprocess(world: str, episode: str) -> Dict:
    """Read the file as it is on disk and fill in missing ids, tags and checklists."""
    check_world(world)
    return call(story.reprocess, world, episode)


@router.patch("/{episode}")
def patch_settings(world: str, episode: str, body: Settings) -> Dict:
    check_world(world)
    return call(story.set_settings, world, episode, body.aspect_ratio, body.final_provider)


@router.patch("/{episode}/shots/{shot}")
def patch_shot(world: str, episode: str, shot: str, body: ShotEdit) -> Dict:
    """A shot's clip length, tags (set by hand from then on) or "end on the next shot's frame"."""
    check_world(world)
    return call(story.set_shot, world, episode, shot, duration=body.duration, end_on_next=body.end_on_next,
                characters=body.characters, objects=body.objects)


@router.patch("/{episode}/scenes/{scene}")
def patch_scene(world: str, episode: str, scene: str, body: SceneEdit) -> Dict:
    """A scene's locations, set by hand from then on."""
    check_world(world)
    return call(story.set_scene, world, episode, scene, body.locations)


@router.get("/{episode}/versions")
def get_versions(world: str, episode: str) -> Dict:
    check_world(world)
    return {"versions": call(story.list_versions, world, episode)}


@router.get("/{episode}/versions/{version}")
def get_version(world: str, episode: str, version: str) -> Dict:
    check_world(world)
    return {"text": call(story.read_version, world, episode, version)}


@router.post("/{episode}/versions/restore")
def restore_version(world: str, episode: str, body: Version) -> Dict:
    """Make a kept version the script again (the current one is kept as a version first)."""
    check_world(world)
    return call(story.restore_version, world, episode, body.version)


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


def _cast(world: str, scene: Dict, shot: Dict) -> List[str]:
    """One line per character, location and object tagged on the shot (locations on its scene), in that order."""
    world_data = read_world(world)
    tagged = story.references(scene, shot)
    cast = []
    for asset_type, folder in ASSET_DIRS.items():
        assets = {asset["name"]: asset for asset in world_data[folder]}
        cast += [_cast_line(assets, reference, asset_type) for reference in tagged[folder]]
    return cast


def _final_references(world: str, scene: Dict, shot: Dict) -> tuple[List, List[str]]:
    """A final frame's references: the design of each asset tagged on the shot, with one label per image."""
    paths, labels = [], []
    tagged = story.references(scene, shot)
    for asset_type, folder in ASSET_DIRS.items():
        designs = library.reference_paths(world, asset_type)
        for reference in tagged[folder]:
            if reference in designs and designs[reference] not in paths:
                paths.append(designs[reference])
                labels.append(f"{reference.replace(':', ' ').replace('_', ' ')} ({asset_type} design)")
    return paths, labels


def _shot(world: str, episode: str, shot: str) -> tuple[Dict, Dict, Dict, Optional[Dict]]:
    view = call(story.read_episode, world, episode)
    try:
        scene_data, shot_data, following = story.find_shot(view, shot)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return view, scene_data, shot_data, following


@router.post("/{episode}/shots/{shot}/generate")
def generate_shot(world: str, episode: str, shot: str, body: Optional[FinalFrame] = None) -> Dict:
    """Render a shot's final frame, replacing the one it had (whose file stays on disk).

    It uses OpenAI (medium quality), Gemini or Runware (Flux 2 Klein) at 1K, the size of the video, in the episode's
    aspect ratio and the world's style. It is sent the design of every character and object tagged on the
    shot and every location tagged on its scene, their descriptions, and the scene's heading and summary and
    the shot's action (not its dialogue).
    """
    body = body or FinalFrame()
    check_world(world)
    view, scene_data, shot_data, _ = _shot(world, episode, shot)
    description = story.shot_description(scene_data, shot_data, _cast(world, scene_data, shot_data))
    if not description.strip():
        raise HTTPException(422, "Describe the shot (or the scene) before generating it.")
    style = read_style(world)
    if not style:
        raise HTTPException(422, "This world has no style yet - write one in Manage worlds.")
    provider = body.provider or view["final_provider"]
    if provider not in FINAL_PROVIDERS:
        raise HTTPException(422, f"a final frame's provider must be one of {list(FINAL_PROVIDERS)}")
    references, labels = _final_references(world, scene_data, shot_data)
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
            story.shots_dir(world, episode),
            provider=provider,
            references=references,
            clause="final",
            aspect_ratio=view["aspect_ratio"],
            quality=FINAL_QUALITY,
            resolution=FINAL_RESOLUTION,
        )
    return story.set_shot_file(world, episode, shot, "final", path, provider)


@router.post("/{episode}/shots/{shot}/video")
def generate_shot_video(world: str, episode: str, shot: str) -> Dict:
    """Render a shot's video from its final frame, replacing the one it had (whose file stays on disk).

    It uses Runware's MiniMax H3 Fast at 768p for the shot's clip length, starting from the shot's final frame and
    prompted with the shot's text (the scene's heading and summary, the shot's action and its tagged cast) and the
    world's style. The camera moves only as the action says. No dialogue or voices.
    """
    check_world(world)
    _, scene_data, shot_data, following = _shot(world, episode, shot)
    if not shot_data["final_path"]:
        raise HTTPException(422, "This shot has no final frame yet - generate it on the Storyboard first.")
    description = story.shot_description(scene_data, shot_data, _cast(world, scene_data, shot_data))
    style = read_style(world)
    if not style:
        raise HTTPException(422, "This world has no style yet - write one in Manage worlds.")
    directory = story.episode_dir(world, episode)
    end_frame = None
    if shot_data["end_on_next"] and following and following["final_path"]:
        end_frame = directory / following["final"]
    with provider_errors("runware"):
        path = video.generate_video(
            world, f"{shot}-video", description, style, directory / shot_data["final"], story.shots_dir(world, episode),
            duration=shot_data["duration"], end_frame=end_frame,
        )
    return story.set_shot_file(world, episode, shot, "video", path)
