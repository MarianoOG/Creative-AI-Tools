# Video Production

A Claude plugin with one skill, `edit-video`. It turns footage, clips, an HTML
animation or an existing video into finished videos: one long-form (landscape)
and as many short-form (vertical) as you need. Each video is its own
[Shotcut](https://shotcut.org) project, which first says whether it is landscape
or vertical, so you can open it and keep adjusting it. A request produces one
video unless you ask for more:

| | Long-form | Short-form |
| --- | --- | --- |
| Frame | 1920×1080, 16:9 | 1080×1920, 9:16 |
| Made for | YouTube (the default target) | YouTube Shorts |
| Subtitles | Sidecar `.srt` | Burned in |

It renders with `melt` (Shotcut's renderer), checks the result (duration, sound,
black frames, loudness) and puts only the final video files in a `Publish`
folder. It makes the videos only: it never uploads or posts anything.

## What is in the skill

| File | For |
| --- | --- |
| `skills/edit-video/SKILL.md` | The workflow, folder layout and ground rules |
| `skills/edit-video/rough-cut.md` | Raw talking-head or course footage: transcribe, cut, order by story |
| `skills/edit-video/formats.md` | Long-form and short-form specs, subtitles, safe areas, export settings |
| `skills/edit-video/sources.md` | HTML/canvas animations, versions with the same audio, short AI clips |
| `skills/edit-video/mlt-gotchas.md` | Verified Shotcut/MLT details for writing `.mlt` files |

## Requirements

`ffmpeg` and `ffprobe`, Shotcut (its `melt` renderer), Python 3 and Node 22.
Raw-footage transcription uses faster-whisper. The skill installs nothing on its
own and asks first if a step needs something new.

## Install

```bash
claude plugin marketplace add MarianoOG/Creative-AI-Tools
claude plugin install video-production@creative-ai-tools
```
