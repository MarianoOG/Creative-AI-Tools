---
name: youtube-next-video
description: "Recommends what video to make next for a YouTube channel: finds its topics, searches recent videos on them, reads their comments, and turns what viewers ask, request and complain about into 3–5 video ideas, each with evidence and links to the original comments so the user can answer them after publishing. Use when the user asks what to make next, for video ideas from comments, or what viewers in a niche are asking for."
---

# YouTube: what to make next

Read `youtube-scout:foundations` → `youtube.md` (running `yt`, quota, data rules) first and pick the channel per its standing rules. Budget: **≤ 520 units**. Say the estimate before starting.

## Step 1 — Source and topics

Run Step 1 of `youtube-scout:youtube-keywords` (source summary). Pick **3–5 topics** from it, as YouTube search phrases. If the user gave topics, use those. Show the topics in one line and continue unless they object.

## Step 2 — Recent videos per topic

For each topic: `yt search "topic" --days 60 -n 20` (100 units; add `--lang es` for Spanish topics). Then `yt videos` on all the video ids together (1 unit per 50).

Pick **about 10 videos** across topics with the most comments relative to their views, preferring channels near the source's size. Skip the source channel's own videos unless asked.

## Step 3 — Comments

`yt comments VIDEO_ID -n 100` on each picked video (1 unit each). Keep comments that are:

- **Questions** ("how do you…", "what tool…", "¿cómo…")
- **Requests** ("can you make…", "please do one on…")
- **Pain points** ("I always get stuck at…", "this never works for me")

Ignore praise, spam and personal remarks. Never note author names.

## Step 4 — Group into ideas

Group similar comments into needs. A need asked under several videos or channels beats one asked once. For each need, write a **video idea**:

- **Idea:** working title (2–3 options, using the phrases viewers used)
- **Why:** the need in one sentence, and how many comments across how many videos asked it
- **Evidence:** 2–5 comment links (`url` from `yt comments`) with a short quote each, plus the video they're under
- **Gap:** whether the source channel already covered it (check its titles from Step 1)

3–5 ideas, best first: most asked, not yet covered, fits the source summary.

## Output

1. The source summary and topics (short)
2. The ideas, as above
3. An **answer list**: every comment link used, grouped by idea, so after publishing the user can reply by hand with the new video
4. Units used

## Rules

- Never post replies or comments; the user answers by hand.
- If the user wants an idea saved, give it as the idea in their own words plus the links, never copied comment text (30-day rule in `youtube.md`). Before replying weeks later, refresh with `yt comments` on that video.
- Evidence only from comments actually read; never invent demand.
