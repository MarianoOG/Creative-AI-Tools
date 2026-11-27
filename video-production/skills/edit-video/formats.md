# Formats

A project is one video, and it first says whether it is **landscape (long-form)** or **vertical (short-form)**. Each has its own rules below. A source gives one long-form video and as many short-form videos as needed, each its own Shotcut project.

Assume YouTube is the target: long-form on YouTube, short-form on YouTube Shorts. If the user directs another platform or another way of editing, follow that.

| | Long-form | Short-form |
|---|---|---|
| Optimised for | YouTube | YouTube Shorts |
| Also used on | LinkedIn, website articles (embedded from YouTube) | Instagram Reels, TikTok |
| Frame | 1920×1080, 16:9 | 1080×1920, 9:16 |
| Length | Whatever the story needs. YouTube chapters for anything over ~3 min | Aim for under 60 s. Hook in the first 1–2 s |
| Subtitles | **Sidecar `.srt`** by default, burned in only on request | **Burned in**, always |
| Safe area | Text inside the inner 90% (title-safe). Lower-thirds sit above the bottom 10% | Keep text and key action out of the top 12% (≈230 px), the bottom 22% (≈420 px) and the right 120 px. These cover the UI of Shorts, Reels and TikTok, so one file works on all three |
| Subtitle style | Lato 48–56 px, white with outline, bottom-centre, max 2 lines, ~42 characters per line | Lato Heavy ~66 px, white, 3 px black outline, on a ~55% black box. Max 3 lines, ~22 characters per line |
| Pace | Let it breathe | One idea per subtitle line. Change shot or framing every 2–6 s |
| Ending | Can close with a call to action card | Ends cleanly; a loop back to the hook works well |

## Long-form notes

- **Chapters:** a long-form video has chapters. Mark them in the project with Shotcut markers (one colour, the chapter title as the marker text) and in the output with a chapter title card on `V3`.
- **Thumbnail:** keep the candidates inside the project: a marker named "Thumbnail", in its own colour, on each candidate frame (2–3). Export a 1280×720 PNG of one only if the user asks.
- **Other platforms:** LinkedIn and website embeds use the same file. Edit differently only when the user directs it.

## Short-form notes

- To reframe 16:9 into 9:16, scale to full height and keyframe a slow pan per shot toward the subject.
- Subtitles go on their own track: one transparent colour clip per line with a "Text: Simple" (`dynamictext`) filter.
- Hooks and labels go on `V3` so they can be muted.
- Hide audio on the video tracks unless it's wanted.

## Export settings (both)

- H.264, `crf=18`, `preset=slow`, `pix_fmt=yuv420p`
- AAC 192 kbps at 48 kHz, `movflags=+faststart`
- 30 fps, unless the source is 24/25/60 and should stay that way
- About −14 LUFS integrated. Check with `ffmpeg -af loudnorm=print_format=summary` and correct only if it's far off.
