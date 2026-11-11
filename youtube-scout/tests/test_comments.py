import pytest

from youtube_scout import comments


@pytest.mark.parametrize("text", [
    "How do you make the armature", "What software do you use for onion skin", "can you make a tutorial on mouths",
    "¿Cómo haces el lip sync?", "Qué programa usas", "haz un tutorial de plastilina", "Is it hard?",
])
def test_questions(text):
    assert comments.is_question(text)


@pytest.mark.parametrize("text", ["Great video!", "Love it", "Me encanta", ""])
def test_not_questions(text):
    assert not comments.is_question(text)


def test_clean_strips_mentions_and_links():
    assert comments.clean("@someone what clay? https://x.y/z") == "what clay?"


def test_mine_writes_only_phrases(cfg, yt, llm, transport):
    path, phrases, stopped = comments.mine(cfg, yt, llm, video_ids=["s1"], channel_ids=[])
    assert not stopped
    assert path.name == "comments-2026-11-11.txt"
    lines = [l for l in path.read_text().splitlines() if not l.startswith("#")]
    assert lines == ["2\tbest clay for claymation", "1\tstop motion armature how to"]
    # The LLM saw cleaned question text only: no mentions, no non-questions, no authors.
    prompt = llm.prompts[0]
    assert "How do you make the armature?" in prompt and "@friend" not in prompt
    assert "Great video" not in prompt and "UCpub" not in prompt and "Someone" not in prompt
    text = path.read_text()
    for leaked in ("armature?", "UCpub", "UCviewer", "Someone", "@"):
        assert leaked not in text
    assert transport.count("commentThreads") == 1


def test_mine_from_channels_and_latest_output(cfg, yt, llm, transport):
    cfg.out_dir.mkdir()
    (cfg.out_dir / "2026-11-10.json").write_text(
        '{"channels": [{"url": "https://www.youtube.com/channel/UCgood"}]}')
    comments.mine(cfg, yt, llm, video_ids=[], channel_ids=[], from_latest=True)
    assert ("commentThreads", {"part": "snippet", "videoId": "g1", "maxResults": 100, "order": "relevance",
                               "textFormat": "plainText"}) in transport.calls
