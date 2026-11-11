# YouTube Scout

A command-line data tool that finds **small YouTube channels, of roughly a given
size, that match a niche you describe**. It is built to run once a day as a
scheduled job and writes one local data file per run. It does not tell you what
to do with the data; it only produces it.

The niche is yours to define: nothing in the code assumes a topic. You describe
your brand or channel and its audience in `brand.txt`, and the tool generates
its own search keywords from that description.

> **This tool uses YouTube API Services.** By using it you agree to be bound by
> the [YouTube Terms of Service](https://www.youtube.com/t/terms), and your use
> of YouTube data is subject to the
> [Google Privacy Policy](https://policies.google.com/privacy). Developers using
> it also accept the
> [YouTube API Services Terms of Service](https://developers.google.com/youtube/terms/api-services-terms-of-service)
> and [Developer Policies](https://developers.google.com/youtube/terms/developer-policies).

## What it does

```
brand.txt ──LLM──▶ keywords.generated.txt
                        │
   ┌────────────────────┼──────────────────────────────┐
   ▼                    ▼                              ▼
fresh uploads      seed channels ──▶ commenters    peer graph: featured channels,
(search.list,      who publish videos              public subscriptions, and
 order=date,       (commentThreads.list)           yesterday's finds (snowball)
 last 14 days)
   └────────────────────┼──────────────────────────────┘
                        ▼
      enrich (channels.list, playlistItems.list) ─▶ filters ─▶ LLM niche fit
                        ▼
              out/YYYY-MM-DD.json + .md   (local, git-ignored)
```

1. **Fresh uploads (primary).** For each keyword, one `search.list` page of
   videos ordered by date and published in the last 14 days, with
   `relevanceLanguage`. This surfaces channels that have only a few videos.
   Searches cost 100 units each, so each run searches only a few keywords
   (`searches_per_run`), the ones searched least recently, with no deep
   pagination.
2. **Keyword variations.** The LLM writes the keywords from `brand.txt`,
   optionally enriched with titles of relevant videos already found and with
   phrases from `peer-scout comments`. No autocomplete or suggest endpoint is
   used.
3. **Seed channels → commenters.** Recent uploads of your `seed_channels`
   (`playlistItems.list`), their top-level commenters (`commentThreads.list`);
   only commenters that turn out to be publishing channels are kept, the rest
   are discarded immediately.
4. **Peer graph.** Featured channels (`channelSections.list`) and public
   subscriptions (`subscriptions.list`; private lists are skipped) of seeds and
   of the snowball frontier.
5. **Snowball.** Channels kept today seed tomorrow's peer graph. The frontier is
   capped (`snowball_frontier_max`) and limited to a few hops from a keyword or
   seed (`snowball_max_depth`) so it does not drift off-niche.

Candidates are then enriched with batched `channels.list` calls (50 ids per
unit) and `playlistItems.list` for recent upload titles and dates, and filtered:

* subscriber count inside the size band (hidden subscriber counts are left out)
* at least one public video, last upload within 30 days (configurable)
* language in `languages`
* not made for kids, and nothing that looks run by a minor (a text check on the
  profile and titles, plus the LLM)
* not your channel, a seed, your exclude list, or a channel reported in the
  last 30 days

Finally the LLM judges niche fit from each channel's description and recent
titles against `brand.txt` and the keywords, and writes one short plain-text
reason per channel. That judgement only orders and trims your local file: it is
never written as a score, rank or metric.

## Setup

Python 3.11 or newer.

```bash
cd youtube-scout
python3 -m venv .venv
source .venv/bin/activate
pip install -e .            # installs the peer-scout command
cp .env.example .env        # then add your keys
cp config.example.toml config.toml
cp brand.example.txt brand.txt
```

Then edit `brand.txt` (describe your brand/channel and its audience) and
`config.toml` (at least `my_channel_id` or an absolute `size_band`).

### Keys

Each user brings their own keys. They are read from the environment or from
the git-ignored `.env`, never from the repository. If one is missing the command
stops with a message naming it; there is no fallback.

| Variable | What for |
| --- | --- |
| `YOUTUBE_API_KEY` | YouTube Data API v3 key from the [Google Cloud console](https://console.cloud.google.com/apis/credentials) |
| `SCOUT_LLM_PROVIDER` | `anthropic` (default) or `openai` |
| `SCOUT_LLM_MODEL` | Optional model override (required for `openai`) |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Key for the chosen provider (`pip install -e .[openai]` for OpenAI) |

### Commit hooks

The repository ships a [pre-commit](https://pre-commit.com) config with
[gitleaks](https://github.com/gitleaks/gitleaks) and a local guard
(`scripts/guard.py`) that blocks API keys, email addresses and every local data
file (`brand.txt`, `config.toml`, `.env`, `out/`, `state/`, …). Install it once
per clone, from the repository root:

```bash
pip install pre-commit
pre-commit install
```

## Usage

```bash
peer-scout run              # today's run; re-running the same day resumes or re-renders it
peer-scout run --force      # redo today's run from scratch
peer-scout keywords         # regenerate keywords.generated.txt from brand.txt
peer-scout comments --video VIDEO_ID ...       # mine questions from these videos
peer-scout comments --channel CHANNEL_ID ...   # ... from these channels' recent uploads
peer-scout comments --latest                   # ... from the channels in the latest run
peer-scout quota            # today's quota use per method
peer-scout purge --yes      # delete every local output and state file
```

Add `-v` for progress logs. `python -m youtube_scout` works too.

### Run it daily

With cron (paths are examples):

```cron
17 6 * * * cd /path/to/youtube-scout && .venv/bin/peer-scout run >> state/cron.log 2>&1
```

Keep it on a machine you control: running it in a public CI service would
publish its logs.

### `peer-scout comments`

Reads top-level comments (`commentThreads.list`, 1 unit per 100 comments),
keeps only comments that are questions or requests ("how do you…", "what
tool…", "can you make…", "¿cómo…"), has the LLM rewrite each as a short
search-style phrase and group the duplicates, and writes
`out/comments-YYYY-MM-DD.txt`:

```
# count<TAB>phrase
4	best clay for claymation
2	stop motion armature how to
```

The next keyword generation reads the latest of these files as extra context
next to `brand.txt`.

## Output

`out/YYYY-MM-DD.json` and `out/YYYY-MM-DD.md` (both git-ignored). For each
channel: title, URL, subscriber count, video count, last upload date, up to 5
recent video titles, the fit reason, and the discovery path (which keyword,
seed or chain found it). The run summary lists quota used per method, the
keywords searched, channels seen vs kept, and how many were left out per filter.

There is no contact information, no email and no outreach suggestion.

## Quota

The default YouTube quota is 10,000 units a day, reset at midnight Pacific
Time. Every call is charged to a per-day ledger (`state/quota-<day>.json`)
**before** it is sent; the tool stops at 80% of the daily quota (configurable
lower, never higher) and still writes what it found. With the defaults a run
uses about 8 × 100 units of search plus a few dozen units of enrichment.

| Method | Units |
| --- | --- |
| `search.list` | 100 per call |
| `channels.list`, `playlistItems.list`, `channelSections.list`, `subscriptions.list` | 1 per call |
| `commentThreads.list` | 1 per page of up to 100 comments |

## Data handling

* **Open source, not data.** The repository holds the code only. `brand.txt`,
  the generated keywords, `config.toml`, `.env`, `out/` and `state/` are
  git-ignored and blocked by the commit hook. Outputs are never published.
* **No contact data.** The tool never collects emails or any contact details.
* **Official API only.** Only `GET` requests to the YouTube Data API v3
  (`googleapis.com/youtube/v3`). No unofficial endpoints, no HTML scraping.
* **Read-only.** It never comments, likes, subscribes or messages.
* **No published scores or rankings.** The fit judgement is a plain-text
  reason in your local file.
* **30-day retention.** Raw API responses are not stored at all. Derived data
  (outputs, run checkpoints, the snowball frontier, the list of channels already
  reported) is deleted after `retention_days` (30 at most) at the start of each
  run; `peer-scout purge --yes` deletes it all at once.
* **Commenters and comments.** Commenter ids exist only in memory during a run;
  those that are not publishing channels are dropped at once and never written.
  `peer-scout comments` sends question text (with @mentions and links removed,
  and no author names or ids) to your LLM provider and writes only the rewritten
  phrases.
* **Minors.** Made-for-kids channels and channels that look run by a minor are
  dropped and only counted; nothing else about them is kept. A run checkpoint
  holds one-way hashes of rejected ids so a resumed run does not look at them
  again.
* **Your LLM provider** receives `brand.txt`, channel descriptions and titles,
  and question text as described above, under that provider's own terms.

## Development

```bash
pip install -e .[dev]
pytest
```

Tests use fixtures in `tests/fixtures/youtube` and a fake LLM; they never call
the network. The fixtures are synthetic data in the API's response shapes:
recording real responses would put third-party data in the repository.

See [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) before tagging a release.
