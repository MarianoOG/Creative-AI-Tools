---
name: foundations
description: "Shared reference for every youtube-scout skill: how to run the bundled yt tool, the API key, the quota budget per skill, and the YouTube data rules. Not used on its own. Load it whenever another youtube-scout skill points here, or when the user asks to change a quota budget or a data rule."
---

This skill holds the facts the other youtube-scout skills share. **Change a rule in `youtube.md`, never in the skill that uses it.**

| File | Answers | Used by |
|---|---|---|
| `youtube.md` | Running `yt`, the API key, quota budget per skill, data rules | youtube-keywords, youtube-next-video, youtube-collaborators, youtube-title-check |

## Standing rules (every youtube-scout skill)

- **Which channel:** use the channel the user gives (`@handle`, URL or `UC…` id). If none is given, use the one the user's own instructions name as theirs (for example in CLAUDE.md or their preferences). If there is none, ask once.
- **Credentials:** never hardcode the API key in a skill, script, file or message.
- **Containment:** these skills reference only skills in this plugin. If the user wants results saved somewhere (a task, a note), hand them over in plain text and let the user's own tools take it from there.
