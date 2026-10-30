# Worlds, assets and stories

Four kinds of image, each rendered by OpenAI (`gpt-image-2`) and Gemini (Nano
Banana 2), always in the world's style:

| Type | What it renders | References are treated as |
| --- | --- | --- |
| `character` | Turnaround sheet: front, side, back on white | inspiration (uploads) |
| `object` | Turnaround sheet: front and side views on white | inspiration (uploads) |
| `location` | Empty background plate, no figures | inspiration (uploads) |
| `shot` | Finished storyboard frame | designs to reproduce faithfully (the scene's assets) |

- `prompt_manager.py`: prompt text (style presets, framing per type, reference clauses). No I/O.
- `generation.py`: provider calls and writing files.
- `library.py`: reading the file tree back as a list of assets.
- `worlds.py`: creating, renaming and deleting worlds, their `style.txt`, moving assets between them.
- `story.py`: episodes, scenes, shots and `script.json`.

The HTTP API is in `app/routers/`. Keys (`OPENAI_API_KEY`, `GEMINI_API_KEY`) go
in `backend/.env`.

## Files

There is no database: the file tree is the store, and the folders are the story structure.

```text
data/assets/
└── <world>/
    ├── style.txt                 the visual style of every image in the world
    ├── characters/
    ├── locations/
    ├── objects/
    └── episodes/
        └── <episode>/
            ├── script.json       title, synopsis, and every scene's text
            └── <scene>/          the scene's shot images
```

Files are named `{name}_{uuid8}_{provider}`; a shot's name is its id in the
script. Every generation gets a new uuid, so re-rendering keeps earlier takes.
OpenAI writes PNG and Gemini JPEG; output is 2K. Older files carry a style slot
(`{name}_{style}_{uuid8}_{provider}`) and still parse.

Assets move between worlds from the World page; a move is refused if the target
already has that filename. Shots never move.

## script.json

Folders decide which episodes and scenes exist; the script decides their order
and words. A scene folder missing from the script reads as an empty scene, and a
scene entry without a folder is dropped on the next save.

```json
{
  "title": "The Lantern",
  "synopsis": "A fox arrives at a night market...",
  "scenes": [{
    "id": "scene1",
    "heading": "EXT. NIGHT MARKET - NIGHT",
    "summary": "What happens in the scene.",
    "characters": ["fox_hero"], "locations": ["night_market"], "objects": ["brass_lantern"],
    "shots": [{
      "id": "market_night",
      "action": "The fox walks down the wet street, lantern raised.",
      "dialogue": [{"character": "fox_hero", "line": "Hello? Anyone still open?"}]
    }]
  }]
}
```

`characters`, `locations` and `objects` hold asset names (the `{name}` part of
their files). A shot's frames are the images in its scene folder named after its
`id`; images no shot claims are shown as unlinked.

## Generating

`POST /assets/generate` (characters, objects, locations) and
`POST /worlds/{world}/episodes/{episode}/scenes/{scene}/shots/{shot}/generate`
wait for the render and return the saved images. With `provider="both"` (what
the UI uses) both providers run at once; if one fails, the other image is still
saved and the failure comes back as a `warning`.

- **style**: always the world's `style.txt`; generation is refused while it is
  empty. New worlds can start from a preset (`STYLES` in `prompt_manager.py`).
  The `ligne_claire_lineart` preset, kept word for word, also swaps in line-only
  framing for locations and shots.
- **shots**: the prompt is the scene heading and summary plus the shot's action
  (dialogue is never drawn), with the newest image of each character, location
  and object the scene lists as references.
- **aspect_ratio**: `landscape` (16:9, default), `square`, `portrait` (9:16).
- **quality**: `low` (default), `medium`, `high`. On Gemini only `high` changes
  anything (it sets `thinking_level`).
