# Video Production

A Claude plugin with one skill, `edit-video`. It turns footage, clips, an HTML
animation or an existing video into finished videos: one long-form (landscape)
and as many short-form (vertical) as you need. Each video is its own
[Shotcut](https://shotcut.org) project, which first says whether it is landscape
or vertical, so you can open it and keep adjusting it. A request produces one
video unless you ask for more.

YouTube is the default target. The skill renders with `melt` (Shotcut's
renderer), checks the result (duration, sound, black frames, loudness) and puts
only the final video files in a `Publish` folder. It makes the videos only: it
never uploads or posts anything.

The workflow, the files it reads and the tools it needs are in
[`skills/edit-video/SKILL.md`](skills/edit-video/SKILL.md).

## Install

```bash
claude plugin marketplace add MarianoOG/Creative-AI-Tools
claude plugin install video-production@creative-ai-tools
```
