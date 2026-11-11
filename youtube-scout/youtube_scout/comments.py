"""``peer-scout comments``: mine viewer questions for new keyword ideas.

Reads top-level comments with ``commentThreads.list`` (1 unit per 100), keeps
only the text of comments that are questions or requests, has the LLM rewrite
them as short search-style phrases and group the duplicates, and writes
``out/comments-YYYY-MM-DD.txt`` as ``count<TAB>phrase`` lines.

Comment text, author names and author ids are never written anywhere: author
fields are not even read, @mentions and links are stripped from the text, and
the texts are dropped from memory as soon as the phrases exist.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .config import Config
from .errors import QuotaStop, ScoutError
from .keywords import latest_file
from .llm import LLM, object_schema
from .state import utc_now, write_text
from .youtube import YouTube

BATCH = 60
MAX_CHARS = 300

_QUESTION_STARTS = (
    # English
    r"how\s+(do|did|does|can|could|would|to|long|much|many)", r"what\s+(is|are|was|do|did|does|tool|app|software"
    r"|program|brush|camera|mic|program|plugin|model|settings?|website|site)", r"which\s+\w+", r"where\s+(do|did|can)",
    r"why\s+(do|did|does|is|are)", r"can\s+you", r"could\s+you", r"would\s+you", r"will\s+you", r"do\s+you",
    r"did\s+you", r"is\s+there", r"are\s+there", r"any\s+(tips|advice|tutorial|recommendations?)",
    r"please\s+(make|do|show|explain|teach)", r"pls\s+(make|do|show)", r"make\s+a\s+(video|tutorial)",
    r"tutorial\s+(on|for|please)", r"i\s+(wonder|was\s+wondering)", r"does\s+anyone", r"anyone\s+know",
    # Spanish
    r"[¿]?\s*c[oó]mo", r"[¿]?\s*qu[eé]\s+(programa|app|aplicaci[oó]n|herramienta|software|pincel|c[aá]mara|usas|usaste"
    r"|es|son)", r"[¿]?\s*cu[aá]l(es)?", r"[¿]?\s*d[oó]nde", r"[¿]?\s*por\s*qu[eé]", r"[¿]?\s*puedes", r"[¿]?\s*podr[ií]as",
    r"[¿]?\s*har[aá]s", r"haz\s+un", r"hagan?\s+un", r"podr[ií]an", r"alg[uú]n\s+(tutorial|consejo|tip)",
    r"por\s+favor\s+(haz|explica|ense[nñ]a|muestra)",
)
_QUESTION_RE = re.compile(r"(^|[.!?\n]\s*)(" + "|".join(_QUESTION_STARTS) + r")\b", re.I)
_CLEAN_RE = re.compile(r"(https?://\S+|www\.\S+|@[\w.\-]+)")


def is_question(text: str) -> bool:
    text = text.strip()
    return bool(text) and ("?" in text or "¿" in text or bool(_QUESTION_RE.search(text)))


def clean(text: str) -> str:
    return " ".join(_CLEAN_RE.sub(" ", text).split())[:MAX_CHARS]


SYSTEM = (
    "You turn viewer questions from YouTube comments into short search-style phrases (2 to 7 words, "
    "lowercase, in the question's language), like what someone would type into YouTube search. "
    "Group questions that ask the same thing under one phrase and count them. Leave out anything "
    "personal, any names, and questions with no topic (e.g. 'how are you?')."
)

SCHEMA = object_schema(
    {
        "phrases": {
            "type": "array",
            "items": object_schema({"phrase": {"type": "string"}, "count": {"type": "integer"}}),
        }
    }
)


def channel_ids_from_latest_output(cfg: Config) -> list[str]:
    path = latest_file(cfg.out_dir, "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json")
    if not path:
        raise ScoutError("No scout output found in out/. Run `peer-scout run` first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return [c["url"].rsplit("/", 1)[-1] for c in data.get("channels", []) if c.get("url")]


def collect_questions(yt: YouTube, video_ids: list[str], max_pages: int) -> list[str]:
    questions: list[str] = []
    for video_id in video_ids:
        for page in yt.comment_pages(video_id, max_pages=max_pages):
            for thread in page:
                text = thread.get("snippet", {}).get("topLevelComment", {}).get("snippet", {}).get("textOriginal", "")
                if is_question(text):
                    cleaned = clean(text)
                    if cleaned:
                        questions.append(cleaned)
    return questions


def rewrite(llm: LLM, questions: list[str]) -> Counter:
    phrases: Counter = Counter()
    for start in range(0, len(questions), BATCH):
        batch = questions[start:start + BATCH]
        prompt = "Questions:\n" + "\n".join(f"- {q}" for q in batch)
        result = llm.json(SYSTEM, prompt, SCHEMA)
        for item in result.get("phrases", []):
            phrase = " ".join(str(item.get("phrase", "")).lower().split())
            count = item.get("count", 1)
            if phrase:
                phrases[phrase] += max(1, int(count) if isinstance(count, int) else 1)
    return phrases


def mine(
    cfg: Config,
    yt: YouTube,
    llm: LLM,
    video_ids: list[str],
    channel_ids: list[str],
    from_latest: bool = False,
    videos_per_channel: int = 3,
    max_pages: int = 1,
) -> tuple[Path, Counter, str]:
    """Mine and write phrases; returns ``(path, phrases, stopped_early_message)``."""
    channel_ids = list(channel_ids) + (channel_ids_from_latest_output(cfg) if from_latest else [])
    if not video_ids and not channel_ids:
        raise ScoutError("Give --video IDs, --channel IDs, or --latest.")
    stopped = ""
    questions: list[str] = []
    try:
        videos = list(video_ids)
        if channel_ids:
            for item in yt.channels(channel_ids).values():
                uploads = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")
                videos += [v["video_id"] for v in yt.recent_uploads(uploads, videos_per_channel)]
        questions = collect_questions(yt, list(dict.fromkeys(videos)), max_pages)
    except QuotaStop as stop:
        stopped = str(stop)
    phrases = rewrite(llm, questions) if questions else Counter()
    asked = len(questions)
    questions.clear()  # Comment text is never kept past this point

    today = utc_now().date().isoformat()
    path = cfg.out_dir / f"comments-{today}.txt"
    header = [
        f"# Questions from YouTube comments, rewritten as search phrases ({today}).",
        f"# {asked} question comments read; comment text and authors were not stored.",
        "# count<TAB>phrase",
    ]
    if stopped:
        header.append(f"# Stopped early: {stopped}")
    write_text(path, "\n".join(header + [f"{n}\t{p}" for p, n in phrases.most_common()]) + "\n")
    return path, phrases, stopped
