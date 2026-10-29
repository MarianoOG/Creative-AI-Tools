# Creative AI Tools

Creative AI tools for visual media — images and video: generating assets and
analysing visual media. Asset generation (worlds, prompts, library) is the core.
The YouTube tool is slated to move out into a separate, standalone tool.

## Project Structure

Two services: a FastAPI backend with all the logic, and a Streamlit frontend
that only renders what the backend returns. They share `data/` — the backend
reads and writes it, the frontend mounts it read-only and opens the relative
paths the API returns.

```text
Creative AI Tools/
├── backend/                  # FastAPI service (all logic)
│   ├── app/
│   │   ├── main.py           # App, lifespan, router registration, OpenAPI tags
│   │   ├── settings.py       # DATA_DIR, .env loading, relative/resolve helpers
│   │   ├── jobs.py           # Background job registry (asset/youtube pools)
│   │   ├── routers/          # One router per tag: assets, worlds, jobs, youtube
│   │   ├── assets/           # Generation, prompts, library scan, worlds
│   │   └── youtube/          # YouTube API, search pipeline, metrics, saved searches
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env                  # API keys (see .env.example)
├── frontend/                 # Streamlit service (visuals only)
│   ├── app.py                # st.navigation entry point
│   ├── api.py                # The only module that calls the backend
│   ├── shared/               # Session state, world switcher, job tracking, YouTube filters
│   ├── views/                # assets/, youtube/ pages
│   ├── requirements.txt
│   └── Dockerfile
├── data/                     # Shared, gitignored: assets/, youtube/
├── docker-compose.yml
└── .venv/                    # Shared Python 3.12 virtual environment
```

## Environment

Always activate the virtual environment before running or testing Python code:

```bash
source .venv/bin/activate
```

## Running Apps

**Everything (Docker):**

```bash
docker compose up --build
```

**Locally:**

```bash
cd backend && uvicorn app.main:app --reload
cd frontend && streamlit run app.py
```

The backend must run as a single process: the job registry is in memory.

## Workflow Guidelines

- **Before running Python:** Always activate `.venv` first
- **After code changes:** Check if the relevant README.md needs updating. Keep documentation general to minimize future edits
- **API keys:** Never commit `.env` files or expose API keys
- **Dependencies:** Add new packages to the service's `requirements.txt`
- **Logic vs. visuals:** Business logic, validation and labels belong in the backend; the frontend only lays out what the API returns

## Code Style

- Use type hints for function signatures
- Keep functions focused and single-purpose
- Follow existing patterns in each service
