"""LLM niche-fit judgement for the channels that passed the filters.

The judgement only orders and trims the local output. It is never written as a
score, rank or metric: the output keeps a plain-text reason per channel.
"""

from __future__ import annotations

from .llm import LLM, object_schema

BATCH = 8
DESCRIPTION_CHARS = 600

SYSTEM = (
    "You judge whether YouTube channels belong to a niche, from each channel's description and "
    "recent video titles. Be strict: a channel fits only if its own videos are about the niche, "
    "not if it mentions it once. Also report the main language of the channel's titles as an ISO "
    "639-1 code, and set possibly_minor to true if anything suggests the channel is run by someone "
    "under 18 (age, school grade, parent-managed) or is aimed at children."
)

SCHEMA = object_schema(
    {
        "channels": {
            "type": "array",
            "items": object_schema(
                {
                    "channel_id": {"type": "string"},
                    "fit": {"type": "string", "enum": ["good", "weak", "none"]},
                    "language": {"type": "string"},
                    "possibly_minor": {"type": "boolean"},
                    "reason": {"type": "string"},
                }
            ),
        }
    }
)


def _prompt(brand: str, keywords: list[str], channels: list[dict]) -> str:
    lines = [
        "Niche (brand and audience):\n" + brand,
        "Search keywords for the niche: " + "; ".join(keywords[:40]),
        "For each channel below, give fit (good / weak / none) and one short sentence of reason "
        "in English that names what the channel actually makes.",
    ]
    for channel in channels:
        titles = "\n".join(f"    - {t}" for t in channel["recent_titles"])
        lines.append(
            f"channel_id: {channel['channel_id']}\n  title: {channel['title']}\n"
            f"  description: {channel['description'][:DESCRIPTION_CHARS]!r}\n  recent titles:\n{titles}"
        )
    return "\n\n".join(lines)


def judge(llm: LLM, brand: str, keywords: list[str], channels: list[dict]) -> dict[str, dict]:
    """``{channel_id: {fit, language, possibly_minor, reason}}`` for every channel judged."""
    verdicts: dict[str, dict] = {}
    for start in range(0, len(channels), BATCH):
        batch = channels[start:start + BATCH]
        wanted = {c["channel_id"] for c in batch}
        result = llm.json(SYSTEM, _prompt(brand, keywords, batch), SCHEMA)
        for item in result.get("channels", []):
            if item.get("channel_id") in wanted:
                verdicts[item["channel_id"]] = {
                    "fit": item.get("fit", "none"),
                    "language": str(item.get("language", "")).lower()[:2],
                    "possibly_minor": bool(item.get("possibly_minor")),
                    "reason": " ".join(str(item.get("reason", "")).split()),
                }
    return verdicts
