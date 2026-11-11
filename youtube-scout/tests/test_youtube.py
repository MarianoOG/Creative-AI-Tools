import json

import pytest

from youtube_scout.errors import QuotaStop
from youtube_scout.youtube import COSTS, QuotaLedger, YouTube


def test_ledger_stops_before_crossing_the_limit_and_persists(tmp_path, transport, frozen):
    ledger = QuotaLedger(tmp_path, limit=201)
    yt = YouTube(transport, ledger)
    yt.search_recent_videos("claymation walk cycle", "2026-10-28T00:00:00Z", "en")
    yt.search_recent_videos("claymation walk cycle", "2026-10-28T00:00:00Z", "en")
    with pytest.raises(QuotaStop):
        yt.search_recent_videos("claymation walk cycle", "2026-10-28T00:00:00Z", "en")
    assert transport.count("search") == 2
    yt.channels(["UCgood"])
    with pytest.raises(QuotaStop):
        yt.channels(["UCgood"])
    saved = json.loads((tmp_path / "quota-2026-11-11.json").read_text())
    assert saved["by_method"] == {"search": 200, "channels": 1}
    # A second process the same day continues from the saved usage.
    assert QuotaLedger(tmp_path, limit=201).used == 201


def test_default_limit_is_80_percent(cfg):
    assert cfg.quota_limit == 8000


def test_channels_batches_by_50(yt, transport):
    ids = [f"UC{i}" for i in range(120)]
    yt.channels(ids)
    assert transport.count("channels") == 3
    assert yt.ledger.used == 3 * COSTS["channels"]


def test_private_subscriptions_are_skipped(yt):
    assert yt.public_subscriptions("UCseed") == []
    assert yt.public_subscriptions("UCgood") == ["UCfeat"]


def test_only_known_read_methods(yt):
    assert set(COSTS) == {"search", "channels", "playlistItems", "videos", "commentThreads",
                          "channelSections", "subscriptions"}
