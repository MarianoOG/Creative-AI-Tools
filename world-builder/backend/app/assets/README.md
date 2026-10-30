# Asset Generation

Four asset types, each rendered by OpenAI (`gpt-image-2`) and Gemini (Nano
Banana 2):

| Type | What it renders | References are treated as |
| --- | --- | --- |
| `character` | Turnaround sheet: front, side, back on white | inspiration |
| `object` | Turnaround sheet: front and side views on white | inspiration |
| `location` | Empty background plate, no figures | inspiration |
| `scene` | Finished composed frame | designs to reproduce faithfully |

- `prompt_manager.py`: prompt text (styles, framing per type, reference clauses). No I/O.
- `generation.py`: provider calls and writing files.
- `library.py`: reading the file tree back as a list of assets.
- `worlds.py`: creating, renaming and deleting worlds, moving assets between them.

The HTTP API is in `app/routers/`. Keys (`OPENAI_API_KEY`, `GEMINI_API_KEY`) go
in `backend/.env`.

## Files and worlds

There is no database: the file tree is the store.

```text
data/
└── <world>/
    ├── characters/
    ├── objects/
    ├── locations/
    └── scenes/
```

Files are named `{name}_{style}_{uuid8}_{provider}`. Every generation gets a new
uuid, so re-rendering keeps earlier attempts. OpenAI writes PNG and Gemini JPEG;
output is 2K.

A scene can only use references from its own world. Assets move between worlds
from the library; a move is refused if the target already has that filename.

## Generating

`POST /assets/generate` waits for the render and returns the saved assets. With
`provider="both"` (what the UI uses) both providers run at once; if one fails,
the other image is still saved and the failure comes back as a `warning`.

- **style**: one of the keys of `STYLES` in `prompt_manager.py`, or none
  ("Follow references") to copy the style from the reference images, which are
  then required.
- **aspect_ratio**: `landscape` (16:9, default), `square`, `portrait` (9:16).
- **quality**: `low` (default), `medium`, `high`. On Gemini only `high` changes
  anything (it sets `thinking_level`).
- **references**: characters, objects and locations take uploads (used for the
  call, never saved); scenes take paths of existing assets.
