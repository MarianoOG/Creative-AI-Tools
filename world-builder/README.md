# World Builder

Build **worlds** with OpenAI and Gemini. Each world has one visual style (its
`style.txt`), its **characters**, **locations** and **objects**, and its
**episodes**: scenes made of storyboard shots, written in a `script.json`.

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
| World | The world's characters, locations, objects and episodes, one tab each. Create and delete episodes here. |
| Create asset | Generate a character, location or object in the world's style. |
| Episode script | The whole episode as text, scene by scene, with each scene's references. Add, edit and delete scenes. |
| Storyboard | One scene's shots: each frame next to its action and dialogue, and generation of the missing frames. |
| Manage worlds | Create (from a style preset), rename and delete worlds. |

The sidebar holds the world picker and the world's `style.txt`, editable in place.
Deleting an episode or a scene asks first, because its shots go with it.

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
