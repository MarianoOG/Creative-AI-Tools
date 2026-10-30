# World Builder

Generate visual assets (**characters**, **objects**, **locations** and
**scenes**) with OpenAI and Gemini, and organise them into worlds.

| Service | What it does | `data/` access |
| --- | --- | --- |
| `backend/` (FastAPI) | All the logic: API calls, generation, files | read and write |
| `frontend/` (Streamlit) | The UI, calling the backend over HTTP | read-only |

Both services share the `data/` folder at the repository root (set `DATA_DIR`
to use another). The backend returns paths relative to it, and the frontend
opens them itself. API docs are at http://localhost:8000/docs; how generation
works is in `backend/app/assets/README.md`.

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
