# YouTube Scout

Small, read-only tools for the YouTube Data API v3, in one file:
[`yt.py`](yt.py). Each tool makes one kind of API call and prints JSON, so you
can read it, pipe it, or let an agent or a Claude session call it. Nothing is
saved to disk and there is no scoring: the tools fetch data, and you (or Claude)
decide what it means.

This tool uses YouTube API Services: see the
[YouTube Terms of Service](https://www.youtube.com/t/terms) and the
[Google Privacy Policy](https://policies.google.com/privacy).

## Setup

Python 3.10+, no other dependencies.

```bash
cd youtube-scout
cp .env.example .env   # then add your YOUTUBE_API_KEY
```

Get a key from the [Google Cloud console](https://console.cloud.google.com/apis/credentials)
(enable "YouTube Data API v3"). The key can also come from the environment.

Run it as `python yt.py ...`, or install the `yt` command anywhere:

```bash
pip install "git+https://github.com/MarianoOG/Creative-AI-Tools#subdirectory=youtube-scout"
```

## Tools

| Command | Returns | Quota units |
| --- | --- | --- |
| `yt channel REF` | A channel's profile and stats (`REF` = `UC…` id, `@handle` or channel URL) | 1 |
| `yt uploads REF -n 10` | Its latest videos, newest first, with views, likes, comments | 3 |
| `yt videos ID…` | Stats and details for given videos | 1 per 50 |
| `yt channels ID…` | Profiles and stats for given channel ids | 1 per 50 |
| `yt search "QUERY" [--days 14] [--lang es] [--order date] [--region MX] [-n 25]` | Videos for a query (one page, up to 50) | 100 |
| `yt creators "QUERY" [same options]` | The channels behind that search, with the titles they matched | 101 |
| `yt comments VIDEO_ID -n 100` | Top-level comments: text, a link to each comment, likes, reply count (no author names or ids) | 1 per 100 |
| `yt featured REF` | Channel ids the channel features on its page | 1 (+1 for a handle) |
| `yt subscriptions REF` | Channel ids it subscribes to, if the list is public | 1 (+1 for a handle) |
| `yt band MIN MAX < channels.json` | Channels with MIN–MAX subscribers, videos, not made for kids | 0 |

Units used are printed to stderr after each command. The default quota is
10,000 units a day; `search` and `creators` are the expensive ones.

## Examples

```bash
# What does a channel make lately?
python yt.py uploads @somehandle -n 15

# Small creators who posted about a topic in the last two weeks
python yt.py creators "stop motion tutorial" --days 14 > creators.json
python yt.py band 300 3000 < creators.json

# What are viewers asking under a video?
python yt.py comments dQw4w9WgXcQ -n 200
```

From Python:

```python
import yt

me = yt.channel("@somehandle")
peers = yt.band(yt.creators("stop motion", days=14), me["subscribers"] // 3, me["subscribers"] * 3)
```

## Rules

- Official YouTube Data API only, `GET` requests only: it never posts, likes,
  subscribes or comments.
- Your key stays in `.env` or the environment, never in the repo.
- Nothing is written to disk. Comments come back without author names or ids,
  but with a link, so you can go back and reply by hand. If you save results,
  don't commit them, and refresh or delete YouTube data within 30 days.

## Tests

```bash
pip install pytest && pytest
```

The API is faked in the tests; they never call the network.
