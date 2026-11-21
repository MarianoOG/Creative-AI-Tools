---
name: youtube-title-check
description: "Checks a planned YouTube video title (or search phrase) against what already ranks on YouTube: who ranks, how big and how recent they are, and whether a channel of a given size has room; then suggests and optionally checks up to two alternative phrasings. Use when the user has a title or topic for a video and asks if it can get found, whether to use it, or for a better title."
---

# YouTube title check

Read `youtube-scout:foundations` → `youtube.md` (running `yt`, quota, data rules) first and pick the channel per its standing rules. Budget: **≤ 320 units** (up to 3 phrasings). Say the estimate before starting.

## Inputs

- **The title** (or the phrase the video should rank for). Required.
- **Channel** to judge size against. `yt channel REF` (1 unit) for its subscribers.
- Language, if not obvious from the title.

## Step 1 — The search phrase

A title isn't always what people type. Turn it into the **search phrase** it should rank for (usually its core 3–6 words), and show both. If the title has no searchable phrase at all (pure curiosity title), say so and suggest pairing it with a phrase in the description and the first line.

## Step 2 — What ranks

1. `yt search "phrase" -n 20` (100 units; `--lang es` for Spanish)
2. `yt videos` on the video ids and `yt channels` on the channel ids (1 unit each)

Report as facts, in a small table of the top 10: title, channel, subscribers, views, published.

Then summarize:

- **Size:** how many of the top 10 come from channels within 3× of the source's size, and how many from much bigger channels
- **Age:** how many are older than a year (old results mean room for a fresh one)
- **Over-performers:** small channels with views well above their subscribers (proof a small channel can win here)
- **Match:** do the results answer the same intent as the planned video, or something else?

Verdict in one sentence: **room**, **crowded** or **unclear**, and why. API results aren't personalized and may differ from what the user sees in the app; say so once.

## Step 3 — Alternatives

If the verdict isn't "room", suggest 2–3 alternative phrasings: more specific (4+ words), a different angle, or the other language. Ask before checking them; each costs ~102 units, 2 at most per run. Check the ones the user picks with Step 2.

## Output

- Search phrase and verdict first, one line each
- The table and the four facts
- Alternatives (checked or not), each with its verdict
- A final title suggestion: the phrase people search, plus the user's hook
- Units used

## Rules

- Never claim search volume; for that, point to vidIQ, TubeBuddy or Google Trends (YouTube Search).
- Facts and a plain verdict only, no scores.
