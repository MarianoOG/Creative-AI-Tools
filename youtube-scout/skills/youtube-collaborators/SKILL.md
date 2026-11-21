---
name: youtube-collaborators
description: "Finds YouTube channels of a similar size in the same topics as a given channel, checks they are active, and lists 5–10 possible collaborators with why each fits and one collaboration idea. Use when the user asks for collaborators, peer channels, channels like theirs or someone else's, or creators in a subscriber range."
---

# YouTube collaborators

Read `youtube-scout:foundations` → `youtube.md` (running `yt`, quota, data rules) first and pick the channel per its standing rules. Budget: **≤ 520 units**. Say the estimate before starting.

## Step 1 — Source, size band, topics

- Source summary: Step 1 of `youtube-scout:youtube-keywords` for the channel.
- **Size band:** default **0.3× to 3×** the source's subscribers (`yt channel REF`). A very small channel (under ~300) uses 100–3,000 instead. The user can give their own range.
- **Topics:** 3–4 search phrases from the source summary, or the ones the user gives.

Show band and topics in one line and continue unless they object.

## Step 2 — Find creators

For each topic: `yt creators "topic" --days 90 -n 50 > topic.json` (101 units), then `yt band MIN MAX < topic.json`. Merge across topics; a channel found under several topics is a stronger fit. Drop the source channel.

## Step 3 — Check the shortlist

Take up to **10** channels, preferring those found under more topics. For each: `yt uploads UC… -n 5` (3 units). Drop channels with no upload in the last 60 days, and any that look run by a minor or aimed at children.

Optional, if the list is thin: `yt featured UC…` (1 unit) on the 2–3 best fits. Featured channels are the creators a channel lists on its own page, usually friends or peers, so they're good leads. Check them with `yt channels` and `yt band`, then Step 3.

## Step 4 — Output

5–10 channels, best fit first, each with:

- Title and link, subscribers, videos, last upload date
- 2–3 recent titles
- **Why it fits:** one sentence, naming the shared topics and audience
- **Collab idea:** one concrete idea that fits both channels
- Found via: which topic(s), or featured by whom

Then units used.

## Rules

- No contact details: no emails, no links from "About" pages, no social handles. The user reaches out by hand.
- No scores or rankings beyond "best fit first"; the reason is in words.
- If the user saves channels, the 30-day rule in `youtube.md` applies: refresh with `yt channel` before reaching out weeks later.
