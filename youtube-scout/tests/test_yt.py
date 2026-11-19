"""Tests for yt.py. The API is faked; nothing reaches the network."""

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import yt  # noqa: E402


def ch(cid, subs=1000, videos=10, kids=False, hidden=False):
    return {"id": cid, "snippet": {"title": cid, "customUrl": "@" + cid.lower()},
            "statistics": {"subscriberCount": str(subs), "videoCount": str(videos),
                           "hiddenSubscriberCount": hidden},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid[2:]}},
            "status": {"madeForKids": kids}}


def vid(vid_id, cid="UCa", date="2026-11-01T00:00:00Z"):
    return {"id": vid_id, "snippet": {"title": "T" + vid_id, "channelId": cid, "publishedAt": date},
            "statistics": {"viewCount": "100", "likeCount": "5", "commentCount": "2"}}


CHANNELS = {c["id"]: c for c in [ch("UCa"), ch("UCb", subs=50_000), ch("UCkid", kids=True),
                                  ch("UChid", hidden=True), ch("UCnone", videos=0)]}


@pytest.fixture
def api(monkeypatch):
    calls = []

    def fake_get(method, **params):
        calls.append((method, params))
        yt.units_used += yt.COST[method]
        if method == "channels":
            if "forHandle" in params:
                items = [c for c in CHANNELS.values() if c["snippet"]["customUrl"] == "@" + params["forHandle"]]
            else:
                items = [CHANNELS[i] for i in params["id"].split(",") if i in CHANNELS]
            return {"items": items}
        if method == "playlistItems":
            return {"items": [{"contentDetails": {"videoId": v}} for v in ("v1", "v2")]}
        if method == "videos":
            dates = {"v1": "2026-10-01T00:00:00Z", "v2": "2026-11-01T00:00:00Z"}
            return {"items": [vid(v, date=dates.get(v, "2026-01-01T00:00:00Z")) for v in params["id"].split(",")]}
        if method == "search":
            return {"items": [{"id": {"videoId": f"s{i}"},
                               "snippet": {"title": f"hit {i}", "channelId": cid, "channelTitle": cid,
                                           "publishedAt": "2026-11-10T00:00:00Z"}}
                              for i, cid in enumerate(["UCa", "UCb", "UCa"])]}
        if method == "commentThreads":
            if params["videoId"] == "off":
                raise yt.YouTubeError("commentThreads: HTTP 403 commentsDisabled")
            page = params.get("pageToken") or "p1"
            items = [{"id": f"t{page}{i}", "snippet": {"totalReplyCount": 1, "topLevelComment": {"id": f"c{page}{i}", "snippet": {
                "textOriginal": f"{page} q{i}?", "likeCount": i, "authorDisplayName": "Someone",
                "authorChannelId": {"value": "UCsomeone"}}}}} for i in range(100)]
            return {"items": items, "nextPageToken": "p2" if page == "p1" else None}
        if method == "channelSections":
            return {"items": [{"contentDetails": {"channels": ["UCb", "UCa", "UCb"]}}, {"contentDetails": {}}]}
        if method == "subscriptions":
            if params["channelId"] == "UCb":
                raise yt.YouTubeError("subscriptions: HTTP 403 subscriptionForbidden")
            return {"items": [{"snippet": {"resourceId": {"channelId": "UCb"}}}]}
        raise AssertionError(method)

    monkeypatch.setattr(yt, "get", fake_get)
    monkeypatch.setattr(yt, "units_used", 0)
    return calls


def test_channel_by_id_handle_and_url(api):
    assert yt.channel("UCa")["subscribers"] == 1000
    assert yt.channel("@ucb")["channel_id"] == "UCb"
    assert yt.channel("https://www.youtube.com/channel/UCa/")["channel_id"] == "UCa"
    assert yt.channel("https://www.youtube.com/@ucb")["channel_id"] == "UCb"
    with pytest.raises(yt.YouTubeError, match="not found"):
        yt.channel("@nobody")


def test_hidden_subscribers_are_none(api):
    assert yt.channel("UChid")["subscribers"] is None


def test_channels_batches_by_50(api):
    yt.channels([f"UC{i}" for i in range(120)])
    assert [m for m, _ in api] == ["channels"] * 3


def test_uploads_newest_first_with_stats(api):
    result = yt.uploads("@uca", n=2)
    assert [v["video_id"] for v in result] == ["v2", "v1"]
    assert result[0]["views"] == 100 and result[0]["url"].endswith("v2")
    assert yt.units_used == 3


def test_search_params(api):
    hits = yt.search("stop motion", n=80, days=14, lang="es", order="date")
    method, params = api[0]
    assert method == "search" and params["maxResults"] == 50 and params["relevanceLanguage"] == "es"
    assert params["publishedAfter"].endswith("Z") and params["order"] == "date" and params["type"] == "video"
    assert hits[0]["channel_id"] == "UCa" and yt.units_used == 100


def test_creators_groups_hits_by_channel(api):
    result = {c["channel_id"]: c for c in yt.creators("stop motion")}
    assert result["UCa"]["matched_videos"] == ["hit 0", "hit 2"]
    assert yt.units_used == 101


def test_comments_paginate_and_drop_authors(api):
    result = yt.comments("v1", n=150)
    assert len(result) == 150 and result[100]["text"] == "p2 q0?"
    assert set(result[0]) == {"comment_id", "url", "text", "likes", "replies", "published_at"}
    assert result[0]["url"] == "https://www.youtube.com/watch?v=v1&lc=cp10"
    assert yt.comments("off") == []


def test_featured_and_subscriptions(api):
    assert yt.featured("UCa") == ["UCb", "UCa"]
    assert yt.units_used == 1  # an id needs no lookup
    assert yt.subscriptions("UCa") == ["UCb"]
    assert yt.subscriptions("UCb") == []  # private list


def test_band_filter(api):
    chans = yt.channels(list(CHANNELS))
    kept = [c["channel_id"] for c in yt.band(chans, 500, 5000)]
    assert kept == ["UCa"]
    assert "UCkid" in [c["channel_id"] for c in yt.band(chans, 500, 5000, include_kids=True)]


def test_cli_prints_json(api, capsys):
    assert yt.main(["channel", "UCa"]) == 0
    out, err = capsys.readouterr()
    assert json.loads(out)["channel_id"] == "UCa" and "1 quota units" in err


def test_cli_channels(api, capsys):
    assert yt.main(["channels", "UCa", "UCb"]) == 0
    assert [c["channel_id"] for c in json.loads(capsys.readouterr().out)] == ["UCa", "UCb"]


def test_cli_band_reads_stdin(api, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(yt.channels(["UCa", "UCb"]))))
    assert yt.main(["band", "500", "5000"]) == 0
    assert [c["channel_id"] for c in json.loads(capsys.readouterr().out)] == ["UCa"]


def test_missing_key(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(yt, "__file__", str(tmp_path / "yt.py"))
    assert yt.main(["channel", "UCa"]) == 1
    assert "YOUTUBE_API_KEY is not set" in capsys.readouterr().err


def test_key_from_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OTHER=1\nYOUTUBE_API_KEY='abc'\n")
    assert yt._key() == "abc"


def test_http_error_message(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")

    def fail(url, timeout):
        body = io.BytesIO(json.dumps({"error": {"message": "Quota exceeded",
                                                "errors": [{"reason": "quotaExceeded"}]}}).encode())
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, body)

    monkeypatch.setattr(yt.urllib.request, "urlopen", fail)
    with pytest.raises(yt.YouTubeError, match="403 quotaExceeded Quota exceeded"):
        yt.get("search", q="x")
