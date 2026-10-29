# World Builder

Generate visual assets — **characters**, **objects**, **locations** and
**scenes** — with OpenAI and Gemini, and organise them into worlds. The
long-term direction is a world-building tool for visual creative media.

Asset generation is described in `backend/app/assets/README.md`.

## Architecture

Two services that share one `data/` folder:

| Service | What it does | `data/` access |
| --- | --- | --- |
| `backend/` (FastAPI) | All the logic: API calls, generation, files | read and write |
| `frontend/` (Streamlit) | The UI, calling the backend over HTTP | read-only |

The backend returns file paths relative to `data/`, and the frontend opens them
from its own read-only mount. Long work (image renders) runs as background jobs
in the backend, so leaving a page never cancels it. API docs, grouped by tag,
are at http://localhost:8000/docs.

`data/` defaults to `world-builder/data/`; set `DATA_DIR` to put it elsewhere.

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

Run the backend as a single process (no `--workers`): background jobs are held
in its memory.

## Run with Docker

From `world-builder/`:

```bash
docker compose up --build
```

The UI is at http://localhost:8501. Both ports are bound to localhost only,
because neither service has authentication and both can spend API credits.

Stopping the stack waits up to three minutes for in-flight renders, so paid
images are not lost.
