# YouTube Scout

Research YouTube channels and videos for creative inspiration.

Search a topic, see which channels make the videos YouTube surfaces for it,
narrow them down by size, reach and activity, and dig into any one channel's
stats and upload history. YouTube Scout is a small Python package: plain
functions that take simple arguments and return JSON-ready dicts and lists.

> A command-line interface and a Claude Code skill built on these functions are
> planned.

## Setup

YouTube Scout has its own virtual environment:

```bash
cd youtube-scout
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then set YOUTUBE_API_KEY
```

Get a YouTube Data API v3 key from the
[Google Cloud console](https://console.cloud.google.com/apis/credentials).

| Variable | Purpose |
| --- | --- |
| `YOUTUBE_API_KEY` | Required for anything that calls YouTube |
| `YOUTUBE_SCOUT_DATA_DIR` | Where saved searches live (default `youtube-scout/data/`) |

Both are read from the environment; `youtube-scout/.env` is loaded if present.
Run Python from the `youtube-scout` folder (or put it on `PYTHONPATH`) so
`import youtube_scout` resolves.

## Usage

```python
from youtube_scout import search, list_searches, get_channels, get_creator

result = search("stop motion animation")          # spends quota once, then cached
print(result["id"], len(result["channels"]))

top = get_channels(
    result["id"],
    min_subscribers=1_000,
    max_subscribers=100_000,
    active_within_days=90,
    sort_by="channel_score",
    limit=10,
)
for channel in top:
    print(channel["channel_name"], channel["median_views"], channel["channel_score"])

creator = get_creator(top[0]["channel_id"], search_id=result["id"])
print(creator["publish_interval_days"], creator["uploads_by_month"])

get_creator("@somehandle")                        # any channel, no search needed
```

## Functions

| Function | What it does | Quota |
| --- | --- | --- |
| `search(keyword, *, max_results=1000, use_cache=True)` | Searches videos, groups them by channel, computes metrics and saves the result. Returns the newest saved search for the same keyword instead when `use_cache` is on | Yes, unless cached |
| `list_searches()` | Saved searches, newest first: `id`, `keyword`, `created_at`, `count` | No |
| `load_search(search_id)` / `find_search(keyword)` | One saved search with all its channels | No |
| `get_channels(search_id, *, sort_by, descending, limit, ...filters)` | A saved search's channels, filtered and sorted | No |
| `get_creator(channel, *, search_id=None, max_videos=50)` | One channel's stats, metrics, latest uploads and uploads per month | A few units |
| `filter_channels(channels, ...)` / `sort_channels(channels, sort_by, descending)` | The same filtering and sorting on any list of channel records | No |
| `compute_metrics(channel)` | (Re)computes the metrics below from a channel's `videos` | No |

Filters (all optional, inclusive): `min_views` / `max_views` (median views),
`min_subscribers` / `max_subscribers`, `active_within_days`,
`min_videos` / `max_videos` (total uploads), `min_score`.
`sort_by` is one of `SORT_FIELDS`: `relevance` (search order), `median_views`,
`subscriber_count`, `last_published`, `channel_score`, `views_to_subs_ratio`,
`likes_to_views_ratio`.

Errors worth showing to a user (missing key, API failure, unknown search or
channel) raise `ScoutError`. `YouTubeClient` wraps the API calls and can be
passed in as `client=` to any function that calls YouTube.

A channel record holds its profile (`channel_name`, `channel_url`,
`subscriber_count`, `total_videos`, `country`, `created_at`, ...), its
`videos` (title, url, views, likes, comments, duration, published date) and the
metrics. Timestamps are ISO 8601 strings.

## Metrics

Computed over the channel's videos: the ones the search found, or its latest
uploads when a creator is fetched without a search.

| Metric | Field | Why it matters |
| --- | --- | --- |
| Median views | `median_views` | Typical reach, not skewed by one viral video |
| Views-to-subscribers | `views_to_subs_ratio` | How much of the audience a video actually reaches (%) |
| Publish frequency | `publish_interval_days` | Average days between uploads; how consistent the channel is |
| Engagement rate | `likes_to_views_ratio`, `comments_to_views_ratio` | How strongly the audience responds (%) |
| Channel score | `channel_score` | 0-100: activity 30%, views-to-subscribers 35%, engagement 35% |

Also included: `average_views`, `median_likes`, `median_comments`,
`avg_duration` (seconds), `last_published`, and at read time
`days_since_last_published`.

## Saved searches

Each search is saved as one JSON file under `<data dir>/searches/`, so
filtering, sorting and reopening it later cost no quota. Files saved by the
former web app (`data/youtube/searches/`) use the same format: copy them into
`youtube-scout/data/searches/` to keep them; they are brought up to date when
loaded.

## Quota

The YouTube Data API allows 10,000 units a day by default. Each page of 50
search results costs 100 units, so a full search (`max_results=1000`, about 20
pages) can use around 2,000 units; lower `max_results` to spend less. Fetching
video and channel statistics costs 1 unit per 50 items, and `get_creator` a
few units. Reuse saved searches instead of searching the same keyword again.
