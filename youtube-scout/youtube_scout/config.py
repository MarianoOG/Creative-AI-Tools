"""Settings from ``config.toml``, the niche input files and environment variables.

Everything local lives under the project root (the ``youtube-scout`` folder by
default, or ``SCOUT_HOME``). The real config, ``brand.txt``, the generated
keywords, ``.env``, ``out/`` and ``state/`` are git-ignored.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from .errors import ScoutError

MAX_RETENTION_DAYS = 30  # Hard constraint: derived API data is gone within 30 days


def project_root() -> Path:
    home = os.getenv("SCOUT_HOME", "").strip()
    return Path(home).expanduser().resolve() if home else Path(__file__).resolve().parent.parent


@dataclass
class SizeBand:
    min_subscribers: int | None = None
    max_subscribers: int | None = None
    min_multiplier: float = 0.3
    max_multiplier: float = 3.0

    @property
    def is_absolute(self) -> bool:
        return self.min_subscribers is not None and self.max_subscribers is not None


@dataclass
class Config:
    root: Path
    my_channel_id: str = ""
    size_band: SizeBand = field(default_factory=SizeBand)
    languages: list[str] = field(default_factory=lambda: ["en"])
    seed_channels: list[str] = field(default_factory=list)
    max_results_per_run: int = 20
    exclude_channel_ids_file: str = ""
    # Discovery
    searches_per_run: int = 8
    search_window_days: int = 14
    search_results_per_keyword: int = 50
    keyword_count: int = 30
    last_upload_within_days: int = 30
    recent_titles: int = 5
    seed_videos: int = 3
    peer_graph: bool = True
    snowball_frontier_max: int = 10
    snowball_max_depth: int = 2
    skip_reported_days: int = 30
    # Quota and retention
    daily_quota: int = 10_000
    quota_stop_fraction: float = 0.8
    retention_days: int = MAX_RETENTION_DAYS

    # Paths -----------------------------------------------------------------
    @property
    def brand_file(self) -> Path:
        return self.root / "brand.txt"

    @property
    def keywords_file(self) -> Path:
        return self.root / "keywords.generated.txt"

    @property
    def out_dir(self) -> Path:
        return self.root / "out"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def quota_limit(self) -> int:
        return int(self.daily_quota * self.quota_stop_fraction)

    def exclude_ids(self) -> set[str]:
        if not self.exclude_channel_ids_file:
            return set()
        path = Path(self.exclude_channel_ids_file).expanduser()
        if not path.is_absolute():
            path = self.root / path
        if not path.exists():
            raise ScoutError(f"exclude_channel_ids_file not found: {path}")
        return {
            line.split("#", 1)[0].strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.split("#", 1)[0].strip()
        }

    def read_brand(self) -> str:
        if not self.brand_file.exists():
            raise ScoutError(
                f"{self.brand_file.name} not found. Copy brand.example.txt to brand.txt "
                "and describe your brand/channel and its audience."
            )
        text = self.brand_file.read_text(encoding="utf-8").strip()
        if not text:
            raise ScoutError("brand.txt is empty. Describe your brand/channel and its audience.")
        return text


def _positive_int(data: dict, key: str, default: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ScoutError(f"config.toml: {key} must be a non-negative integer")
    return value


def load_config(path: Path | None = None, root: Path | None = None) -> Config:
    """Read ``config.toml`` (and ``.env`` into the environment)."""
    root = root or project_root()
    load_dotenv(root / ".env")
    path = path or root / "config.toml"
    if not path.exists():
        raise ScoutError(f"{path.name} not found. Copy config.example.toml to config.toml and edit it.")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ScoutError(f"config.toml is not valid TOML: {exc}") from exc

    band_data = data.get("size_band", {})
    band = SizeBand(
        min_subscribers=band_data.get("min_subscribers"),
        max_subscribers=band_data.get("max_subscribers"),
        min_multiplier=float(band_data.get("min_multiplier", 0.3)),
        max_multiplier=float(band_data.get("max_multiplier", 3.0)),
    )
    if (band.min_subscribers is None) != (band.max_subscribers is None):
        raise ScoutError("config.toml: set both size_band.min_subscribers and max_subscribers, or neither")
    if band.is_absolute and band.min_subscribers > band.max_subscribers:
        raise ScoutError("config.toml: size_band.min_subscribers is above max_subscribers")
    if not band.is_absolute and band.min_multiplier > band.max_multiplier:
        raise ScoutError("config.toml: size_band.min_multiplier is above max_multiplier")

    languages = [str(x).lower() for x in data.get("languages", ["en"])]
    if not languages:
        raise ScoutError("config.toml: languages must list at least one language code")

    disc = data.get("discovery", {})
    quota = data.get("quota", {})
    cfg = Config(
        root=root,
        my_channel_id=str(data.get("my_channel_id", "")).strip(),
        size_band=band,
        languages=languages,
        seed_channels=[str(x).strip() for x in data.get("seed_channels", []) if str(x).strip()],
        max_results_per_run=_positive_int(data, "max_results_per_run", 20),
        exclude_channel_ids_file=str(data.get("exclude_channel_ids_file", "")).strip(),
        searches_per_run=_positive_int(disc, "searches_per_run", 8),
        search_window_days=_positive_int(disc, "search_window_days", 14),
        search_results_per_keyword=min(_positive_int(disc, "search_results_per_keyword", 50), 50),
        keyword_count=_positive_int(disc, "keyword_count", 30),
        last_upload_within_days=_positive_int(disc, "last_upload_within_days", 30),
        recent_titles=min(_positive_int(disc, "recent_titles", 5), 50),
        seed_videos=_positive_int(disc, "seed_videos", 3),
        peer_graph=bool(disc.get("peer_graph", True)),
        snowball_frontier_max=_positive_int(disc, "snowball_frontier_max", 10),
        snowball_max_depth=_positive_int(disc, "snowball_max_depth", 2),
        skip_reported_days=_positive_int(disc, "skip_reported_days", 30),
        daily_quota=_positive_int(quota, "daily_quota", 10_000),
        quota_stop_fraction=float(quota.get("stop_fraction", 0.8)),
        retention_days=_positive_int(data, "retention_days", MAX_RETENTION_DAYS),
    )
    if not 0 < cfg.quota_stop_fraction <= 0.8:
        raise ScoutError("config.toml: quota.stop_fraction must be above 0 and at most 0.8")
    if not 1 <= cfg.retention_days <= MAX_RETENTION_DAYS:
        raise ScoutError(f"config.toml: retention_days must be between 1 and {MAX_RETENTION_DAYS}")
    if not band.is_absolute and not cfg.my_channel_id:
        raise ScoutError(
            "config.toml: set my_channel_id (to size the band from your subscriber count) "
            "or both size_band.min_subscribers and size_band.max_subscribers"
        )
    return cfg


def require_env(name: str, hint: str) -> str:
    """An env var's value, or a clear error. No fallbacks."""
    value = os.getenv(name, "").strip()
    if not value:
        raise ScoutError(f"{name} is not set. {hint}")
    return value
