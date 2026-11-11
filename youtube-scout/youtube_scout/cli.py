"""The ``peer-scout`` command line.

    peer-scout run [--force]        discover, filter, judge fit, write out/YYYY-MM-DD.{json,md}
    peer-scout keywords             (re)generate keywords.generated.txt from brand.txt
    peer-scout comments ...         mine viewer questions into out/comments-YYYY-MM-DD.txt
    peer-scout quota                show today's quota use per method
    peer-scout purge                delete every local output, cache and state file
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys

from . import comments, keywords, pipeline
from .config import Config, load_config, require_env
from .errors import ScoutError
from .llm import get_llm
from .state import purge_old_files
from .youtube import HttpTransport, QuotaLedger, YouTube


def youtube_client(cfg: Config) -> YouTube:
    key = require_env(
        "YOUTUBE_API_KEY",
        "Add your own YouTube Data API v3 key to youtube-scout/.env or the environment "
        "(https://console.cloud.google.com/apis/credentials).",
    )
    return YouTube(HttpTransport(key), QuotaLedger(cfg.state_dir, cfg.quota_limit))


def cmd_run(cfg: Config, args: argparse.Namespace) -> int:
    yt, llm = youtube_client(cfg), get_llm()
    summary = pipeline.run(cfg, yt, llm, force=args.force)
    print(
        f"Kept {summary['channels_kept']} of {summary['channels_seen']} channels seen; "
        f"used {sum(summary['quota_used'].values())} quota units this run "
        f"({summary['quota_used_today']}/{summary['quota_limit']} today)."
    )
    if summary.get("stopped_early"):
        print("Stopped early: " + summary["stopped_early"], file=sys.stderr)
    return 0


def cmd_keywords(cfg: Config, args: argparse.Namespace) -> int:
    generated = keywords.generate_keywords(cfg, get_llm())
    print(f"Wrote {len(generated)} keywords to {cfg.keywords_file}")
    return 0


def cmd_comments(cfg: Config, args: argparse.Namespace) -> int:
    purge_old_files([cfg.out_dir], cfg.retention_days)
    yt, llm = youtube_client(cfg), get_llm()
    path, phrases, stopped = comments.mine(
        cfg, yt, llm, args.video, args.channel, args.latest, args.videos_per_channel, args.pages
    )
    print(f"Wrote {len(phrases)} phrases to {path} (used {sum(yt.ledger.session.values())} quota units).")
    if stopped:
        print("Stopped early: " + stopped, file=sys.stderr)
    return 0


def cmd_quota(cfg: Config, args: argparse.Namespace) -> int:
    ledger = QuotaLedger(cfg.state_dir, cfg.quota_limit)
    print(f"{ledger.day} (Pacific): {ledger.used} of {ledger.limit} units "
          f"({cfg.quota_stop_fraction:.0%} of {cfg.daily_quota})")
    for method, units in sorted(ledger.by_method.items()):
        print(f"  {method}: {units}")
    return 0


def cmd_purge(cfg: Config, args: argparse.Namespace) -> int:
    if not args.yes:
        print("This deletes out/, state/ and keywords.generated.txt. Re-run with --yes to confirm.")
        return 1
    for directory in (cfg.out_dir, cfg.state_dir):
        shutil.rmtree(directory, ignore_errors=True)
    cfg.keywords_file.unlink(missing_ok=True)
    print("Deleted all local outputs and state.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="peer-scout", description="Find small YouTube channels in your niche.")
    parser.add_argument("--config", help="path to config.toml (default: ./config.toml in the project folder)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run discovery and write today's output")
    run.add_argument("--force", action="store_true", help="redo today's run instead of re-rendering it")
    run.set_defaults(func=cmd_run)

    sub.add_parser("keywords", help="(re)generate keywords.generated.txt from brand.txt").set_defaults(
        func=cmd_keywords
    )

    com = sub.add_parser("comments", help="mine viewer questions into keyword phrases")
    com.add_argument("--video", nargs="*", default=[], metavar="ID", help="video ids")
    com.add_argument("--channel", nargs="*", default=[], metavar="ID", help="channel ids (their recent uploads)")
    com.add_argument("--latest", action="store_true", help="use the channels in the latest scout output")
    com.add_argument("--videos-per-channel", type=int, default=3)
    com.add_argument("--pages", type=int, default=1, help="pages of 100 comments per video (1 unit each)")
    com.set_defaults(func=cmd_comments)

    sub.add_parser("quota", help="show today's quota use").set_defaults(func=cmd_quota)
    purge = sub.add_parser("purge", help="delete all local outputs and state")
    purge.add_argument("--yes", action="store_true")
    purge.set_defaults(func=cmd_purge)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")
    try:
        from pathlib import Path

        cfg = load_config(Path(args.config).resolve() if args.config else None)
        return args.func(cfg, args)
    except ScoutError as exc:
        print(f"peer-scout: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("peer-scout: interrupted; run again to resume.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
