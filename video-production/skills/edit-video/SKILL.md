---
name: edit-video
description: "Edits videos into two deliverables from the same material: a horizontal long-form video (mainly YouTube, also LinkedIn or embedded in a website article) and a vertical short-form video (mainly YouTube Shorts, also Instagram Reels and TikTok). Builds a Shotcut project for each, renders it with what's already installed, checks the result and puts the finals in a Publish folder. Starts with a rough cut when the source is raw talking-head or course footage. Use when the user asks to edit, cut, reframe, subtitle, export or make a long or short video from footage, clips, an HTML animation or an existing video. It makes the videos only, not the post texts (captions)."
---

# Edit video

Turn source material into finished videos, with a Shotcut project behind every one so the user can open it and keep adjusting it. This skill makes the videos only; post texts (captions) are out of scope.

Read the file each step names, in this skill's folder:

| File | For |
|---|---|
| `rough-cut.md` | Raw talking-head or course footage: transcribe, cut, order by story, first draft `.mlt` |
| `formats.md` | Long-form and short-form specs, subtitles, safe areas, export settings |
| `sources.md` | HTML/canvas animations, several versions with the same audio, AI clips shorter than their slot |
| `mlt-gotchas.md` | Verified Shotcut/MLT details. Read before writing or editing any `.mlt` |

## Ground rules

- **Install nothing.** Use what's already there: `ffmpeg`/`ffprobe`, the Shotcut snap (`shotcut.melt` renders projects), Node 22, Python 3, and the cached headless Chrome at `~/.cache/puppeteer/chrome-headless-shell/linux-*/chrome-headless-shell-linux64/chrome-headless-shell`. If a step really needs something new (a transcription model, for example), stop and ask first. Never use an unofficial mirror without asking.
- **Never modify or delete the originals.** Move them into the source folder unchanged.
- **Every deliverable has a Shotcut project** (`.mlt`) that renders exactly what was published. Render with melt from that project, never with a separate ffmpeg pipeline the project doesn't reflect.
- **Never overwrite the user's edits.** A new version is a new file (`<project>-long-v2.mlt`). If the Shotcut window has an older copy of a project open, say so: saving it would overwrite the new one.
- **Don't invent facts** in on-screen text, titles or inserts. Ask, or leave an INSERT placeholder that says what goes there and why.
- **Never publish or upload** anything. Posting is the user's job.

## Deliverables

Unless the user asks for only one, every video produces **both**:

| | Long-form | Short-form |
|---|---|---|
| Optimised for | YouTube | YouTube Shorts |
| Also used on | LinkedIn, embedded in a website article (via YouTube) | Instagram Reels, TikTok |
| Frame | 1920×1080, 16:9 | 1080×1920, 9:16 |
| Subtitles | Sidecar `.srt` (burned in only on request) | Burned in, always |
| File | `<project>-long-16x9.mp4` | `<project>-short-9x16.mp4` |

The full specs are in `formats.md`. One short-form file serves all three vertical platforms. Don't make per-platform variants unless the user asks.

**Where the short comes from:** if the source is already short and vertical-friendly, reframe it. If it's long, propose 2–3 candidate moments (start–end, the hook line, why it stands alone) and let the user pick before building it. A short must make sense without the long video.

## Folder layout

Inside the project folder (e.g. `~/Videos/<Project>/`). If the project already has its own layout, keep it and tell the user how it maps to this one.

- `01 Source/`: originals, unchanged. Old exports or other people's cuts go in `01 Source/Old cuts/`.
- `02 Edit/`: one `.mlt` per deliverable and version, the `.srt` files, `Transcripts/` (.txt and .srt per clip) and a short `notes.md`. Variants (motion graphics, comparisons) get a subfolder each.
- `03 Publish/`: **only the final video files.** No `.mlt`, `.srt`, notes or post texts.
- `_claude_scratch/`: anything temporary, deletable at the end.

Shotcut projects use absolute paths. After moving anything, rewrite the paths in every `.mlt` and re-render a few seconds of each project to prove it still finds its files. Never leave renders or projects in the scratchpad: the Shotcut snap can't see `/tmp`.

## Workflow

1. **Look before cutting.** `ffprobe` every source (size, fps, duration, audio, creation time). Make contact sheets (`ffmpeg ... -vf "fps=1/2,scale=320:-2,tile=7x4"`) and actually look at them: where the cuts are, where the subject sits in each shot, what text is already on screen.
2. **Raw footage? Rough cut first.** For talking-head or course footage, follow `rough-cut.md` and get the user's yes on the draft before going on. For an existing edit, an animation or a few finished clips, skip this step.
3. **Get the transcript.** Reuse what exists: the rough cut's transcripts, an `.srt`/`.vtt`, subtitle data in an HTML file, burned-in text or a script. If none exists, ask before transcribing.
4. **Build the long-form project** per `formats.md`, with separate tracks so each layer can change on its own:
   - `V1`: footage
   - `V2`: subtitles, only when burned in
   - `V3`: optional titles, chapter cards and labels
   - `A1`: narration or music

   Export the `.srt` from the final cut, not from the raw transcript.
5. **Build the short-form project** per `formats.md`. Reframe per shot toward the subject, picked from the contact sheet rather than centred by default, and burn in the subtitles.
6. **Place on-screen text per shot, not globally.** For each shot, find the faces, hands, main object and motion, and put text in the empty part inside the safe area. Text over the main action is a bug.
7. **Render with melt** from each project into `03 Publish/`.
8. **Verify each render.** Check the duration against the audio and make a contact sheet with one frame per subtitle at its midpoint. Confirm there's sound (`volumedetect`), the picture isn't black (`signalstats`) and the loudness is near −14 LUFS. Fix and re-render until it passes. Only then report.
9. **Deliver.** Tell the user where each final, project and `.srt` is, plus the open questions (at most 2).
