"""One scout run: discover candidates, enrich, filter, judge fit, write the output.

The run is idempotent and resumable. Its progress is checkpointed in
``state/run-<date>.json`` after every step; running again the same day resumes
where it stopped, and a finished run only re-renders its output without new API
calls (unless ``force``). The checkpoint keeps eligible channel profiles and the
discovery paths of candidate creators, plus one-way hashes of rejected ids. It
never holds raw API responses, comments, commenter ids, or anything about
channels rejected as made for kids or run by a minor.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import timedelta

from . import keywords as kw
from .channels import id_hash, profile, profile_reject_reason, size_band, uploads_reject_reason
from .config import Config
from .errors import QuotaStop, ScoutError
from .llm import LLM
from .output import write_outputs
from .relevance import judge
from .state import prune_dated_map, purge_old_files, read_json, utc_now, write_json
from .youtube import YouTube

log = logging.getLogger("peer_scout")

FIT_ORDER = {"good": 0, "weak": 1}


class Run:
    def __init__(self, cfg: Config, yt: YouTube, llm: LLM, force: bool = False):
        self.cfg, self.yt, self.llm = cfg, yt, llm
        self.now = utc_now()
        self.date = self.now.date().isoformat()
        self.path = cfg.state_dir / f"run-{self.date}.json"
        self.cp = read_json(self.path, {})
        if force or not self.cp:
            self.cp = {
                "date": self.date,
                "steps": [],
                "candidates": {},  # channel_id -> {"paths": [...], "depth": n}
                "evaluated": [],  # id hashes of every channel already looked at
                "eligible": {},  # channel_id -> profile + recent uploads
                "verdicts": {},
                "excluded": {},
                "keywords_searched": [],
                "sources": {},  # candidate count per discovery source
                "quota_used": {},
                "done": False,
            }
        self.excluded = Counter(self.cp["excluded"])

    # Checkpoint ---------------------------------------------------------------
    def save(self) -> None:
        self.cp["excluded"] = dict(self.excluded)
        used = Counter(self.cp["quota_used"])
        used.update(self.yt.ledger.session)
        self.yt.ledger.session.clear()
        self.cp["quota_used"] = dict(used)
        write_json(self.path, self.cp)

    def step_done(self, name: str) -> bool:
        return name in self.cp["steps"]

    def finish_step(self, name: str) -> None:
        self.cp["steps"].append(name)
        self.save()

    def add_candidate(self, channel_id: str, path: str, depth: int = 1) -> None:
        if not channel_id or channel_id in self.skip_ids:
            return
        if channel_id not in self.cp["candidates"]:
            if id_hash(channel_id) in self.cp["evaluated"] and channel_id not in self.cp["eligible"]:
                return  # Already rejected this run; keep nothing about it
            sources = Counter(self.cp["sources"])
            sources[path.split(":", 1)[0]] += 1
            self.cp["sources"] = dict(sources)
        entry = self.cp["candidates"].setdefault(channel_id, {"paths": [], "depth": depth})
        if path not in entry["paths"]:
            entry["paths"].append(path)
        entry["depth"] = min(entry["depth"], depth)

    # Run ----------------------------------------------------------------------
    def run(self) -> dict:
        cfg = self.cfg
        purge_old_files([cfg.out_dir, cfg.state_dir], cfg.retention_days, self.now.date())
        reported = prune_dated_map(read_json(cfg.state_dir / "reported.json", {}), cfg.skip_reported_days)
        write_json(cfg.state_dir / "reported.json", reported)
        self.skip_ids = cfg.exclude_ids() | set(cfg.seed_channels) | set(reported) | {cfg.my_channel_id} - {""}

        if self.cp["done"]:
            log.info("Today's run is already finished; re-rendering its output (use --force to redo).")
            return self.write()

        try:
            keywords = self.prepare_keywords()
            self.band = self.size_band()
            self.search(keywords)
            self.seed_commenters()
            self.peer_graph()
            self.evaluate()
        except QuotaStop as stop:
            log.warning(str(stop))
            self.cp["stopped_early"] = str(stop)
            self.save()
        self.judge(keywords)
        self.cp["done"] = True
        summary = self.write()
        self.update_snowball_and_reported(reported)
        return summary

    def prepare_keywords(self) -> list[kw.Keyword]:
        if not self.step_done("keywords"):
            kw.generate_keywords(self.cfg, self.llm)
            self.finish_step("keywords")
        keywords = kw.read_keywords(self.cfg.keywords_file)
        if not keywords:
            raise ScoutError("keywords.generated.txt is empty. Run `peer-scout keywords`.")
        return keywords

    def size_band(self) -> tuple[int, int]:
        if "my_subscribers" not in self.cp and not self.cfg.size_band.is_absolute:
            mine = self.yt.channels([self.cfg.my_channel_id]).get(self.cfg.my_channel_id)
            if not mine:
                raise ScoutError(f"my_channel_id {self.cfg.my_channel_id} was not found.")
            me = profile(mine)
            if me["subscriber_count"] is None:
                raise ScoutError("Your channel hides its subscriber count; set an absolute size_band instead.")
            self.cp["my_subscribers"] = me["subscriber_count"]
            self.save()
        return size_band(self.cfg, self.cp.get("my_subscribers"))

    def search(self, keywords: list[kw.Keyword]) -> None:
        if "planned_keywords" not in self.cp:
            picked = kw.pick_keywords(self.cfg, keywords, self.cfg.searches_per_run)
            self.cp["planned_keywords"] = [[k.language, k.text] for k in picked]
            self.save()
        after = (self.now - timedelta(days=self.cfg.search_window_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for language, text in self.cp["planned_keywords"]:
            step = f"search:{text}"
            if self.step_done(step):
                continue
            hits = self.yt.search_recent_videos(text, after, language, self.cfg.search_results_per_keyword)
            for hit in hits:
                self.add_candidate(hit["channel_id"], f"keyword: {text}")
            self.cp["keywords_searched"].append(text)
            kw.mark_searched(self.cfg, kw.Keyword(language, text), self.date)
            self.finish_step(step)

    def seed_commenters(self) -> None:
        """Seed channels' recent videos -> commenters who publish videos themselves.

        Commenter ids live only in memory inside this step. Those that are not
        publishing channels are dropped immediately; comment text is never read.
        """
        if self.step_done("seeds") or not self.cfg.seed_channels:
            return
        seeds = self.yt.channels(self.cfg.seed_channels)
        for seed_id in self.cfg.seed_channels:
            if seed_id not in seeds:
                log.warning("Seed channel %s was not found.", seed_id)
                continue
            seed = profile(seeds[seed_id])
            authors: set[str] = set()
            for video in self.yt.recent_uploads(seed["uploads_playlist"], self.cfg.seed_videos):
                for page in self.yt.comment_pages(video["video_id"], max_pages=1):
                    for thread in page:
                        top = thread.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                        author = top.get("authorChannelId", {}).get("value", "")
                        if author and author not in self.skip_ids:
                            authors.add(author)
            unknown = [a for a in authors if id_hash(a) not in self.cp["evaluated"]]
            publishers = [cid for cid, item in self.yt.channels(unknown).items() if profile(item)["video_count"] > 0]
            authors.clear()
            for cid in publishers:
                self.add_candidate(cid, f"seed comments: {seed['title']}")
        self.finish_step("seeds")

    def peer_graph(self) -> None:
        """Featured channels and public subscriptions of seeds and the snowball frontier."""
        if not self.cfg.peer_graph or self.step_done("peers"):
            return
        frontier = read_json(self.cfg.state_dir / "frontier.json", [])
        sources = [{"channel_id": s, "title": None, "depth": 0, "seed": True} for s in self.cfg.seed_channels]
        sources += [dict(item, seed=False) for item in frontier if not item.get("expanded")]
        for source in sources:
            step = f"peers:{source['channel_id']}"
            if self.step_done(step):
                continue
            name = source["title"] or source["channel_id"]
            depth = source["depth"] + 1
            label = "seed" if source["seed"] else "snowball"
            for cid in self.yt.featured_channels(source["channel_id"]):
                self.add_candidate(cid, f"{label} featured: {name}", depth)
            for cid in self.yt.public_subscriptions(source["channel_id"]):
                self.add_candidate(cid, f"{label} subscriptions: {name}", depth)
            for item in frontier:
                if item["channel_id"] == source["channel_id"]:
                    item["expanded"] = True
            write_json(self.cfg.state_dir / "frontier.json", frontier)
            self.finish_step(step)
        self.finish_step("peers")

    def evaluate(self) -> None:
        evaluated = set(self.cp["evaluated"])
        pending = [cid for cid in self.cp["candidates"] if id_hash(cid) not in evaluated]
        for start in range(0, len(pending), 50):
            batch = pending[start:start + 50]
            items = self.yt.channels(batch)
            for cid in batch:
                item = items.get(cid)
                reason = "not found" if item is None else None
                p = profile(item) if item else None
                reason = reason or profile_reject_reason(p, self.band, self.cfg)
                if reason is None:
                    uploads = self.yt.recent_uploads(p["uploads_playlist"], self.cfg.recent_titles)
                    reason = uploads_reject_reason(uploads, self.cfg, self.now)
                if reason:
                    self.excluded[reason] += 1
                    del self.cp["candidates"][cid]  # Keep nothing about rejected channels
                else:
                    self.cp["eligible"][cid] = {
                        **{k: p[k] for k in ("channel_id", "title", "url", "description", "subscriber_count",
                                             "video_count", "language")},
                        "recent_titles": [u["title"] for u in uploads],
                        "last_upload": uploads[0]["published_at"],
                    }
                self.cp["evaluated"].append(id_hash(cid))
                evaluated.add(id_hash(cid))
                self.save()

    def judge(self, keywords: list[kw.Keyword]) -> None:
        todo = [c for cid, c in self.cp["eligible"].items() if cid not in self.cp["verdicts"]]
        if todo:
            brand = self.cfg.read_brand()
            self.cp["verdicts"].update(judge(self.llm, brand, [k.text for k in keywords], todo))
        for cid in list(self.cp["eligible"]):
            verdict = self.cp["verdicts"].get(cid)
            if not verdict:
                continue
            reason = None
            if verdict["possibly_minor"]:
                reason = "looks run by a minor"
            elif verdict["fit"] not in FIT_ORDER:
                reason = "off-niche"
            elif verdict["language"] and verdict["language"] not in self.cfg.languages:
                reason = "language"
            if reason:
                self.excluded[reason] += 1
                del self.cp["eligible"][cid]
                del self.cp["verdicts"][cid]
                self.cp["candidates"].pop(cid, None)
        self.save()

    def kept(self) -> list[dict]:
        judged = [c for cid, c in self.cp["eligible"].items() if cid in self.cp["verdicts"]]
        judged.sort(key=lambda c: FIT_ORDER[self.cp["verdicts"][c["channel_id"]]["fit"]])
        out = []
        for channel in judged[: self.cfg.max_results_per_run]:
            out.append(
                {
                    **channel,
                    "fit_reason": self.cp["verdicts"][channel["channel_id"]]["reason"],
                    "discovery_path": self.cp["candidates"].get(channel["channel_id"], {}).get("paths", []),
                }
            )
        return out

    def write(self) -> dict:
        kept = self.kept()
        summary = {
            "quota_used": self.cp["quota_used"],
            "quota_used_today": self.yt.ledger.used,
            "quota_limit": self.yt.ledger.limit,
            "keywords_searched": self.cp["keywords_searched"],
            "channels_seen": len(self.cp["evaluated"]),
            "channels_kept": len(kept),
            "excluded": dict(self.excluded),
            "candidates_by_source": self.cp["sources"],
            "stopped_early": self.cp.get("stopped_early", ""),
        }
        self.cp["summary"] = summary
        self.save()
        json_path, md_path = write_outputs(self.cfg.out_dir, self.date, kept, summary)
        log.info("Wrote %s and %s", json_path, md_path)
        return summary

    def update_snowball_and_reported(self, reported: dict) -> None:
        """Today's kept channels seed tomorrow's peer graph, capped to stay on-niche."""
        kept = self.kept()
        for channel in kept:
            reported[channel["channel_id"]] = self.date
        write_json(self.cfg.state_dir / "reported.json", reported)
        frontier = read_json(self.cfg.state_dir / "frontier.json", [])
        known = {item["channel_id"] for item in frontier}
        for channel in kept:
            depth = self.cp["candidates"].get(channel["channel_id"], {}).get("depth", 1)
            if channel["channel_id"] not in known and depth < self.cfg.snowball_max_depth:
                frontier.append({"channel_id": channel["channel_id"], "title": channel["title"],
                                 "depth": depth, "added": self.date})
        cutoff = (self.now.date() - timedelta(days=self.cfg.retention_days)).isoformat()
        frontier = [item for item in frontier if not item.get("expanded") and item.get("added", "") >= cutoff]
        frontier = frontier[-self.cfg.snowball_frontier_max:]
        write_json(self.cfg.state_dir / "frontier.json", frontier)


def run(cfg: Config, yt: YouTube, llm: LLM, force: bool = False) -> dict:
    return Run(cfg, yt, llm, force=force).run()
