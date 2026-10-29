"""YouTube Scout - research YouTube channels and videos for creative inspiration.

Every function takes plain arguments and returns JSON-serializable dicts and
lists (timestamps are ISO 8601 strings). See the README for the record shapes.

    from youtube_scout import search, get_channels, get_creator

    result = search("stop motion animation")
    top = get_channels(result["id"], min_subscribers=1_000, sort_by="channel_score", limit=10)
    creator = get_creator(top[0]["channel_id"], search_id=result["id"])
"""

from .channels import SORT_FIELDS, filter_channels, sort_channels, uploads_by_month
from .config import ScoutError
from .metrics import compute_metrics
from .scout import get_channels, get_creator, search
from .store import find_search, list_searches, load_search
from .youtube_api import YouTubeClient

__all__ = [
    "SORT_FIELDS",
    "ScoutError",
    "YouTubeClient",
    "compute_metrics",
    "filter_channels",
    "find_search",
    "get_channels",
    "get_creator",
    "list_searches",
    "load_search",
    "search",
    "sort_channels",
    "uploads_by_month",
]
