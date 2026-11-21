---
name: youtube-keywords
description: "Turns a YouTube channel into long-tail YouTube search phrases: reads the channel through the YouTube API, generates seeds, gives a manual autocomplete plan, checks what already ranks, then groups and prioritizes the phrases with video title ideas. Use when the user asks for YouTube keywords, search phrases, topics people search for on YouTube, or how to title a video so it gets found."
---

# YouTube keywords

Goal: find the long, specific phrases a channel's audience types into **YouTube** search. The phrases are used in YouTube titles, descriptions and tags.

Read `youtube-scout:foundations` → `youtube.md` first (running `yt`, quota, data rules) and pick the channel per its standing rules.

## Step 1 — The source channel

`yt channel REF` and `yt uploads REF -n 20`. Read the description and titles. If the user described their audience or direction, that outranks old titles when they disagree.

Write a **source summary** (5 lines max): what the channel makes, for whom, its topics, languages, what's off-topic. The other youtube-scout skills reuse this step. If the channel has almost no videos and no description, ask once what it is about.

## Step 2 — Seeds

8–15 seed phrases per language, mixing:

- Head topics (2–3 words) the audience would recognise
- Audience phrases ("for programmers who draw", "without being an animator"), and buyer phrases if the channel also sells something
- Problem phrases ("how to…", "why does…", "without…")
- Tool and comparison phrases ("X vs Y", "best X for Y")

Mark each seed's intent: learn, compare, solve a problem, get inspired.

## Step 3 — Manual autocomplete plan

The API has no autocomplete, so this part stays by hand. For the 3–5 strongest seeds, give a copy-friendly checklist:

1. **Alphabet soup:** `seed a` … `seed z` (and `seed 1`…`seed 9` if relevant).
2. **Wildcards and question prefixes:** `how to * seed`, `seed vs *`, `why seed`, `best seed for`, `seed for beginners`, `seed without`, `seed <current year>`; Spanish: `cómo * seed`, `por qué seed`, `qué es seed`, `mejor seed para`, `seed para principiantes`, `seed sin`.
3. **Desktop and mobile:** suggestions differ.

The user pastes back what they saw. From it, pick 3–5 new phrases as the next round; 2–3 rounds at most, stop when suggestions repeat. If they'd rather skip this step, go on with the seeds.

## Step 4 — What already ranks (API, capped)

For the **5 most promising phrases at most** (100 units each), run `yt search "phrase" -n 20`, then `yt channels` on the channel ids and `yt videos` on the video ids (1 unit each). Note per phrase, as facts:

- How many results come from channels near the source's size vs much bigger ones
- How recent the results are
- Whether small channels get views well above their subscriber count

Then one plain sentence: **room** (small channels and older videos rank), **crowded** (big channels with recent videos) or **unclear**. API results aren't personalized and may differ from what the user sees; say so once.

## Step 5 — Group and prioritize

- Remove duplicates and near-duplicates; group by meaning, short group names.
- 1–3 video title ideas per group.
- Best first: specific phrases of 4+ words with a clear intent, phrases from real autocomplete before invented ones, "room" before "crowded".
- Everything is a hypothesis until the user checks it.

## Step 6 — Before choosing (always include)

- **vidIQ or TubeBuddy (free tiers)** for search volume and competition; TubeBuddy's weighted score adjusts to channel size.
- **Google Trends** with "YouTube Search" selected: seasonality, two phrasings side by side.
- **YouTube Studio** → Research, if available.
- For a single title, `youtube-scout:youtube-title-check` goes deeper.

## Output

- A plain list, one phrase per line, under `# group name` lines, best first.
- A table: group, phrase, intent, source (autocomplete / generated), ranks (room / crowded / unclear / not checked), title ideas.
- Units used.

## Rules

- Never claim search volume or difficulty numbers. Only the user's own checks and the facts from Step 4 count.
- Never scrape YouTube or call autocomplete endpoints; searches only through `yt`, within the cap.
- Short, copy-friendly output; data and the ranking facts, no advice beyond them.
