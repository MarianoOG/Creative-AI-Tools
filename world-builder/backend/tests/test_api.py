"""The story routes, end to end through FastAPI (the text model is faked)."""

import uuid

from fastapi.testclient import TestClient

from app.assets import tagging
from app.assets.worlds import create_world
from app.main import app

client = TestClient(app)


def test_episode_routes(monkeypatch):
    monkeypatch.setattr(tagging, "tag", lambda world, scenes: {"scenes": {}, "shots": {}})
    world = create_world(f"w{uuid.uuid4().hex[:8]}", style="flat")
    base = f"/worlds/{world}/episodes"
    name = client.post(base, json={"title": "Pilot"}).json()["name"]
    text = client.get(f"{base}/{name}").json()["text"]
    edited = text.replace("Describe the next shot.", "Describe the next shot.\n\nOne more shot.")

    preview = client.post(f"{base}/{name}/preview", json={"text": edited}).json()
    assert preview["summary"]["changed"] and any(e["type"] == "heading" for e in preview["elements"])

    saved = client.put(f"{base}/{name}/text", json={"text": edited}).json()
    shots = saved["episode"]["scenes"][0]["shots"]
    assert len(shots) == 3 and all(shot["id"] for shot in shots)

    patched = client.patch(f"{base}/{name}/shots/{shots[0]['id']}", json={"duration": 10}).json()
    assert patched["scenes"][0]["shots"][0]["duration"] == 10
    assert client.patch(f"{base}/{name}/shots/{shots[0]['id']}", json={"duration": 7}).status_code == 400
    assert client.patch(f"{base}/{name}", json={"aspect_ratio": "square"}).json()["aspect_ratio"] == "square"
    assert client.get(f"{base}/{name}/versions").json()["versions"]
    assert client.post(f"{base}/{name}/shots/nope/generate").status_code == 404
    assert client.get(f"{base}").json()["episodes"][0]["shot_count"] == 3
    options = client.get("/assets/options").json()
    assert options["checklist"] and options["text_model"] == "anthropic:claude@haiku-5.5"
