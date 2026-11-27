"""Episodes on disk: saving text, tags, versions, stale frames and converting episodes from before Fountain."""

import json
import uuid

import pytest

from app.assets import library, story, tagging
from app.assets.worlds import create_world


@pytest.fixture
def world():
    name = create_world(f"w{uuid.uuid4().hex[:8]}", style="flat")
    library.create_asset(name, "character", "mara", "A girl.")
    library.create_asset(name, "location", "kitchen", "A kitchen.")
    library.create_asset(name, "object", "lantern", "A lantern.")
    return name


@pytest.fixture
def calls(monkeypatch):
    """A fake text model: tags every shot with mara and every scene with kitchen, and says nothing is missing."""
    seen = []

    def fake(world_data, scenes):
        seen.append(scenes)
        return {
            "scenes": {scene["key"]: ["kitchen"] for scene in scenes if scene["tag"]},
            "shots": {shot["key"]: {"chars": ["mara"], "objs": [], "missing": ["Camera angle"]}
                      for scene in scenes for shot in scene["shots"]},
        }
    monkeypatch.setattr(tagging, "tag", fake)
    return seen


TEXT = """Title: Pilot

INT. KITCHEN - DAY

Mara walks in.

MARA
Hello?

She sees the lantern.
"""


def test_new_episode_starts_from_the_template(world):
    episode = story.create_episode(world, "Pilot", "A start.", "portrait")
    view = story.read_episode(world, episode)
    assert view["title"] == "Pilot" and view["synopsis"] == "A start." and view["aspect_ratio"] == "portrait"
    assert view["scenes"][0]["heading"] == "INT. PLACE - TIME OF DAY"
    assert view["needs_ids"]  # nothing has been saved yet


def test_save_tags_checks_and_keeps_ids(world, calls):
    episode = story.create_episode(world, "Pilot")
    result = story.save_text(world, episode, TEXT)
    view = result["episode"]
    scene = view["scenes"][0]
    assert scene["id"] and scene["locations"] == ["kitchen"]
    first, second = scene["shots"]
    assert first["characters"] == ["mara"] and first["missing"] == ["Camera angle"]
    assert first["dialogue"][0]["text"] == "Hello?"
    assert view["text"] == TEXT and not view["needs_reprocess"]
    assert "[[wb: id=" in (story.episode_dir(world, episode) / story.SCRIPT_FILE).read_text()

    # Saving the same text again changes nothing and asks the model nothing.
    calls.clear()
    again = story.save_text(world, episode, TEXT)
    assert not again["summary"]["changed"] and not calls
    # Editing one shot keeps both ids and asks only about that shot.
    edited = story.save_text(world, episode, TEXT.replace("Mara walks in.", "Mara walks in, slowly."))
    assert [shot["id"] for shot in edited["episode"]["scenes"][0]["shots"]] == [first["id"], second["id"]]
    assert edited["summary"]["shots"]["modified"] == 1
    assert [shot["key"] for scene in calls[0] for shot in scene["shots"]] == [first["id"]]


def test_hand_tags_survive_edits(world, calls):
    episode = story.create_episode(world, "Pilot")
    shot = story.save_text(world, episode, TEXT)["episode"]["scenes"][0]["shots"][0]
    story.set_shot(world, episode, shot["id"], characters=[], objects=["lantern"], duration=8)
    view = story.save_text(world, episode, TEXT.replace("Mara walks in.", "Mara walks in, slowly."))["episode"]
    edited = view["scenes"][0]["shots"][0]
    assert edited["characters"] == [] and edited["objects"] == ["lantern"] and edited["duration"] == 8


def test_failed_tagging_still_saves(world, monkeypatch):
    def broken(*_):
        raise RuntimeError("no key")
    monkeypatch.setattr(tagging, "tag", broken)
    episode = story.create_episode(world, "Pilot")
    result = story.save_text(world, episode, TEXT)
    assert "no key" in result["warning"]
    assert result["episode"]["scenes"][0]["shots"][0]["id"]
    assert result["episode"]["needs_reprocess"]


def test_stale_frames_versions_and_restore(world, calls):
    episode = story.create_episode(world, "Pilot")
    shot = story.save_text(world, episode, TEXT)["episode"]["scenes"][0]["shots"][0]
    frame = story.shots_dir(world, episode) / f"abcd1234-{shot['id']}-final.jpg"
    frame.parent.mkdir(exist_ok=True)
    frame.write_bytes(b"jpg")
    story.set_shot_file(world, episode, shot["id"], "final", frame)
    assert not story.read_episode(world, episode)["scenes"][0]["shots"][0]["final_stale"]

    preview = story.preview(world, episode, TEXT.replace("Mara walks in.", "Mara runs in."))
    assert preview["summary"]["stale"] == {"frames": 1, "videos": 0}
    edited = story.save_text(world, episode, TEXT.replace("Mara walks in.", "Mara runs in."))["episode"]
    assert edited["scenes"][0]["shots"][0]["final_stale"]

    removed = story.save_text(world, episode, TEXT.replace("Mara walks in.\n\nMARA\nHello?\n\n", ""))
    assert removed["summary"]["unlinked"]["frames"] == 1
    assert [entry["id"] for entry in removed["episode"]["unlinked"]] == [shot["id"]]

    # Restoring the version before the removal links the frame again.
    versions = story.list_versions(world, episode)
    restored = story.restore_version(world, episode, versions[0]["name"])
    assert restored["scenes"][0]["shots"][0]["id"] == shot["id"]
    assert restored["scenes"][0]["shots"][0]["final_path"] and not restored["unlinked"]


def test_reprocess_fills_in_an_edited_file(world, calls):
    episode = story.create_episode(world, "Pilot")
    story.save_text(world, episode, TEXT)
    path = story.episode_dir(world, episode) / story.SCRIPT_FILE
    path.write_text(path.read_text() + "\nA shot added in another app.\n")
    assert story.reprocess_preview(world, episode)["ids"] == 1
    view = story.reprocess(world, episode)["episode"]
    assert all(shot["id"] and shot["tagged"] for shot in view["scenes"][0]["shots"])


def test_unknown_names_are_problems(world, calls):
    episode = story.create_episode(world, "Pilot")
    text = TEXT.replace("MARA\nHello?", "GHOST\nBoo.")
    view = story.save_text(world, episode, text)["episode"]
    assert any("GHOST speaks" in problem["message"] for problem in view["problems"])


def test_rename_references(world, calls):
    episode = story.create_episode(world, "Pilot")
    story.save_text(world, episode, TEXT)
    story.rename_references(world, "characters", "mara", "mara_jones")
    assert story.read_episode(world, episode)["scenes"][0]["shots"][0]["characters"] == ["mara_jones"]


def test_converts_an_episode_from_before_fountain(world):
    directory = story.episodes_dir(world) / "old"
    (directory / "scene1").mkdir(parents=True)
    (directory / "scene1" / "11111111-shot1-final.jpg").write_bytes(b"jpg")
    (directory / "scene1" / "22222222-shot1-video.mp4").write_bytes(b"mp4")
    (directory / "script.json").write_text(json.dumps({
        "title": "Old one", "synopsis": "Before.", "aspect_ratio": "square", "final_provider": "runware",
        "scenes": [{
            "id": "scene1", "heading": "the kitchen", "summary": "Mara arrives.",
            "characters": ["mara"], "locations": ["kitchen"], "objects": ["lantern"],
            "shots": [
                {"id": "shot1", "type": "Wide shot", "action": "MARA", "final": "11111111-shot1-final.jpg",
                 "video": "22222222-shot1-video.mp4", "duration": 8, "camera": "Push in", "end_on_next": True},
                {"id": "shot2", "type": None, "action": "", "camera": "Static"},
            ],
        }],
    }))
    view = story.read_episode(world, "old")
    assert view["title"] == "Old one" and view["aspect_ratio"] == "square" and view["final_provider"] == "nano-banana"
    scene = view["scenes"][0]
    assert scene["heading"] == "the kitchen" and scene["summary"] == "Mara arrives." and scene["locations"] == ["kitchen"]
    first, second = scene["shots"]
    assert first["action"] == "Wide shot. MARA Camera: push in."
    assert first["characters"] == ["mara"] and first["objects"] == ["lantern"]
    assert first["duration"] == 8 and first["end_on_next"]
    assert first["final_path"] and first["video_path"] and not first["final_stale"] and not first["video_stale"]
    assert second["action"] == "(No action yet.)"
    assert (directory / "script.json").is_file()
