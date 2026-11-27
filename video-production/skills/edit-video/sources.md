# Special sources

- **HTML/canvas animation** (motion graphics made as code):
  1. Open it in the installed headless Chrome over CDP, using Node 22's built-in `WebSocket`.
  2. Set the viewport to the target size with `deviceScaleFactor: 1` and wait for fonts.
  3. Step time frame by frame, in order. Look for a still-frame hook like `window.NR.at(t)`; otherwise drive its clock.
  4. Pipe `canvas.toDataURL()` PNGs into `ffmpeg -f image2pipe`. Capture the canvas, not a screenshot, so player controls don't show.
  5. Extract any embedded audio and mux it with `-c:a copy`.

  Render once per kind (frame sizes in `formats.md`) rather than cropping one into the other when the layout allows it.
- **Several versions with the same audio:** compare `silencedetect` timings to confirm the audio is shared. A stacked comparison works in vertical: three 1080×608 rows with 24 px gaps, a label in each row's top-left and a single shared audio track. Comparison projects live in `02 Edit/`, never in Publish.
- **AI-generated clips shorter than their narration slot:** slow them with a timewarp producer (`speed = source length ÷ slot`), with the narration audio muted on the clips.
