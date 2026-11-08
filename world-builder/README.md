# World Builder

Build **worlds** with OpenAI, Gemini or Runware (Flux 2 Klein 4B, cheap and fast). Each world has a `world.json` holding
its visual style, its **context** (free notes on the premise, cast and tone, never sent to a render) and its **characters**, **locations** and **objects** (with
their variations), and its **episodes**: scenes made of storyboard shots,
written in a `script.json`.

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
| World | The world's characters, locations and objects (three columns, each shown by its preferred image) and episodes, one tab each. Create assets (a name and a description) and episodes (a title, a synopsis and an aspect ratio) the same way, from a New button that opens a small form; a new one opens on its own page. Click an image or Edit to open the asset. |
| Asset | One asset, picked in the sidebar: edit its name and description, and generate, prefer, regenerate (one or all) and delete its variations (a location starts with its establishing shot). |
| Script | The whole episode, scene by scene and shot by shot, editable in place: each scene's heading, summary and references, and each shot's action (its type is set on the Storyboard, its camera move and clip length on the Video page), as text only (nothing is generated here). Add and delete scenes and shots (shots are numbered `shot1`, `shot2`... by their place in the scene, never named), and set the episode's aspect ratio. The episode picker is in the sidebar. Every field saves as soon as it changes (a text field when you leave it), so there is no Save button. |
| Storyboard | An episode's final frames, two per row, each with one line under it: the shot's type (wide, medium, close-up, panorama, ...; saved as soon as it changes) and a Generate or Regenerate button with its price (this world's average logged cost for the chosen model, else a rough list price; OpenAI's varies). Generate the missing ones in one click (OpenAI, Gemini or Runware Flux 2 Klein, your pick, drawn from the shot's text and the scene's designs in the world's style), then download them all as a zip. Regenerating is one frame at a time: there is no "regenerate all", as it costs too much to be one click away. |
| Video | One row per shot: its final frame on the left and its video on the right, so a missing video, or one older than a regenerated frame (flagged), stands out. Each shot's final frame is animated into a clip with Runware's MiniMax H3 Fast at 768p (no dialogue or voices), prompted with the world's style, the frame, the shot's text (scene heading, summary and cast, and the shot's type and action) and its camera move. Each shot has its own camera move (Static by default) and clip length (5 to 15 s, 5 by default), set on one line beside its button and saved with the shot. The price of each clip ($0.08/s list price) shows on every button; generate or regenerate one, or all the pending ones (missing or older than their frame), and download them as a zip. There is no "regenerate all". A shot needs its final frame first. |
| Manage worlds | Create (from a style preset) and delete worlds, and edit each one's name, style and context behind one Save world button. |

The sidebar holds the world picker.
Nothing in the app removes a file. Deleting an asset or a variation only drops
it from `world.json`; deleting a world, an episode or a scene moves its folder
into a hidden `.deleted/` folder next to it. Each asks first.

## Setup

From `world-builder/`:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt -r frontend/requirements.txt
cp backend/.env.example backend/.env   # then fill in the keys you need
```

## Run locally

```bash
cd backend && uvicorn app.main:app --reload   # terminal 1
cd frontend && streamlit run app.py           # terminal 2
```

## Run with Docker

```bash
docker compose up --build
```

The UI is at http://localhost:8501. Both ports are bound to localhost only,
because neither service has authentication and both can spend API credits.
