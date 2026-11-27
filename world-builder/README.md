# World Builder

Build **worlds** with image models reached through one provider, Runware: OpenAI GPT-Image-2.6 (Sunburst or Flare), Nano Banana 2.1, FLUX 3 Image or FLUX 3 Image Klein (the cheapest and fastest). Each world has a `world.json` holding
its visual style, its **context** (free notes on the premise, cast and tone, never sent to a render) and its **characters**, **locations** and **objects** (with
their variations), and its **episodes**: screenplays written in
[Fountain](https://fountain.io), plain text where each action paragraph is a storyboard shot.

| Service | What it does | `data/` access |
| --- | --- | --- |
| `backend/` (FastAPI) | All the logic: API calls, generation, files | read and write |
| `frontend/` (Streamlit) | The UI, calling the backend over HTTP | read-only |

Both services share the `data/` folder at the repository root (set `DATA_DIR`
to use another); worlds live in `data/assets/`. The backend returns paths relative to it, and the frontend
opens them itself. API docs are at http://localhost:8000/docs; how generation
works is in `backend/app/assets/README.md`.

## Pages

| Page | What it shows |
| --- | --- |
| World | The world's characters, locations and objects (three columns, each shown by its preferred image) and episodes (newest first), one view each, picked in the top bar. Create assets (a name and a description) and episodes (a title, a synopsis and an aspect ratio) the same way, from the New button in the bar that opens a small form; a new one opens on its own page. Click an image or Edit to open the asset. The bar also says what the world has spent on renders. |
| Asset | One asset, picked in the sidebar: edit its name and description, and generate, prefer, regenerate (one or all) and delete its variations (a location starts with one wide 3:1 panorama of the whole place, and its variations stay panoramas). |
| Script | The episode as a Fountain screenplay, in three views picked in the top bar: **Write** (a plain-text editor, with a narrower **Cheat sheet** of Fountain to copy and paste beside it), **Preview** (the screenplay as it reads, unsaved edits included) and **Breakdown** (one scene at a time, picked at the top: its locations, the characters and objects in it, then each shot's action and dialogue beside its characters, objects, clip length and checklist). Each action paragraph is a shot; the dialogue under it belongs to it. New episodes start from a sample scene of placeholders. The bar also says what saving would change (+1 scene · −2 shots · 1 shot modified), opens the problems (syntax problems by line, such as a heading without INT./EXT. or a name with no dialogue under it, and references the world does not have) and has **Save** and **Discard**. **Save** asks first, listing the changes (removals, and the frames they unlink, first). Saving keeps each shot's frames through edits (an edited shot's frame is flagged as out of date), and the text model (Claude Haiku on Runware) tags new and changed shots with the world's characters, objects and locations and lists which checklist items each shot does not mention (framing, camera angle, camera movement, who or what is in frame, what happens), without suggesting any. Fix a tag in the Breakdown and it stays as you set it. The ids and tags live in hidden notes in `script.fountain`, so they cannot be deleted from the editor. Every save keeps the previous script: **Versions** in the sidebar shows and restores them. **Reprocess file** fills in ids, tags and checklists after editing the file in another app. The sidebar also has the episode and its aspect ratio. Nothing is generated here. |
| Storyboard | An episode's final frames, two per row, each with its number and words under it, a warning when the shot changed after its frame, and a Generate or Regenerate button with its price (this world's average logged cost for the chosen model, else a rough list price). The sidebar has the episode, the model (GPT-Image-2.6, Nano Banana 2.1 or FLUX 3, kept per episode) and **Export all frames** (a zip). The top bar says how many frames are done and generates the missing ones in one click (drawn from the shot's text and the designs of what is tagged on it, in the world's style). Regenerating is one frame at a time: there is no "regenerate all", as it costs too much to be one click away. |
| Video | One row per shot: its final frame on the left and its video on the right, so a missing or out-of-date video (made from another frame, or before the shot or its length changed: flagged) stands out. The sidebar has the episode, the model (Runware's MiniMax H3 Fast at 768p, $0.08/s, or Gemini Omni Flash 1.2 at 720p, $0.07/s, list prices; kept per episode) and **Export all videos** (a zip). Each shot's final frame is animated into a clip (no dialogue or voices), prompted with the world's style, the frame and the shot's text (scene heading and summary, the shot's action and tagged cast). The camera moves only as the action says. Each shot's clip length (5 to 15 s, 5 by default; saved in the script; Omni Flash renders up to 10 s from a frame) and "end on the next shot's frame" toggle sit on one line beside its button. The price of each clip shows on every button; the top bar says how many videos are up to date and generates all the pending ones (missing or out of date). There is no "regenerate all". A shot needs its final frame first. |
| Manage worlds | Create (from a style preset) and delete worlds, and edit each one's name, style and context behind one Save world button. |

The sidebar holds the world picker (and, on the episode pages, the episode, newest first). Every page starts with a top bar instead of a title: its views and main actions, staying on screen as the page scrolls.
Nothing in the app removes a file. Deleting an asset or a variation only drops
it from `world.json`; removing a shot from the script leaves its frame and video
on disk (restore an older version to link them again); deleting a world or an
episode moves its folder into a hidden `.deleted/` folder next to it. Each asks first.

Episodes made before the Fountain script (a `script.json`) are converted on
first open, keeping every frame and video.

## Setup

From `world-builder/`:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt -r frontend/requirements.txt
cp backend/.env.example backend/.env   # then fill in RUNWARE_API_KEY
```

## Run locally

```bash
cd backend && uvicorn app.main:app --reload   # terminal 1
cd frontend && streamlit run app.py           # terminal 2
```

## Tests

```bash
cd backend && pip install pytest && python -m pytest tests
```

## Run with Docker

```bash
docker compose up --build
```

The UI is at http://localhost:8501. Both ports are bound to localhost only,
because neither service has authentication and both can spend API credits.
