# World Builder

Build **worlds** with OpenAI, Gemini or Runware (Flux 2 Klein 4B, cheap and fast). Each world has a `world.json` holding
its visual style and its **characters**, **locations** and **objects** (with
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
| World | The world's characters, locations and objects (three columns, each shown by its preferred image) and episodes, one tab each. Create assets (a name and a description) and episodes here. Click an image or Edit to open the asset. |
| Asset | One asset: edit its name and description, and generate, prefer, regenerate (one or all) and delete its variations, or a location's views. |
| Script | The whole episode, scene by scene and shot by shot, editable in place: each scene's heading, summary and references, and each shot's type (wide, medium, close-up, panorama, ...) and action, as text only (nothing is generated here). Add and delete scenes and shots, and set the episode's aspect ratio. Any button saves everything typed on the page. |
| Storyboard | An episode's high-fidelity final frames in a grid, each with a Regenerate button. Generate the missing ones in one click (OpenAI or Gemini, your pick, drawn from the shot's text and the scene's designs in the world's style), then download them all as a zip. Once all exist, the small refresh icon beside Export regenerates every one (after a confirm). |
| Manage worlds | Create (from a style preset) and delete worlds, and edit each one's name and style behind one Save world button. |

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
