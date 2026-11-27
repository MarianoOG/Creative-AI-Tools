"""Episodes: a Fountain script each, plus what was generated for its shots.

    <world>/episodes/<episode>/script.fountain    the story: the source of truth for every word and the order
    <world>/episodes/<episode>/episode.json       settings and each shot's generated files, by shot id
    <world>/episodes/<episode>/shots/             the shots' frames and videos
    <world>/episodes/<episode>/.versions/         the script before each save, reprocess or restore

**script.fountain** holds everything about the story (see :mod:`fountain`): the
title page, scenes, each shot's action and dialogue, and, in the app's hidden
notes, each scene's and shot's id, its tags (locations; characters and
objects) and each shot's clip length. Nothing in ``episode.json`` repeats it.

**episode.json** holds what cannot be written in a screenplay::

    {"aspect_ratio": "landscape", "final_provider": "nano-banana",
     "shots": {"a3f9c2": {"final": "shots/1a2b3c4d-a3f9c2-final.jpg", "final_hash": "...",
                          "video": "shots/9a8b7c6d-a3f9c2-video.mp4", "video_hash": "...", "video_final": "shots/1a2b...jpg",
                          "end_on_next": false, "tags_manual": false, "check": {"hash": "...", "missing": [...]}}},
     "scenes": {"k7q2d8": {"tags_manual": false}}}

A shot's entry stays when the shot leaves the script, so restoring an older
version links its frames again. ``final_hash`` is the shot's
:func:`fingerprint` when its frame was made, so a frame whose shot changed
since is flagged stale; ``video_hash`` and ``video_final`` do the same for a video.

Saving edited text (:func:`save_text`) carries the ids over from the saved
script (:mod:`sync`), tags new and changed shots and checks them against the
checklist (:mod:`tagging`), and keeps the previous file in ``.versions/``.
Episodes from before Fountain (a ``script.json``) are converted on first read,
keeping every frame and video; the ``script.json`` stays on disk.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.assets import fountain, sync, tagging
from app.assets.generation import ASPECT_RATIOS, DEFAULT_FINAL_PROVIDER, FINAL_PROVIDERS
from app.assets.video import DEFAULT_DURATION, DURATIONS
from app.assets.worlds import (
    child_dir, existing_dir, move_to_deleted, new_child_dir, read_world, subfolders, world_dir, write_json,
)
from app.settings import relative

SCRIPT_FILE = "script.fountain"
EPISODE_FILE = "episode.json"
LEGACY_SCRIPT_FILE = "script.json"
SHOTS_DIR = "shots"
VERSIONS_DIR = ".versions"

#: Note key -> the world folder its names refer to.
TAG_FOLDERS = {"loc": "locations", "chars": "characters", "objs": "objects"}

#: A new episode starts with this, so the syntax is in front of the writer. Placeholders only: no story.
TEMPLATE_BODY = """INT. PLACE - TIME OF DAY

= One line on what this scene is about.

Describe the first shot: what we see, who is in it and what they do.

CHARACTER NAME
(how they say it)
What they say.

Describe the next shot.
"""

#: Held across each read-change-write of an episode, so parallel renders never drop each other's files.
_lock = threading.RLock()


# --- folders and files ----------------------------------------------------------

def episodes_dir(world: str) -> Path:
    return world_dir(world) / "episodes"


def episode_dir(world: str, episode: str) -> Path:
    return child_dir(episodes_dir(world), episode, "episode")


def shots_dir(world: str, episode: str) -> Path:
    return episode_dir(world, episode) / SHOTS_DIR


def list_episodes(world: str) -> List[str]:
    return sorted(subfolders(episodes_dir(world)), key=_natural)


def _natural(name: str) -> list:
    import re
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def _new_id(taken: set) -> str:
    while True:
        candidate = secrets.token_hex(3)
        if candidate not in taken:
            taken.add(candidate)
            return candidate


def _clean_meta(raw: Dict) -> Dict:
    final_provider = raw.get("final_provider")
    return {
        "aspect_ratio": raw.get("aspect_ratio") if raw.get("aspect_ratio") in ASPECT_RATIOS else "landscape",
        "final_provider": final_provider if final_provider in FINAL_PROVIDERS else DEFAULT_FINAL_PROVIDER,
        "shots": {str(key): value for key, value in (raw.get("shots") or {}).items() if isinstance(value, dict)},
        "scenes": {str(key): value for key, value in (raw.get("scenes") or {}).items() if isinstance(value, dict)},
    }


def _read(world: str, episode: str) -> tuple[str, Dict]:
    """The script's text (with the app's notes) and ``episode.json``, converting an older episode first."""
    directory = existing_dir(episode_dir(world, episode), "episode")
    script = directory / SCRIPT_FILE
    if not script.is_file():
        _migrate(directory)
    meta_path = directory / EPISODE_FILE
    meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
    return script.read_text(), _clean_meta(meta)


def _write_meta(world: str, episode: str, meta: Dict) -> None:
    write_json(episode_dir(world, episode) / EPISODE_FILE, _clean_meta(meta))


def _write_text(world: str, episode: str, text: str, keep_version: bool = True) -> None:
    """Write the script, keeping the one it replaces in ``.versions/`` (if it changed)."""
    directory = episode_dir(world, episode)
    path = directory / SCRIPT_FILE
    if keep_version and path.is_file() and path.read_text() != text:
        versions = directory / VERSIONS_DIR
        versions.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(path, versions / f"{stamp}.fountain")
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    temporary.write_text(text)
    temporary.replace(path)


# --- reading -----------------------------------------------------------------

def _int_duration(value: Any) -> Optional[int]:
    try:
        return int(str(value).rstrip("s"))
    except ValueError:
        return None


def fingerprint(scene: Dict, shot: Dict) -> str:
    """What a shot's frame is drawn from: if this changes, the frame is stale. Dialogue is not drawn, so it is left out."""
    data = [scene["heading"], scene["summary"], scene["locations"], shot["action"], shot["characters"], shot["objects"]]
    return hashlib.sha1(json.dumps(data).encode()).hexdigest()[:16]


def video_fingerprint(scene: Dict, shot: Dict) -> str:
    return hashlib.sha1(f"{fingerprint(scene, shot)}:{shot['duration']}".encode()).hexdigest()[:16]


def _text_hash(shot: Dict) -> str:
    return hashlib.sha1(fountain.shot_text(shot).encode()).hexdigest()[:16]


def _file(world: str, episode: str, name: Optional[str]) -> Optional[str]:
    """A shot file's data-relative path, ``None`` if it is not on disk."""
    if not name:
        return None
    path = episode_dir(world, episode) / name
    return relative(path) if path.is_file() else None


def _view(world: str, episode: str, text: str, meta: Dict) -> Dict:
    """The episode as the pages use it: parsed, with ids, tags, files and what is stale or missing."""
    parsed = fountain.parse(text)
    world_data = read_world(world)
    known = {key: {asset["name"] for asset in world_data[folder]} for key, folder in TAG_FOLDERS.items()}
    problems: List[Dict[str, Any]] = []
    seen: set = set()
    scenes = []
    for scene_number, raw_scene in enumerate(parsed["scenes"], start=1):
        note = raw_scene["note"]
        scene_id = note.get("id") if note.get("id") not in seen else None
        seen.add(scene_id)
        scene = {
            "id": scene_id,
            "number": scene_number,
            "heading": raw_scene["heading"],
            "summary": raw_scene["summary"],
            "locations": list(note.get("loc", [])),
            "tagged": "loc" in note,
            "line": raw_scene["line"],
            "shots": [],
        }
        for name in scene["locations"]:
            if name.split(":")[0] not in known["loc"]:
                problems.append({"line": raw_scene["line"], "message": f"Location {name!r} is not in this world."})
        for shot_number, raw_shot in enumerate(raw_scene["shots"], start=1):
            shot_note = raw_shot["note"]
            shot_id = shot_note.get("id") if shot_note.get("id") not in seen else None
            seen.add(shot_id)
            duration = _int_duration(shot_note.get("dur", DEFAULT_DURATION))
            if duration not in DURATIONS:
                problems.append({"line": raw_shot["end"], "message": f"A clip can be {', '.join(map(str, DURATIONS))} "
                                 f"seconds long, not {shot_note.get('dur')!r}: {DEFAULT_DURATION} is used."})
                duration = DEFAULT_DURATION
            files = meta["shots"].get(shot_id, {}) if shot_id else {}
            shot = {
                "id": shot_id,
                "number": shot_number,
                "action": raw_shot["action"],
                "dialogue": raw_shot["dialogue"],
                "characters": list(shot_note.get("chars", [])),
                "objects": list(shot_note.get("objs", [])),
                "tagged": "chars" in shot_note or "objs" in shot_note,
                "tags_manual": bool(files.get("tags_manual")),
                "duration": duration,
                "end_on_next": bool(files.get("end_on_next")),
                "line": raw_shot["start"],
                "final": files.get("final"),
                "video": files.get("video"),
                "final_path": _file(world, episode, files.get("final")),
                "video_path": _file(world, episode, files.get("video")),
            }
            check = files.get("check") or {}
            shot["missing"] = check.get("missing") if check.get("hash") == _text_hash(raw_shot) else None
            shot["final_stale"] = bool(shot["final_path"]) and files.get("final_hash") != fingerprint(scene, shot)
            shot["video_stale"] = bool(shot["video_path"]) and (
                files.get("video_final") != files.get("final") or files.get("video_hash") != video_fingerprint(scene, shot)
            )
            for key, field in (("chars", "characters"), ("objs", "objects")):
                for name in shot[field]:
                    if name.split(":")[0] not in known[key]:
                        problems.append({"line": raw_shot["end"], "message": f"{field[:-1].capitalize()} {name!r} is "
                                         "not in this world."})
            for line in raw_shot["dialogue"]:
                if line["character"] not in known["chars"]:
                    problems.append({"line": raw_shot["end"], "message": f"{line['cue']} speaks but is not a "
                                     "character in this world."})
            scene["shots"].append(shot)
        scenes.append(scene)
    needs_ids = sum(1 for scene in scenes if not scene["id"]) + sum(
        1 for scene in scenes for shot in scene["shots"] if not shot["id"]
    )
    in_script = {shot["id"] for scene in scenes for shot in scene["shots"]}
    unlinked = [
        {"id": shot_id, "final_path": _file(world, episode, files.get("final")),
         "video_path": _file(world, episode, files.get("video"))}
        for shot_id, files in meta["shots"].items()
        if shot_id not in in_script and (files.get("final") or files.get("video"))
    ]
    return {
        "name": episode,
        "title": parsed["title"] or episode,
        "synopsis": parsed["synopsis"],
        "aspect_ratio": meta["aspect_ratio"],
        "final_provider": meta["final_provider"],
        "text": fountain.strip_notes(text),
        "scenes": scenes,
        "lint": parsed["lint"],
        "problems": _dedupe(problems),
        "needs_reprocess": needs_ids + sum(
            1 for scene in scenes for shot in scene["shots"] if not shot["tagged"] or shot["missing"] is None
        ) + sum(1 for scene in scenes if not scene["tagged"]),
        "needs_ids": needs_ids,
        "unlinked": [entry for entry in unlinked if entry["final_path"] or entry["video_path"]],
    }


def _dedupe(problems: List[Dict]) -> List[Dict]:
    seen, result = set(), []
    for problem in problems:
        key = (problem["line"], problem["message"])
        if key not in seen:
            seen.add(key)
            result.append(problem)
    return result


def read_episode(world: str, episode: str) -> Dict:
    text, meta = _read(world, episode)
    return _view(world, episode, text, meta)


def list_summaries(world: str) -> List[Dict]:
    summaries = []
    for name in list_episodes(world):
        view = read_episode(world, name)
        summaries.append({
            "name": name, "title": view["title"], "synopsis": view["synopsis"],
            "scene_count": len(view["scenes"]), "shot_count": sum(len(scene["shots"]) for scene in view["scenes"]),
        })
    return summaries


def find_shot(view: Dict, shot_id: str) -> tuple[Dict, Dict, Optional[Dict]]:
    """The scene a shot is in, the shot, and the next shot in the same scene (``None`` for the last)."""
    for scene in view["scenes"]:
        for position, shot in enumerate(scene["shots"]):
            if shot["id"] == shot_id:
                following = scene["shots"][position + 1] if position + 1 < len(scene["shots"]) else None
                return scene, shot, following
    raise ValueError(f"no shot {shot_id!r} in this episode - save or reprocess the script first")


# --- saving text -----------------------------------------------------------------

def preview(world: str, episode: str, text: str) -> Dict:
    """What saving ``text`` would change (no AI, nothing written), its lint and its preview elements."""
    current, meta = _read(world, episode)
    old, new = fountain.parse(current), fountain.parse(fountain.strip_notes(text))
    summary = sync.match(old, new)["summary"]
    return {"summary": _describe(summary, old, meta), "lint": new["lint"], "elements": new["elements"]}


def _describe(summary: Dict, old: Dict, meta: Dict) -> Dict:
    """The summary, plus how many frames and videos would go stale or be unlinked."""
    def files(pairs: List) -> Dict[str, int]:
        ids = [old["scenes"][s]["shots"][n]["note"].get("id") for s, n in pairs]
        return {
            "frames": sum(1 for shot_id in ids if meta["shots"].get(shot_id, {}).get("final")),
            "videos": sum(1 for shot_id in ids if meta["shots"].get(shot_id, {}).get("video")),
        }
    return {**{key: summary[key] for key in ("scenes", "shots", "changed")},
            "stale": files(summary["modified_shots"]), "unlinked": files(summary["removed_shots"])}


def _tag(world: str, parsed: Dict, scene_notes: List[Dict], shot_notes: List[List[Dict]],
         meta: Dict, scene_jobs: set, shot_jobs: set) -> Optional[str]:
    """Ask the model for the tags and checklist of the scenes and shots in ``scene_jobs``/``shot_jobs`` (by id),
    and write them into the notes and ``meta``. Returns a warning if it failed (the save goes on without them)."""
    check_jobs = {
        note["id"] for scene, notes in zip(parsed["scenes"], shot_notes) for shot, note in zip(scene["shots"], notes)
        if (meta["shots"].get(note["id"], {}).get("check") or {}).get("hash") != _text_hash(shot)
    }
    jobs = shot_jobs | check_jobs
    if not scene_jobs and not jobs:
        return None
    request = []
    for scene, scene_note, notes in zip(parsed["scenes"], scene_notes, shot_notes):
        shots = [
            {"key": note["id"], "action": shot["action"],
             "dialogue": " / ".join(f"{line['cue']}: {line['text']}" for line in shot["dialogue"])}
            for shot, note in zip(scene["shots"], notes) if note["id"] in jobs
        ]
        if shots or scene_note["id"] in scene_jobs:
            request.append({"key": scene_note["id"], "heading": scene["heading"], "summary": scene["summary"],
                            "tag": scene_note["id"] in scene_jobs, "shots": shots})
    try:
        answer = tagging.tag(read_world(world), request)
    except Exception as exc:  # the save must never be lost to a tagging failure
        return f"Tags and checklist were not updated ({exc}). Use Reprocess to try again."
    for scene_note in scene_notes:
        if scene_note["id"] in scene_jobs and scene_note["id"] in answer["scenes"]:
            scene_note["loc"] = answer["scenes"][scene_note["id"]]
    for scene, notes in zip(parsed["scenes"], shot_notes):
        for shot, note in zip(scene["shots"], notes):
            result = answer["shots"].get(note["id"])
            if result is None:
                continue
            if note["id"] in shot_jobs:
                note["chars"], note["objs"] = result["chars"], result["objs"]
            entry = meta["shots"].setdefault(note["id"], {})
            entry["check"] = {"hash": _text_hash(shot), "missing": result["missing"]}
    return None


def save_text(world: str, episode: str, text: str, use_ai: bool = True) -> Dict:
    """Save the editor's ``text``: ids carried over from the saved script, new and changed shots and scenes
    tagged and checked, the previous file kept in ``.versions/``. Returns the episode, the summary and any warning."""
    with _lock:
        current, meta = _read(world, episode)
        old = fountain.parse(current)
        clean = fountain.strip_notes(text)
        new = fountain.parse(clean)
        matched = sync.match(old, new)
        summary = _describe(matched["summary"], old, meta)
        taken = _all_ids(old, meta)
        scene_notes, shot_notes, scene_jobs, shot_jobs = [], [], set(), set()
        used: set = set()
        for number, scene in enumerate(new["scenes"]):
            before = matched["scenes"][number]
            note = dict(old["scenes"][before]["note"]) if before is not None else {}
            if not note.get("id") or note["id"] in used:
                note["id"] = _new_id(taken)
            used.add(note["id"])
            changed = before is None or sync._scene_text(old["scenes"][before]) != sync._scene_text(scene)
            if "loc" not in note or (changed and not meta["scenes"].get(note["id"], {}).get("tags_manual")):
                scene_jobs.add(note["id"])
            scene_notes.append(note)
            notes = []
            for shot_number, shot in enumerate(scene["shots"]):
                pair = matched["shots"][number][shot_number]
                old_shot = old["scenes"][pair[0]]["shots"][pair[1]] if pair else None
                shot_note = dict(old_shot["note"]) if old_shot else {}
                if not shot_note.get("id") or shot_note["id"] in used:
                    shot_note["id"] = _new_id(taken)
                used.add(shot_note["id"])
                untagged = "chars" not in shot_note and "objs" not in shot_note
                edited = old_shot is None or fountain.shot_text(old_shot) != fountain.shot_text(shot)
                if untagged or (edited and not meta["shots"].get(shot_note["id"], {}).get("tags_manual")):
                    shot_jobs.add(shot_note["id"])
                notes.append(shot_note)
            shot_notes.append(notes)
        warning = _tag(world, new, scene_notes, shot_notes, meta, scene_jobs, shot_jobs) if use_ai else None
        _write_text(world, episode, fountain.annotate(clean, scene_notes, shot_notes))
        _write_meta(world, episode, meta)
        return {"episode": read_episode(world, episode), "summary": summary, "warning": warning}


def _all_ids(parsed: Dict, meta: Dict) -> set:
    """Every id in use, so a new one never takes the id (and files) of a shot that left the script."""
    ids = set(meta["shots"]) | set(meta["scenes"])
    for scene in parsed["scenes"]:
        ids.add(scene["note"].get("id"))
        ids |= {shot["note"].get("id") for shot in scene["shots"]}
    return {i for i in ids if i}


def reprocess_preview(world: str, episode: str) -> Dict:
    """What :func:`reprocess` would do, without doing it."""
    view = read_episode(world, episode)
    return {
        "ids": view["needs_ids"],
        "untagged_shots": sum(1 for scene in view["scenes"] for shot in scene["shots"] if not shot["tagged"]),
        "untagged_scenes": sum(1 for scene in view["scenes"] if not scene["tagged"]),
        "unchecked_shots": sum(1 for scene in view["scenes"] for shot in scene["shots"] if shot["missing"] is None),
        "unlinked": len(view["unlinked"]),
    }


def reprocess(world: str, episode: str) -> Dict:
    """Read the file as it is on disk (it may have been edited elsewhere) and fill in what is missing:
    ids, tags and checklists. Nothing already there changes."""
    with _lock:
        text, meta = _read(world, episode)
        parsed = fountain.parse(text)
        taken = _all_ids(parsed, meta)
        used: set = set()
        scene_notes, shot_notes, scene_jobs, shot_jobs = [], [], set(), set()
        for scene in parsed["scenes"]:
            note = dict(scene["note"])
            if not note.get("id") or note["id"] in used:
                note["id"] = _new_id(taken)
            used.add(note["id"])
            if "loc" not in note:
                scene_jobs.add(note["id"])
            scene_notes.append(note)
            notes = []
            for shot in scene["shots"]:
                shot_note = dict(shot["note"])
                if not shot_note.get("id") or shot_note["id"] in used:
                    shot_note["id"] = _new_id(taken)
                used.add(shot_note["id"])
                if "chars" not in shot_note and "objs" not in shot_note:
                    shot_jobs.add(shot_note["id"])
                notes.append(shot_note)
            shot_notes.append(notes)
        warning = _tag(world, parsed, scene_notes, shot_notes, meta, scene_jobs, shot_jobs)
        _write_text(world, episode, fountain.annotate(text, scene_notes, shot_notes))
        _write_meta(world, episode, meta)
        return {"episode": read_episode(world, episode), "warning": warning}


# --- notes and settings from the pages ---------------------------------------------

def _edit_notes(world: str, episode: str, change: Callable[[List[Dict], List[List[Dict]]], None]) -> None:
    """Change the app's notes in the file, and nothing else in it. No version is kept: the words do not change."""
    text, _ = _read(world, episode)
    parsed = fountain.parse(text)
    scene_notes = [dict(scene["note"]) for scene in parsed["scenes"]]
    shot_notes = [[dict(shot["note"]) for shot in scene["shots"]] for scene in parsed["scenes"]]
    change(scene_notes, shot_notes)
    _write_text(world, episode, fountain.annotate(text, scene_notes, shot_notes), keep_version=False)


def set_shot(world: str, episode: str, shot_id: str, *, duration: Optional[int] = None,
             end_on_next: Optional[bool] = None, characters: Optional[List[str]] = None,
             objects: Optional[List[str]] = None) -> Dict:
    """Change a shot's clip length, tags (by hand: the model will not change them again) or "end on the next frame"."""
    if duration is not None and duration not in DURATIONS:
        raise ValueError(f"duration must be one of {list(DURATIONS)} seconds")
    with _lock:
        find_shot(read_episode(world, episode), shot_id)
        if duration is not None or characters is not None or objects is not None:
            def change(_: List[Dict], shot_notes: List[List[Dict]]) -> None:
                for note in (note for notes in shot_notes for note in notes if note.get("id") == shot_id):
                    if duration is not None:
                        note["dur"] = str(duration) if duration != DEFAULT_DURATION else None
                    if characters is not None:
                        note["chars"] = characters
                        note.setdefault("objs", [])
                    if objects is not None:
                        note["objs"] = objects
                        note.setdefault("chars", [])
            _edit_notes(world, episode, change)
        _, meta = _read(world, episode)
        entry = meta["shots"].setdefault(shot_id, {})
        if end_on_next is not None:
            entry["end_on_next"] = end_on_next
        if characters is not None or objects is not None:
            entry["tags_manual"] = True
        _write_meta(world, episode, meta)
        return read_episode(world, episode)


def set_scene(world: str, episode: str, scene_id: str, locations: List[str]) -> Dict:
    """Set a scene's locations by hand (the model will not change them again)."""
    with _lock:
        if not any(scene["id"] == scene_id for scene in read_episode(world, episode)["scenes"]):
            raise ValueError(f"no scene {scene_id!r} in this episode")

        def change(scene_notes: List[Dict], _: List[List[Dict]]) -> None:
            for note in scene_notes:
                if note.get("id") == scene_id:
                    note["loc"] = locations
        _edit_notes(world, episode, change)
        _, meta = _read(world, episode)
        meta["scenes"].setdefault(scene_id, {})["tags_manual"] = True
        _write_meta(world, episode, meta)
        return read_episode(world, episode)


def set_settings(world: str, episode: str, aspect_ratio: Optional[str] = None,
                 final_provider: Optional[str] = None) -> Dict:
    with _lock:
        _, meta = _read(world, episode)
        if aspect_ratio is not None:
            if aspect_ratio not in ASPECT_RATIOS:
                raise ValueError(f"aspect_ratio must be one of {list(ASPECT_RATIOS)}")
            meta["aspect_ratio"] = aspect_ratio
        if final_provider is not None:
            if final_provider not in FINAL_PROVIDERS:
                raise ValueError(f"final_provider must be one of {list(FINAL_PROVIDERS)}")
            meta["final_provider"] = final_provider
        _write_meta(world, episode, meta)
        return read_episode(world, episode)


def set_shot_file(world: str, episode: str, shot_id: str, field: str, path: Path,
                  final_provider: Optional[str] = None) -> Dict:
    """Point a shot's ``final`` or ``video`` at a new file in its episode, with the fingerprint it was made from.
    The previous file stays on disk."""
    with _lock:
        text, meta = _read(world, episode)
        scene, shot, _ = find_shot(_view(world, episode, text, meta), shot_id)
        entry = meta["shots"].setdefault(shot_id, {})
        entry[field] = path.relative_to(episode_dir(world, episode)).as_posix()
        if field == "final":
            entry["final_hash"] = fingerprint(scene, shot)
        else:
            entry["video_hash"] = video_fingerprint(scene, shot)
            entry["video_final"] = entry.get("final")
        if final_provider:
            meta["final_provider"] = final_provider
        _write_meta(world, episode, meta)
        return read_episode(world, episode)


# --- versions ----------------------------------------------------------------------

def list_versions(world: str, episode: str) -> List[Dict]:
    """Every kept version, newest first: ``name`` and when (UTC)."""
    directory = episode_dir(world, episode) / VERSIONS_DIR
    if not directory.is_dir():
        return []
    versions = []
    for path in sorted(directory.glob("*.fountain"), reverse=True):
        stamp = datetime.strptime(path.stem, "%Y%m%d-%H%M%S-%f").replace(tzinfo=timezone.utc)
        versions.append({"name": path.stem, "saved_at": stamp.isoformat(timespec="seconds")})
    return versions


def read_version(world: str, episode: str, version: str) -> str:
    path = episode_dir(world, episode) / VERSIONS_DIR / f"{Path(version).name}.fountain"
    if not path.is_file():
        raise ValueError(f"no version {version!r}")
    return fountain.strip_notes(path.read_text())


def restore_version(world: str, episode: str, version: str) -> Dict:
    """Make an older version the script again. The current one is kept as a version first, so this can be undone."""
    with _lock:
        path = episode_dir(world, episode) / VERSIONS_DIR / f"{Path(version).name}.fountain"
        if not path.is_file():
            raise ValueError(f"no version {version!r}")
        _write_text(world, episode, path.read_text())
        return read_episode(world, episode)


# --- episodes ---------------------------------------------------------------------

def _title_page(title: str, synopsis: str) -> str:
    lines = [f"Title: {' '.join(title.split())}"]
    if synopsis.strip():
        lines.append("Synopsis:")
        lines += [f"    {line.strip()}" for line in synopsis.strip().splitlines() if line.strip()]
    return "\n".join(lines) + "\n\n"


def create_episode(world: str, title: str, synopsis: str = "", aspect_ratio: str = "landscape") -> str:
    """A new episode named after its title, starting from :data:`TEMPLATE_BODY`."""
    directory = new_child_dir(episodes_dir(world), title, "episode")
    directory.mkdir(parents=True)
    (directory / SCRIPT_FILE).write_text(_title_page(title, synopsis) + TEMPLATE_BODY)
    _write_meta(world, directory.name, {"aspect_ratio": aspect_ratio})
    return directory.name


def delete_episode(world: str, episode: str) -> None:
    """Hide an episode with all its files: its folder moves into ``episodes/.deleted/``."""
    move_to_deleted(existing_dir(episode_dir(world, episode), "episode"))


def rename_references(world: str, folder: str, old: str, new: str) -> None:
    """Point every tag naming asset ``old`` (``old`` and ``old:variation``) in one ``folder`` at ``new``."""
    key = next(key for key, name in TAG_FOLDERS.items() if name == folder)

    def rename(note: Dict) -> None:
        if key in note:
            note[key] = [new + ref[len(old):] if ref == old or ref.startswith(f"{old}:") else ref for ref in note[key]]

    for episode in list_episodes(world):
        with _lock:
            def change(scene_notes: List[Dict], shot_notes: List[List[Dict]]) -> None:
                for note in scene_notes + [note for notes in shot_notes for note in notes]:
                    rename(note)
            _edit_notes(world, episode, change)


# --- prompts ---------------------------------------------------------------------

def references(scene: Dict, shot: Dict) -> Dict[str, List[str]]:
    """World folder -> the shot's references in it: its characters and objects, and its scene's locations."""
    return {"characters": shot["characters"], "locations": scene["locations"], "objects": shot["objects"]}


def shot_description(scene: Dict, shot: Dict, cast: List[str]) -> str:
    """What a shot's frame (and video) should show, with ``cast`` (one line per character, location or object)."""
    lines = [scene["heading"], scene["summary"], shot["action"]]
    if cast:
        lines.append("In this shot:\n" + "\n".join(f"- {line}" for line in cast))
    return "\n".join(line for line in lines if line.strip())


# --- episodes from before Fountain ---------------------------------------------------

def _migrate(directory: Path) -> None:
    """Write ``script.fountain`` and ``episode.json`` for an episode that has only a ``script.json`` (or nothing).

    Every scene and shot keeps its words, its references (a scene's characters and
    objects go to each of its shots), its clip length and its frame and video.
    A shot's type and camera move become words in its action. The ``script.json`` stays.
    """
    legacy = directory / LEGACY_SCRIPT_FILE
    raw = json.loads(legacy.read_text()) if legacy.is_file() else {}
    folders = [name for name in subfolders(directory) if name != SHOTS_DIR]
    by_id = {scene.get("id"): scene for scene in raw.get("scenes", []) if scene.get("id") in folders}
    order = list(by_id) + sorted(set(folders) - set(by_id), key=_natural)

    body: List[str] = []
    taken: set = set()
    plan = []  # per scene: (scene note, [(shot note, files)])
    for number, scene_id in enumerate(order, start=1):
        scene = by_id.get(scene_id, {})
        heading = str(scene.get("heading", "")).strip() or f"SCENE {number}"
        body += [fountain.force_heading(heading), ""]
        body += [f"= {line.strip()}" for line in str(scene.get("summary", "")).splitlines() if line.strip()]
        if body[-1] != "":
            body.append("")
        scene_note = {"id": _new_id(taken), "loc": [str(ref) for ref in scene.get("locations", [])]}
        shots = []
        for shot in scene.get("shots", []):
            words = []
            if shot.get("type"):
                words.append(f"{shot['type']}.")
            words.append(str(shot.get("action", "")).strip())
            if shot.get("camera") and shot.get("camera") != "Static":
                words.append(f"Camera: {str(shot['camera']).lower()}.")
            body += [fountain.force_action(" ".join(word for word in words if word)), ""]
            duration = shot.get("duration") if shot.get("duration") in DURATIONS else DEFAULT_DURATION
            shot_note = {
                "id": _new_id(taken),
                "dur": str(duration) if duration != DEFAULT_DURATION else None,
                "chars": [str(ref) for ref in scene.get("characters", [])],
                "objs": [str(ref) for ref in scene.get("objects", [])],
            }
            files = {"end_on_next": shot.get("end_on_next") is True}
            for field in ("final", "video"):
                name = shot.get(field)
                if name and (directory / scene_id / Path(str(name)).name).is_file():
                    files[field] = f"{scene_id}/{Path(str(name)).name}"
            shots.append((shot_note, files))
        plan.append((scene_note, shots))

    text = _title_page(str(raw.get("title") or directory.name), str(raw.get("synopsis", ""))) + "\n".join(body)
    text = fountain.annotate(text, [note for note, _ in plan], [[note for note, _ in shots] for _, shots in plan])
    meta = {"aspect_ratio": raw.get("aspect_ratio"), "final_provider": raw.get("final_provider"),
            "shots": {}, "scenes": {}}
    # Frames and videos stay current: they were made from what was just converted.
    parsed = fountain.parse(text)
    for raw_scene, (_, shots) in zip(parsed["scenes"], plan):
        scene = {"heading": raw_scene["heading"], "summary": raw_scene["summary"],
                 "locations": raw_scene["note"].get("loc", [])}
        for raw_shot, (note, files) in zip(raw_scene["shots"], shots):
            shot = {"action": raw_shot["action"], "characters": note["chars"], "objects": note["objs"],
                    "duration": int(note["dur"] or DEFAULT_DURATION)}
            if files.get("final"):
                files["final_hash"] = fingerprint(scene, shot)
            if files.get("video"):
                files["video_hash"] = video_fingerprint(scene, shot)
                final, video = directory / files.get("final", "-"), directory / files["video"]
                newer = final.is_file() and video.stat().st_mtime >= final.stat().st_mtime
                files["video_final"] = files.get("final") if newer else None
            meta["shots"][note["id"]] = files
    (directory / SCRIPT_FILE).write_text(text)
    write_json(directory / EPISODE_FILE, _clean_meta(meta))
