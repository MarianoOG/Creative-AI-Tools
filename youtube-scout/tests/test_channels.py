import pytest

from youtube_scout.channels import looks_like_minor, profile, profile_reject_reason, size_band, uploads_reject_reason


@pytest.mark.parametrize("text", [
    "I'm 12 and I love animation", "13 years old animator", "14yo artist", "tengo 13 años",
    "kid youtuber", "This channel is managed by my mom", "niño youtuber", "8th grader making cartoons",
])
def test_minor_signals(text):
    assert looks_like_minor(text)


@pytest.mark.parametrize("text", [
    "I'm 3D animator", "Animating for 12 years", "I'm 32 and learning", "10k subscribers soon",
    "I'm 12k subs away", "Blender 4.2 tutorial", "Trabajo hace 15 años en animación",
])
def test_not_minor(text):
    assert not looks_like_minor(text)


def test_size_band_from_multiplier(cfg):
    assert size_band(cfg, 1000) == (300, 3000)


def item(**over):
    base = {"id": "UC1", "snippet": {"title": "T", "description": "D"},
            "statistics": {"subscriberCount": "1000", "videoCount": "3"},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}, "status": {"madeForKids": False}}
    base.update(over)
    return base


def test_profile_reasons(cfg):
    band = (300, 3000)
    assert profile_reject_reason(profile(item()), band, cfg) is None
    assert profile_reject_reason(profile(item(status={"madeForKids": True})), band, cfg) == "made for kids"
    assert profile_reject_reason(profile(item(statistics={"hiddenSubscriberCount": True, "videoCount": "3"})), band, cfg) \
        == "hidden subscriber count"
    assert profile_reject_reason(profile(item(statistics={"subscriberCount": "5000", "videoCount": "3"})), band, cfg) \
        == "outside size band"
    assert profile_reject_reason(profile(item(statistics={"subscriberCount": "500", "videoCount": "0"})), band, cfg) \
        == "no public videos"


def test_upload_reasons(cfg, frozen):
    assert uploads_reject_reason([], cfg) == "no public videos"
    assert uploads_reject_reason([{"title": "x", "published_at": "2026-09-01T00:00:00Z"}], cfg) == "inactive"
    assert uploads_reject_reason([{"title": "x", "published_at": "2026-11-01T00:00:00Z"}], cfg) is None
    assert uploads_reject_reason([{"title": "my 5th grade project", "published_at": "2026-11-01T00:00:00Z"}], cfg) \
        == "looks run by a minor"
