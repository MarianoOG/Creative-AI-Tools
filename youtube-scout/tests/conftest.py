"""Shared test setup: fixture-backed YouTube transport, a fake LLM, frozen time.

No test reaches the network. The YouTube fixtures in ``fixtures/youtube`` are
synthetic data in the API's response shapes (real recorded responses would be
third-party data, which this repository never stores).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from youtube_scout import channels, comments, keywords, pipeline, state
from youtube_scout.config import load_config
from youtube_scout.errors import ApiError
from youtube_scout.youtube import QuotaLedger, YouTube

FIXTURES = Path(__file__).parent / "fixtures" / "youtube"
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)

# Which request parameter selects the recorded response, per method.
KEY_PARAM = {
    "search": "q",
    "playlistItems": "playlistId",
    "commentThreads": "videoId",
    "channelSections": "channelId",
    "subscriptions": "channelId",
}


class FixtureTransport:
    def __init__(self):
        self.data = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in FIXTURES.glob("*.json")}
        self.calls: list[tuple[str, dict]] = []

    def get(self, method: str, params: dict) -> dict:
        assert "key" not in params, "the API key must only be added by HttpTransport"
        self.calls.append((method, dict(params)))
        if method == "channels":
            wanted = set(params["id"].split(","))
            assert len(wanted) <= 50
            return {"items": [i for i in self.data["channels"]["items"] if i["id"] in wanted]}
        response = self.data[method].get(params[KEY_PARAM[method]])
        if response is None:
            raise ApiError(404, "notFound")
        if "error" in response:
            raise ApiError(response["error"]["status"], response["error"]["reason"])
        return response

    def count(self, method: str) -> int:
        return sum(1 for m, _ in self.calls if m == method)


class FakeLLM:
    """Answers by schema: keywords, channel verdicts, or comment phrases."""

    def __init__(self):
        self.prompts: list[str] = []

    def json(self, system: str, prompt: str, schema: dict) -> dict:
        self.prompts.append(prompt)
        kind = next(iter(schema["properties"]))
        if kind == "keywords":
            return {"keywords": [
                {"language": "en", "keyword": "claymation walk cycle"},
                {"language": "es", "keyword": "animación con plastilina"},
                {"language": "en", "keyword": "Claymation  walk cycle"},  # duplicate
                {"language": "de", "keyword": "knetanimation"},  # not a configured language
            ]}
        if kind == "channels":
            ids = re.findall(r"channel_id: (\S+)", prompt)
            verdicts = {
                "UCgood": ("good", "en", False, "Plasticine stop-motion tests and lip sync."),
                "UCoff": ("none", "en", False, "Cooking recipes."),
                "UCpub": ("weak", "en", False, "Puppet animation tests."),
                "UCfeat": ("good", "en", False, "Claymation shorts."),
            }
            return {"channels": [
                dict(zip(("fit", "language", "possibly_minor", "reason"), verdicts.get(i, ("none", "en", False, "?"))),
                     channel_id=i) for i in ids
            ]}
        if kind == "phrases":
            return {"phrases": [
                {"phrase": "stop motion armature how to", "count": 1},
                {"phrase": "best clay for claymation", "count": 2},
            ]}
        raise AssertionError(kind)


@pytest.fixture
def frozen(monkeypatch):
    for module in (state, pipeline, channels, keywords, comments):
        monkeypatch.setattr(module, "utc_now", lambda: NOW)
    return NOW


@pytest.fixture
def project(tmp_path, monkeypatch):
    for name in ("YOUTUBE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "SCOUT_LLM_PROVIDER", "SCOUT_LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "brand.txt").write_text("A clay stop-motion animation channel for adult hobbyists.\n")
    (tmp_path / "config.toml").write_text(
        'my_channel_id = "UCme"\nlanguages = ["en", "es"]\nseed_channels = ["UCseed"]\n'
        "[discovery]\nsearches_per_run = 2\n"
    )
    return tmp_path


@pytest.fixture
def cfg(project):
    return load_config(root=project)


@pytest.fixture
def transport():
    return FixtureTransport()


@pytest.fixture
def yt(cfg, transport, frozen):
    return YouTube(transport, QuotaLedger(cfg.state_dir, cfg.quota_limit))


@pytest.fixture
def llm():
    return FakeLLM()
