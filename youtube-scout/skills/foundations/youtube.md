# YouTube

How the youtube-scout skills reach YouTube, what it costs, and what they may keep.

## Running `yt`

Every skill uses `yt`, a small read-only tool for the official YouTube Data API v3. It ships with this plugin as `yt.py` at the plugin root (two folders above this file's folder: `skills/foundations/` → plugin root). Each command prints JSON; units used go to stderr.

- If the `yt` command is on the PATH, use it.
- Otherwise run `python3 <plugin root>/yt.py …` (Python 3.10+, no dependencies), or install it once: `pip install "git+https://github.com/MarianoOG/Creative-AI-Tools#subdirectory=youtube-scout"`.
- **Key:** `YOUTUBE_API_KEY`, from the environment or a `.env` file next to `yt.py`. If it is missing, stop and say so. Never ask for it in chat, never write it in a file.

| Command | Gives | Units |
|---|---|---|
| `yt channel REF` | Profile and stats (REF = `@handle`, `UC…` id or channel URL) | 1 |
| `yt uploads REF -n 15` | Latest videos with views, likes, comment counts | 3 |
| `yt videos ID…` / `yt channels ID…` | Many videos / channels at once | 1 per 50 |
| `yt search "phrase" [--days N] [--lang es] [--order date] -n 20` | Videos for a phrase | **100** |
| `yt creators "phrase" [same options]` | The channels behind that search | **101** |
| `yt comments VIDEO_ID -n 100` | Comments: text, link, likes, replies (no author names) | 1 per 100 |
| `yt featured REF` | Channels it lists on its page (Featured channels) | 1 |
| `yt subscriptions REF` | Channels it follows, only if public | 1 |
| `yt band MIN MAX < channels.json` | Keep channels in a subscriber range, with videos, not made for kids | 0 |

## Quota

The API is free. A project gets **10,000 units a day** by default (resets at midnight Pacific time). A search costs 100 units, almost everything else 1–3, so the budget is about searches.

| Skill | Default budget | Mostly |
|---|---|---|
| youtube-keywords | ≤ 510 | up to 5 searches to check what ranks |
| youtube-next-video | ≤ 520 | up to 5 searches + comments on ~10 videos |
| youtube-collaborators | ≤ 520 | up to 4 creator searches + uploads of the shortlist |
| youtube-title-check | ≤ 320 | up to 3 phrasings |

Every skill states its units before starting and reports the units used at the end. Going over a budget needs the user's yes.

## Data rules

- **Official API only, read-only.** Never post, comment, like or subscribe. Never scrape youtube.com or call autocomplete/suggest endpoints (they aren't part of the API).
- **Comments:** quote or summarize them in the answer, with their links so the user can reply by hand later. Never collect author names, emails or any contact details.
- **30 days:** YouTube data must not be kept more than 30 days without refreshing it. Anything saved keeps the idea **in the user's own words** plus links. Refresh before relying on it later (for comments, re-run `yt comments` on that video).
- **No scores.** Report facts (subscribers, views, dates) and a plain-language reason, never a made-up score or rank.
