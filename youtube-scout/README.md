# YouTube Scout

Find the YouTube channels behind a topic, narrow them down by size, reach and
activity, and look into any one channel's stats and uploads. A small Python
library: plain functions that return JSON-ready dicts and lists. Nothing is
stored on disk; every search asks YouTube afresh.

> A command-line interface and a Claude Code skill built on it are planned.

## Setup

```bash
cd youtube-scout
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then set YOUTUBE_API_KEY
```

Get a YouTube Data API v3 key from the
[Google Cloud console](https://console.cloud.google.com/apis/credentials).
The key can also come from the environment. Run Python from the `youtube-scout`
folder so `import youtube_scout` works.

## Usage

```python
from youtube_scout import search, filter_channels, sort_channels, get_creator

channels = search("stop motion animation", max_results=200)["channels"]
picked = filter_channels(channels, min_subscribers=1_000, active_within_days=90)
for channel in sort_channels(picked, "channel_score")[:10]:
    print(channel["channel_name"], channel["median_views"], channel["channel_score"])

creator = get_creator("@somehandle")   # or a channel id
print(creator["publish_interval_days"], creator["uploads_by_month"])
```

## Functions

| Function | Returns |
| --- | --- |
| `search(keyword, max_results=1000)` | `{keyword, channels}`: the channels behind the top videos, in relevance order, each with its profile, the `videos` found and the metrics below |
| `filter_channels(channels, *, min_views, max_views, min_subscribers, max_subscribers, active_within_days, min_videos, max_videos, min_score)` | The channels within every given bound (inclusive). Views are median views, videos are total uploads |
| `sort_channels(channels, sort_by="relevance", descending=True)` | The channels sorted by one of `SORT_FIELDS`: `relevance`, `median_views`, `subscriber_count`, `last_published`, `channel_score`, `views_to_subs_ratio`, `likes_to_views_ratio` |
| `get_creator(channel, max_videos=50)` | One channel (id or `@handle`) with metrics over its latest uploads (`videos`, max 50) and `uploads_by_month` for the last six months |

Problems to show the user (missing key, API error, nothing found, bad sort
field) raise `ScoutError`. Timestamps are ISO 8601 strings.

## Metrics

| Field | Meaning |
| --- | --- |
| `median_views`, `average_views` | Typical reach; the median is not skewed by one viral video |
| `median_likes`, `median_comments` | Typical response per video |
| `views_to_subs_ratio` | Median views as % of subscribers |
| `likes_to_views_ratio`, `comments_to_views_ratio` | Engagement, % of median views |
| `avg_duration` | Average video length in seconds |
| `publish_interval_days` | Average days between uploads |
| `last_published`, `days_since_last_published` | Newest video and its age |
| `channel_score` | 0-100: activity 30%, views-to-subscribers 35%, engagement 35% |

## Quota

The YouTube Data API allows 10,000 units a day by default. Search costs 100
units per 50 results, so `max_results=1000` uses about 2,000 units; lower it to
spend less. Video and channel statistics cost 1 unit per 50 items, and
`get_creator` a few units.
