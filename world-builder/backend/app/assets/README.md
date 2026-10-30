# Worlds, assets and stories

Four kinds of image, each rendered by one provider, OpenAI (`gpt-image-2`) or
Gemini (Nano Banana 2), always in the world's style:

| Type | What it renders | References are treated as |
| --- | --- | --- |
| `character` | Turnaround sheet: front, three-quarter, back on white | inspiration (uploads) |
| `object` | Turnaround sheet: front isometric and side views on white | inspiration (uploads) |
| `location` | Empty background plate, no figures, in three views | inspiration (uploads) |
| `shot` | Storyboard frame | designs to reproduce faithfully (the scene's assets) |

An asset is created as just a name and a description, with no images. Its
images are **variations**, each with a name, and one is **preferred** (the
first one made, until another is picked):

- Characters and objects take any named variation (new clothes, older, broken,
  dirty...). The first is drawn from the description; later ones from the
  preferred image, as the design to keep, plus what the variation says changes.
- A location's variations are the fixed views of `LOCATION_VIEWS`
  (`establishing`, `reverse`, `detail`), rendered together: the establishing
  view from the description, the others from it as the same place.

Any variation can be regenerated, or all of them at once (the preferred image,
or the establishing view, first), from the asset's current description and the
reference images it was made with.

- `prompt_manager.py`: prompt text (style presets, framing per type, location views, reference clauses). No I/O.
- `generation.py`: provider calls and writing files.
- `worlds.py`: creating, renaming and deleting worlds, and reading and writing their `world.json`.
- `library.py`: assets, their variations and the preferred one, in `world.json`.
- `story.py`: episodes, scenes, shots and `script.json`.

The HTTP API is in `app/routers/`. Keys (`OPENAI_API_KEY`, `GEMINI_API_KEY`) go
in `backend/.env`.

## Files

There is no database: the JSON files are the store, and the folders are the story structure.

```text
data/assets/
└── <world>/
    ├── world.json                the style, and every character, location and object
    ├── references/               uploaded reference images, kept for regenerating
    ├── characters/
    ├── locations/
    ├── objects/
    └── episodes/
        └── <episode>/
            ├── script.json       title, synopsis, model, aspect ratio, and every scene's text
            └── <scene>/          the scene's shot images
```

New files are named `{uuid8}-{name}-{variation}` (shots: `{uuid8}-{shot}`). Every
render gets a new uuid, so nothing is overwritten. OpenAI writes PNG and Gemini
JPEG; output is 2K.

The JSON files decide what exists: an image in a folder that no `world.json` or
`script.json` entry points at is an orphan and is never shown. Removing an
asset, a variation or a shot, or regenerating anything, only changes the JSON;
the files stay on disk. Deleting a world, an episode or a scene moves its folder
into a hidden `.deleted/` folder beside it.

## world.json

```json
{
  "style": "Hand-painted watercolour storybook style...",
  "characters": [{
    "name": "fox_hero",
    "description": "A young red fox in a green scarf.",
    "preferred": "young",
    "variations": [
      {"name": "young", "description": "", "provider": "openai", "image": "1a2b3c4d-fox_hero-young.png",
       "references": ["9f8e7d6c-fox_hero-young-ref1.png"]},
      {"name": "older", "description": "Twenty years older, grey muzzle.", "provider": "gemini",
       "image": "5e6f7a8b-fox_hero-older.jpg", "references": []}
    ]
  }],
  "locations": [{"name": "night_market", "description": "...", "variations": [
    {"name": "establishing", "...": "..."}, {"name": "reverse", "...": "..."}, {"name": "detail", "...": "..."}
  ]}],
  "objects": []
}
```

A world from before `world.json` gets one on its first read: the style from
its `style.txt` (which is then no longer used) and, for each asset name, its
newest file as its one variation (`original`, or `establishing` for a
location), preferred. Nothing on disk is renamed or removed. A `world.json`
without `preferred` reads its first variation as preferred.

Worlds are isolated: assets never move between them. Renaming an asset updates
the scenes that point at it; its files keep their names.

## script.json

Folders decide which episodes and scenes exist; the script decides their order
and words. A scene folder missing from the script reads as an empty scene, and a
scene entry without a folder is dropped on the next save.

```json
{
  "title": "The Lantern",
  "synopsis": "A fox arrives at a night market...",
  "provider": "openai",
  "aspect_ratio": "landscape",
  "scenes": [{
    "id": "scene1",
    "heading": "EXT. NIGHT MARKET - NIGHT",
    "summary": "What happens in the scene.",
    "characters": ["fox_hero:older"], "locations": ["night_market"], "objects": ["brass_lantern"],
    "shots": [{
      "id": "market_night",
      "action": "The fox walks down the wet street, lantern raised.",
      "image": "9c0d1e2f-market_night.png"
    }]
  }]
}
```

`characters`, `locations` and `objects` hold references: `name` for an asset's
preferred image, `name:variation` for a specific one (`fox_hero:older`,
`night_market:reverse`). A shot's `image` is its one frame in the scene folder;
scripts from before it get the newest file named after the shot.

## Generating

`POST /assets` creates an asset (no images) and `PATCH /assets` renames it,
changes its description or picks its preferred variation. `POST
/assets/variations` (characters, objects), `POST /assets/views` (a location's
missing views), `POST /assets/regenerate` and
`POST /worlds/{world}/episodes/{episode}/scenes/{scene}/shots/{shot}/generate`
wait for the render and return the result. Each image is rendered by one
`provider` (`openai`, `gemini` or `runware`).

- **style**: always the world's style; generation is refused while it is
  empty. New worlds can start from a preset (`STYLES` in `prompt_manager.py`).
  The `ligne_claire_lineart` preset, kept word for word, also swaps in line-only
  framing for locations and shots.
- **assets**: always landscape (16:9) and high quality. Several renders (a
  location's views, regenerate all) run one after another; if one fails, the
  ones already made are kept and the failure comes back as a `warning`.
- **shots**: the prompt is the scene heading and summary plus the shot's action,
  with the description of each character, location and object the scene lists
  (no images are sent). Every shot is a *low detailed view* in the world's
  style: simplified, and about composition and lighting only. It renders at low
  quality and a lower resolution (`SHOT_SIZES` in `generation.py`). The model
  and aspect ratio (`landscape`, `square`, `portrait`) are the episode's.
  Regenerating points the shot at the new image.
