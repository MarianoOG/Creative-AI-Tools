"""Rendering through Runware: the task each model is sent, and how locations become panoramas (Runware is faked)."""

import base64
import io
import uuid

from fastapi.testclient import TestClient
from PIL import Image

from app.assets import generation, library
from app.assets.generation import image_size, model_key, runware_task
from app.assets.prompt_manager import build_prompt
from app.assets.worlds import create_world
from app.main import app

client = TestClient(app)


def _jpeg(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "grey").save(buffer, "JPEG")
    return buffer.getvalue()


def test_tasks_per_model():
    gpt = runware_task("gpt-image-sunburst", "a forest", image_size("gpt-image-sunburst", "panorama", "2K"), "high")
    assert gpt["model"] == "openai:gpt-image@2.6-sunburst" and (gpt["width"], gpt["height"]) == (3072, 1024)
    assert gpt["settings"] == {"quality": "high"} and "steps" not in gpt and gpt["includeCost"]

    frame = runware_task("gpt-image-flare", "a frame", image_size("gpt-image-flare", "landscape", "1K"), "frame",
                         ["data:image/jpeg;base64,AAAA"])
    assert frame["model"] == "openai:gpt-image@2.6-flare" and frame["settings"] == {"quality": "medium"}
    assert frame["inputs"] == {"referenceImages": ["data:image/jpeg;base64,AAAA"]}

    nano = runware_task("nano-banana", "a forest", image_size("nano-banana", "landscape", "1K"), "frame")
    assert nano["model"] == "google:nano-banana@2.1" and (nano["width"], nano["height"]) == (1376, 768)
    assert nano["settings"] == {"thinkingLevel": "high"}

    flux = runware_task("flux-klein", "a forest", image_size("flux-klein", "panorama", "2K"), "high")
    assert flux["steps"] == 4 and "settings" not in flux and max(flux["width"], flux["height"]) <= 2048


def test_older_model_names_are_translated():
    assert [model_key(name) for name in ("openai", "gemini", "runware", "nano-banana", None)] == [
        "gpt-image-sunburst", "nano-banana", "flux-klein", "nano-banana", None,
    ]


def test_location_prompts():
    first = build_prompt("location", "A forest.", "flat")
    assert "panoramic" in first and "3:1" in first
    later = build_prompt("location", "A forest at night.", "flat", clause="location_variation", view="variation")
    assert "same wide 3:1 panoramic composition" in later


def test_locations_render_as_panoramas(monkeypatch):
    sent = []

    def fake_runware(task):
        sent.append(task)
        return _jpeg(task["width"] // 16, task["height"] // 16), 0.07

    monkeypatch.setattr(generation, "_runware_bytes", fake_runware)
    world = create_world(f"w{uuid.uuid4().hex[:8]}", style="flat")
    client.post("/assets", json={"world": world, "asset_type": "location", "name": "forest", "description": "A forest."})

    form = {"world": world, "asset_type": "location", "name": "forest", "provider": "openai"}
    first = client.post("/assets/variations", data={**form, "variation": "ignored"}).json()["asset"]
    assert [v["name"] for v in first["variations"]] == ["panorama"] and first["preferred"] == "panorama"
    assert first["variations"][0]["provider"] == "gpt-image-sunburst"
    assert (sent[0]["width"], sent[0]["height"]) == (3072, 1024) and "inputs" not in sent[0]

    assert client.post("/assets/variations", data={**form, "variation": "night"}).status_code == 422
    night = client.post("/assets/variations", data={**form, "variation": "night", "description": "After dusk."})
    assert night.status_code == 200 and len(sent[1]["inputs"]["referenceImages"]) == 1
    assert (sent[1]["width"], sent[1]["height"]) == (3072, 1024)


def test_older_locations_keep_their_first_image_as_base(monkeypatch):
    sent = []
    monkeypatch.setattr(generation, "_runware_bytes", lambda task: (sent.append(task), (_jpeg(64, 36), 0.05))[1])
    world = create_world(f"w{uuid.uuid4().hex[:8]}", style="flat")
    library.create_asset(world, "location", "market", "A market.")
    old = library.references_dir(world).parent / "locations" / "old-market-establishing.jpg"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(_jpeg(64, 36))
    for name in ("establishing", "reverse"):
        library.put_variation(world, "location", "market",
                              {"name": name, "description": "", "provider": "gemini", "image": old.name, "references": []})

    result = client.post("/assets/regenerate", json={"world": world, "asset_type": "location", "name": "market"}).json()
    assert result["warning"] is None and len(sent) == 2
    # The base (establishing) renders first, from the description, as a panorama; reverse is drawn from it.
    assert "inputs" not in sent[0] and (sent[0]["width"], sent[0]["height"]) == (3072, 1024)
    assert len(sent[1]["inputs"]["referenceImages"]) == 1
    assert base64.b64decode(sent[1]["inputs"]["referenceImages"][0].split(",", 1)[1])[:2] == b"\xff\xd8"
