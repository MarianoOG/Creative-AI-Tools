# Worlds, assets and stories

Four kinds of image, each rendered by one provider, OpenAI (`gpt-image-2`),
Gemini (Nano Banana 2) or Runware (Flux 2 Klein), always in the world's style:

| Type | What it renders | References are treated as |
| --- | --- | --- |
| `character` | Turnaround sheet: front, three-quarter, back on white | inspiration (uploads) |
| `object` | Turnaround sheet: front isometric and side views on white | inspiration (uploads) |
| `location` | Empty background plate, no figures, establishing shot first | inspiration (uploads) |
| `final` | A shot's frame | the scene's assets as designs to reproduce faithfully |

An asset is created as just a name and a description, with no images. Its
images are **variations**, each with a name, and one is **preferred** (the
first one made, until another is picked):

- Characters and objects take any named variation (new clothes, older, broken,
  dirty...). The first is drawn from the description; later ones from the
  preferred image, as the design to keep, plus what the variation says changes.
- A location works the same way, except that its first image is always the
  `establishing` shot, drawn from the description. Its other variations are
  named and described freely (a reverse angle, night, after the storm...) and
  drawn from the establishing shot as the same empty place.

Any variation can be regenerated, or all of them at once (the preferred image,
or the establishing view, first), from the asset's current description and the
reference images it was made with.

- `prompt_manager.py`: prompt text (style presets, framing per type, location camera, reference clauses). No I/O.
- `generation.py`: provider calls and writing files.
- `worlds.py`: creating, renaming and deleting worlds, and reading and writing their `world.json`.
- `library.py`: assets, their variations and the preferred one, in `world.json`.
- `story.py`: episodes: their `script.fountain` and `episode.json`, versions, and converting older episodes.
- `fountain.py`: reading Fountain screenplays, the app's hidden notes, the linter and the preview. No I/O.
- `sync.py`: carrying scene and shot ids from the saved script to an edited one, and the change summary. No I/O.
- `tagging.py`: tags and the checklist from the text model (Claude Haiku on Runware by default).
- `video.py`: shot videos (Runware MiniMax H3 Fast) and their prompt.

The HTTP API is in `app/routers/`. Keys (`OPENAI_API_KEY`, `GEMINI_API_KEY`) go
in `backend/.env`.

## Files

There is no database: the JSON and Fountain files are the store.

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
            ├── script.fountain   the screenplay: every word, the order, and (in hidden notes) ids, tags and clip lengths
            ├── episode.json      aspect ratio, model, and each shot's frame and video, by shot id
            ├── shots/            the shots' frames and videos
            └── .versions/        the script before each save, reprocess or restore
```

New files are named `{uuid8}-{name}-{variation}` (final frames: `{uuid8}-{shot id}-final`). Every
render gets a new uuid, so nothing is overwritten. OpenAI writes PNG and Gemini
JPEG; assets are 2K, final frames 1K (the size of the 768p video).

The files decide what exists: an image that no `world.json` or `episode.json`
entry points at is an orphan and is never shown. Removing an asset, a variation
or a shot, or regenerating anything, only changes those files; the images and
videos stay on disk. Deleting a world or an episode moves its folder into a
hidden `.deleted/` folder beside it.

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
    {"name": "establishing", "...": "..."}, {"name": "night", "description": "After dusk, lanterns lit.", "...": "..."}
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
the tags that name it in every script; its files keep their names.

## Episodes: script.fountain and episode.json

The script is a [Fountain](https://fountain.io) screenplay, the source of truth
for the story: a title page (`Title:`, `Synopsis:`), scene headings
(`INT. KITCHEN - DAY`, or any line starting with a period), synopses (`= ...`,
a scene's summary), action and dialogue. **Each action paragraph is a shot**,
and the dialogue after it belongs to it. Writers never see ids: the app keeps
what it needs in a note of its own at the end of each heading and each shot,
hidden in the editor and written back on save:

```text
INT. KITCHEN - DAY [[wb: id=k7q2d8; loc=kitchen]]

= Mara finds the lantern still warm.

Wide, low angle. Mara steps in and stops at the table. [[wb: id=a3f9c2; dur=8; chars=mara; objs=lantern]]

MARA
(whispering)
Who lit this?
```

`loc`, `chars` and `objs` are tags: `name` for an asset's preferred image,
`name:variation` for a specific one (`fox_hero:older`). A key that is there
but empty means "tagged, nothing in it"; a missing one means "not tagged yet".
`dur` is the clip's length (5, 6, 8, 10 or 15 seconds; 5 when left out).

`episode.json` holds only what a screenplay cannot:

```json
{
  "aspect_ratio": "landscape",
  "final_provider": "gemini",
  "shots": {"a3f9c2": {
    "final": "shots/3a4b5c6d-a3f9c2-final.jpg", "final_hash": "...",
    "video": "shots/7e8f9a0b-a3f9c2-video.mp4", "video_hash": "...", "video_final": "shots/3a4b5c6d-a3f9c2-final.jpg",
    "end_on_next": false, "tags_manual": false, "check": {"hash": "...", "missing": ["Camera angle"]}
  }},
  "scenes": {"k7q2d8": {"tags_manual": false}}
}
```

- **Saving** (`PUT .../episodes/{episode}/text`) takes the script as the editor
  shows it. `sync.py` matches its scenes and shots to the saved ones: identical
  shots, then similar ones (an edit keeps the id, so the frame stays linked and
  is flagged stale), then shots moved elsewhere. A shot rewritten beyond
  recognition is a new one. The previous file goes to `.versions/`.
  `POST .../preview` says what a save would change, without saving.
- **Tags and checklist**: on save, new and changed shots (and scenes) go to the
  text model (`TEXT_MODEL`, default `anthropic:claude@haiku-5.5`, through
  Runware's OpenAI-compatible endpoint). It tags each shot's characters and
  objects and each scene's locations, using only names the world has, and says
  which checklist items (framing, camera angle, camera movement, who or what is
  in frame, what happens) a shot does not mention. It never suggests values.
  Tags set by hand (`PATCH .../shots/{shot}`, `PATCH .../scenes/{scene}`) are
  not changed by the model again. If the call fails, the save goes through
  without them.
- **Reprocess** (`POST .../reprocess`) reads the file as it is on disk (after
  editing it in another app) and fills in missing ids, tags and checklists.
- **Stale**: `final_hash` is the shot's fingerprint (scene heading, summary
  and locations, the shot's action and tags; not dialogue) when its frame was
  made; a different one now means the frame is out of date. A video is out of
  date when it was made from another frame or before the shot or its length changed.
- **Unlinked**: a shot's entry stays in `episode.json` when the shot leaves the
  script, so restoring an older version (`POST .../versions/restore`) links its files again.
- **Older episodes** (a `script.json` and scene folders) are converted on their
  first read: each shot keeps its words, clip length, frame and video; its type
  and camera move become words in its action; its scene's characters and
  objects become its tags. The `script.json` stays on disk.

## Generating

`POST /assets` creates an asset (no images) and `PATCH /assets` renames it,
changes its description or picks its preferred variation. `POST
/assets/variations` (any asset; a location's first is its establishing shot), `POST /assets/regenerate` and
`POST /worlds/{world}/episodes/{episode}/shots/{shot}/generate`
wait for the render and return the result. Each image is rendered by one
`provider` (`openai`, `gemini` or `runware`).

- **style**: always the world's style; generation is refused while it is
  empty. New worlds can start from a preset (`STYLES` in `prompt_manager.py`).
  The `ligne_claire_lineart` preset, kept word for word, also swaps in line-only
  framing for locations and final frames.
- **assets**: always landscape (16:9) and high quality. Several renders (regenerate all) run one after another; if one fails, the
  ones already made are kept and the failure comes back as a `warning`.
- **final frames**: the shot endpoint, with `{"provider": "openai" | "gemini" | "runware"}`
  (the episode's last one when left out), renders the shot's finished, fully
  detailed frame at 1K (1360×768 landscape, the size of the 768p video it becomes) in the episode's
  aspect ratio, with OpenAI at medium quality. It is sent the image of every character
  and object tagged on the shot and every location tagged on its scene (as designs to reproduce,
  which with the world's style decide the look), plus their descriptions and the shot's text
  (the scene's heading and summary, and the shot's action; not its dialogue).
  Regenerating points `final` at the new image.
- **shot videos**: `POST /worlds/{world}/episodes/{episode}/shots/{shot}/video`
  animates the shot's final frame with Runware's MiniMax H3 Fast (`minimax:h3@fast`) at 768p, for the
  shot's clip length. The frame is sent as the first frame; the prompt is the shot's text (as for its
  final frame), the world's style, and a direction to keep the frame's designs and style, to move the
  camera only as the action says (still when it says nothing), and to have no dialogue or voices. The task runs async and is polled until done
  (up to 9 minutes). It refuses a shot with no final frame. The clip is saved as
  `{uuid8}-{shot id}-video.mp4` in `shots/`, and its billed cost is logged (the list price,
  $0.08/s, marked estimated, if Runware reports none). Regenerating a frame leaves the old clip
  in place until the video is regenerated too.
