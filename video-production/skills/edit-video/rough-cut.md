# Rough cut from raw footage

For raw talking-head or course footage. Goal: a first-draft Shotcut project the user can open and keep editing. It becomes the base of the long-form video, and the short is cut from it.

## 0. Before touching anything (ask in one message)

- **Who is the video for, and what should they be able to do afterwards?** The audience decides the story order. Don't build in recording order first.
- Which files are the originals (base quality) and which are old exports or someone else's cuts.
- Shotcut version (Help > About). RNNoise needs 26.06 or newer.
- If a tool or model can't be downloaded (for example, the network allowlist blocks Hugging Face), **ask** before using any unofficial mirror. The user can put the model file in the folder, run the step locally or allow the domain.

## 1. Organise the folder

Use the layout in `SKILL.md`. Originals go to `01 Source/`, moved and unchanged, and old cuts go to `01 Source/Old cuts/`. Transcripts go to `02 Edit/Transcripts/`, scratch to `_claude_scratch/`.

## 2. Analyse (cheap first)

- `ffprobe` every clip: duration, fps, resolution, audio, `creation_time` (recording order). Use EXIF times to place photos.
- Extract 16 kHz mono FLAC into `_claude_scratch/audio/`, then transcribe with faster-whisper (language set, word timestamps).
- If old exports exist, transcribe ONE first to see what they are (a separate voice-over, for example) before any audio matching.
- One contact sheet per chapter (`-skip_frame nokey`, `fps=1/4,scale=256:-1,tile=6x8`). **Look at it before writing titles or inserts**: on-screen text and visible materials must not be repeated in titles.
- Skip motion analysis (handheld footage makes it meaningless) and audio cross-correlation.

## 3. Story

- Outline the story from the transcripts: explainer style, 3 acts, one question per chapter. The chapter title is the question, the footage is the demonstration and the speaker gives the answer.
- Open with the end result (hook) and come back to it at the end.
- Where a beat is missing and can't be re-recorded, add an INSERT placeholder that says what goes there and why. Don't create the content.
- While outlining, note 2–3 moments that could stand alone as the short.
- Get a yes on the outline before building.

## 4. Cutting rules

- Trim silences over 1.2 s, keeping 0.25 s before and 0.35 s after speech. Keep silent stretches of 4 s or more as demos, and don't speed them up.
- Retakes: keep the last complete take. The other goes to the Playlist as ALTERNATIVA.
- Remove chatter with the camera person and setup talk. Trim oral bridges that point to things that no longer come before them ("otra opción…").
- Everything removed goes to the Playlist (`main_bin`) with the reason. Never just drop it.
- Markers: few, only for chapters, inserts and demos. No 'perdón' flags.
- Audio chain and markers: see `mlt-gotchas.md`.

## 5. Audio check

Render about 30 s of cleaned audio and have the user listen before calling it done. Numbers (SNR) aren't enough: "understandable but unnatural" is the usual result.

## 6. Hand back

Save a new file per version (`<project>-rough-vN.mlt`) and add to `notes.md`: the outline table, pending inserts, the audio chain settings, the candidate short moments and the open decisions. Once the user approves the draft, continue with step 3 of `SKILL.md`.
