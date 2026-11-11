import json
from datetime import timedelta

import pytest

from youtube_scout import pipeline, state
from youtube_scout.errors import ApiError
from youtube_scout.youtube import QuotaLedger, YouTube

from conftest import NOW


def all_local_text(root):
    return "\n".join(p.read_text(encoding="utf-8") for p in root.rglob("*") if p.is_file() and p.suffix in (".json", ".md", ".txt"))


def test_full_run_keeps_only_eligible_fitting_channels(cfg, yt, llm, transport):
    summary = pipeline.run(cfg, yt, llm)
    data = json.loads((cfg.out_dir / "2026-11-11.json").read_text())
    titles = [c["title"] for c in data["channels"]]
    # Good fits first, then weak; nothing excluded leaks through.
    assert titles == ["Clayframe Studio", "Featured Friend", "Commenter Who Publishes"]
    good = data["channels"][0]
    assert good["url"] == "https://www.youtube.com/channel/UCgood"
    assert good["subscriber_count"] == 900 and good["video_count"] == 12
    assert good["recent_titles"] == ["Clay walk cycle test", "Plasticine lip sync"]  # private video skipped
    assert good["last_upload"].startswith("2026-11-05")
    assert good["fit_reason"] == "Plasticine stop-motion tests and lip sync."
    assert good["discovery_path"] == ["keyword: claymation walk cycle", "keyword: animación con plastilina"]
    assert data["channels"][1]["discovery_path"] == ["seed featured: UCseed"]
    assert data["channels"][2]["discovery_path"] == ["seed comments: Seed Studio"]

    assert summary["excluded"] == {
        "outside size band": 1, "made for kids": 1, "looks run by a minor": 1, "inactive": 1,
        "hidden subscriber count": 1, "language": 1, "off-niche": 1,
    }
    assert summary["channels_kept"] == 3
    assert summary["keywords_searched"] == ["claymation walk cycle", "animación con plastilina"]
    assert summary["quota_used"]["search"] == 200
    assert transport.count("search") == 2
    assert all(call[1]["order"] == "date" and call[1]["type"] == "video" and call[1]["publishedAfter"] == "2026-10-28T12:00:00Z"
               for call in transport.calls if call[0] == "search")
    assert (cfg.out_dir / "2026-11-11.md").exists()


def test_output_has_no_scores_contacts_commenters_or_minors(cfg, yt, llm):
    pipeline.run(cfg, yt, llm)
    data = json.loads((cfg.out_dir / "2026-11-11.json").read_text())
    for channel in data["channels"]:
        assert set(channel) == {"title", "url", "subscriber_count", "video_count", "last_upload",
                                "recent_titles", "fit_reason", "discovery_path"}
    text = all_local_text(cfg.root).lower()
    for forbidden in ("score", "rank", "email", "@", "ucviewer", "just a viewer", "how do you make the armature",
                      "tiny animator", "i'm 12", "clay for kids", "ucminor", "uckids"):
        assert forbidden not in text, forbidden


def test_rerun_same_day_makes_no_api_calls(cfg, yt, llm, transport):
    pipeline.run(cfg, yt, llm)
    calls, prompts = len(transport.calls), len(llm.prompts)
    first = (cfg.out_dir / "2026-11-11.json").read_text()
    pipeline.run(cfg, yt, llm)
    assert len(transport.calls) == calls and len(llm.prompts) == prompts
    assert (cfg.out_dir / "2026-11-11.json").read_text() == first


def test_crashed_run_resumes_without_repeating_searches(cfg, yt, llm, transport, monkeypatch):
    original = transport.get

    def crash_on_channel_sections(method, params):
        if method == "channelSections":
            raise ApiError(500, "backendError")
        return original(method, params)

    monkeypatch.setattr(transport, "get", crash_on_channel_sections)
    with pytest.raises(ApiError):
        pipeline.run(cfg, yt, llm)
    assert transport.count("search") == 2

    monkeypatch.setattr(transport, "get", original)
    summary = pipeline.run(cfg, yt, llm)
    assert transport.count("search") == 2
    assert summary["channels_kept"] == 3
    assert summary["quota_used"]["search"] == 200


def test_quota_stop_still_writes_partial_output(cfg, transport, llm, frozen):
    yt = YouTube(transport, QuotaLedger(cfg.state_dir, limit=150))  # room for 1 search only
    summary = pipeline.run(cfg, yt, llm)
    assert transport.count("search") == 1
    assert "Stopping" in summary["stopped_early"]
    assert yt.ledger.used <= 150
    assert (cfg.out_dir / "2026-11-11.json").exists()


def test_snowball_and_no_repeats_next_day(cfg, yt, llm, transport, monkeypatch):
    pipeline.run(cfg, yt, llm)
    frontier = json.loads((cfg.state_dir / "frontier.json").read_text())
    # Keyword finds and direct seed peers are depth 1 and seed tomorrow.
    assert {item["channel_id"] for item in frontier} == {"UCgood", "UCpub", "UCfeat"}

    tomorrow = NOW + timedelta(days=1)
    for module in (state, pipeline):
        monkeypatch.setattr(module, "utc_now", lambda: tomorrow)
    yt2 = YouTube(transport, QuotaLedger(cfg.state_dir, cfg.quota_limit))
    transport.calls.clear()
    summary = pipeline.run(cfg, yt2, llm)
    assert ("channelSections", {"part": "contentDetails", "channelId": "UCgood"}) in transport.calls
    data = json.loads((cfg.out_dir / "2026-11-12.json").read_text())
    assert data["channels"] == []  # yesterday's channels are not repeated
    assert summary["channels_kept"] == 0
    frontier = json.loads((cfg.state_dir / "frontier.json").read_text())
    assert all(not item.get("expanded") for item in frontier)


def test_old_outputs_and_state_are_purged(cfg, yt, llm):
    old = cfg.out_dir / "2026-10-01.json"
    old_state = cfg.state_dir / "run-2026-10-01.json"
    for path in (old, old_state):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    recent = cfg.out_dir / "comments-2026-11-01.txt"
    recent.write_text("1\tphrase\n")
    pipeline.run(cfg, yt, llm)
    assert not old.exists() and not old_state.exists() and recent.exists()
