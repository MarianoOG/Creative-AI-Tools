"""YouTube Scout: research YouTube channels for creative inspiration.

    from youtube_scout import search, filter_channels, sort_channels, get_creator

    channels = search("stop motion animation")["channels"]
    top = sort_channels(filter_channels(channels, min_subscribers=1_000), "channel_score")[:10]
    creator = get_creator(top[0]["channel_id"])
"""

from .scout import SORT_FIELDS, filter_channels, get_creator, search, sort_channels
from .youtube_api import ScoutError

__all__ = ["SORT_FIELDS", "ScoutError", "filter_channels", "get_creator", "search", "sort_channels"]
