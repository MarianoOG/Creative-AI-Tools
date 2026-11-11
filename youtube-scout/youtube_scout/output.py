"""The local, git-ignored output of a run: ``out/YYYY-MM-DD.json`` and ``.md``.

Channels appear in the order the private relevance check left them, with no
score, rank number or metric. There is no contact information of any kind.
"""

from __future__ import annotations

from pathlib import Path

from .state import write_json, write_text

OUTPUT_FIELDS = (
    "title",
    "url",
    "subscriber_count",
    "video_count",
    "last_upload",
    "recent_titles",
    "fit_reason",
    "discovery_path",
)


def channel_record(channel: dict) -> dict:
    return {key: channel.get(key) for key in OUTPUT_FIELDS}


def write_outputs(out_dir: Path, run_date: str, channels: list[dict], summary: dict) -> tuple[Path, Path]:
    records = [channel_record(c) for c in channels]
    json_path = out_dir / f"{run_date}.json"
    md_path = out_dir / f"{run_date}.md"
    write_json(json_path, {"date": run_date, "channels": records, "summary": summary})
    write_text(md_path, render_markdown(run_date, records, summary))
    return json_path, md_path


def render_markdown(run_date: str, records: list[dict], summary: dict) -> str:
    lines = [f"# YouTube Scout: {run_date}", ""]
    if not records:
        lines += ["No channels matched today.", ""]
    for record in records:
        lines += [
            f"## [{record['title']}]({record['url']})",
            "",
            f"- Subscribers: {record['subscriber_count']:,} · Videos: {record['video_count']:,}"
            f" · Last upload: {(record['last_upload'] or '')[:10]}",
            f"- Fit: {record['fit_reason']}",
            f"- Found via: {'; '.join(record['discovery_path'])}",
            "- Recent videos:",
            *[f"  - {title}" for title in record["recent_titles"]],
            "",
        ]
    lines += ["## Run summary", ""]
    if summary.get("stopped_early"):
        lines += [f"**Stopped early:** {summary['stopped_early']}", ""]
    quota = summary.get("quota_used", {})
    lines += [
        f"- Quota used this run: {sum(quota.values())} units"
        + (" (" + ", ".join(f"{k} {v}" for k, v in sorted(quota.items())) + ")" if quota else ""),
        f"- Quota used today: {summary.get('quota_used_today', 0)} of {summary.get('quota_limit', 0)}",
        f"- Keywords searched: {', '.join(summary.get('keywords_searched', [])) or 'none'}",
        f"- Channels seen: {summary.get('channels_seen', 0)} · kept: {summary.get('channels_kept', 0)}",
    ]
    excluded = summary.get("excluded", {})
    if excluded:
        lines.append("- Left out: " + ", ".join(f"{reason} {n}" for reason, n in sorted(excluded.items())))
    sources = summary.get("candidates_by_source", {})
    if sources:
        lines.append("- Candidates by source: " + ", ".join(f"{k} {v}" for k, v in sorted(sources.items())))
    return "\n".join(lines) + "\n"
