# Shotcut / MLT gotchas (verified)

## Producers and cuts

- Producers use `in="0" out="length-1"`. Cut points go ONLY on `<entry in out>`; otherwise the in-point is applied twice. Use frames at the real fps (e.g. 60000/1001).
- Set `mlt_service avformat-novalidate`, `shotcut:caption` (clip name) and `shotcut:comment` (why it was cut).
- Timewarp producer: `resource="<speed>:<path>"`, `mlt_service=timewarp`, `warp_speed`, `warp_resource`, `warp_pitch=0`.
- Cards and inserts are a `color` producer (`#AARRGGBB`) plus text filters.

## Tracks and transitions

- Give every video track a `frei0r.cairoblend` transition to the background with `disable=0`, plus a `mix` transition for audio.
- Markers: tractor `<properties name="shotcut:markers">` with text, start, end (clock) and color.

## Filters

- **Text: Simple** is `dynamictext` with `shotcut:filter dynamicText` and `shotcut:usePointSize 0`. Fade it with an animated `opacity` (`"0=0;12=1;…"`).
- `dynamictext` treats `#` as a keyword marker, so avoid `#` in on-screen text. Real newlines work for line breaks.
- **Size, Position & Rotate** (`affine`): do **not** set `transition.invert_scale=1`, because it renders black. Use `transition.fill=1` and `transition.distort=0`, with keyframes as `HH:MM:SS.mmm~=x y w h 1`.

## Audio

- Track filters:
  - `rnnoise` (track-only, `mix`)
  - High Pass `ladspa.1890`
  - Low Pass `ladspa.1891`
  - Parametric EQ `ladspa.1204` (`parametricEq`)
  - Noise Gate `ladspa.1410`
  - Compressor `ladspa.1882`
- Normalize, One Pass: `dynamic_loudness` on the tractor.
- **Normalize and compressor makeup gain also raise the noise in pauses.** Keep max_gain low (≤6 dB), with little compressor makeup.

## Testing

- To test a project without the real media: run melt with xvfb on fake media (`testsrc2` with the same names and durations, in mkv/mpeg4; the mp4/x264 path crashes there). Check frame numbers on 2–3 source timecodes.
- After moving files, re-render a few seconds of each project to prove the paths still resolve.
