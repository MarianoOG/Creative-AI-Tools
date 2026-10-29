# Creative AI Tools

AI tools for visual creative media (images and video): generating it and
analysing it. Each top-level folder is a standalone tool: its own README,
`requirements.txt`, `.env` and `.venv`. Tools do not import from each other.

## Project Structure

```text
Creative AI Tools/
├── world-builder/                # Visual asset generation, organised into worlds
│   ├── backend/                  # FastAPI service (all logic)
│   │   └── app/
│   │       ├── main.py           # App, lifespan, router registration, OpenAPI tags
│   │       ├── settings.py       # DATA_DIR, .env loading, relative/resolve helpers
│   │       ├── jobs.py           # Background job registry
│   │       ├── routers/          # One router per tag: assets, worlds, jobs
│   │       └── assets/           # Generation, prompts, library scan, worlds
│   ├── frontend/                 # Streamlit service (visuals only)
│   │   ├── app.py                # st.navigation entry point
│   │   ├── api.py                # The only module that calls the backend
│   │   ├── shared/               # Session state, world switcher, job tracking
│   │   └── views/                # Pages
│   ├── data/                     # Gitignored; backend writes, frontend reads
│   ├── docker-compose.yml
│   └── .venv/
└── youtube-scout/                # YouTube channel and video research (library)
    ├── youtube_scout/            # Package: API client, search, filters, metrics, saved searches
    ├── data/                     # Gitignored; saved searches
    └── .venv/
```

## Environment

Each tool has its own virtual environment. Activate the one for the tool you are
working on before running or testing Python code:

```bash
cd world-builder && source .venv/bin/activate   # or youtube-scout
```

## World Builder

Two services: a FastAPI backend with all the logic, and a Streamlit frontend
that only renders what the backend returns. They share `world-builder/data/`:
the backend reads and writes it, the frontend mounts it read-only and opens the
relative paths the API returns.

```bash
cd world-builder && docker compose up --build    # everything
cd world-builder/backend && uvicorn app.main:app --reload
cd world-builder/frontend && streamlit run app.py
```

The backend must run as a single process: the job registry is in memory.

## YouTube Scout

A plain Python library: functions that take simple arguments and return
JSON-serialisable data, so a CLI or agent skill can wrap them later. No UI or
server.

## Workflow Guidelines

- **Before running Python:** Activate the tool's `.venv` first
- **After code changes:** Check if the relevant README.md needs updating. Keep documentation general to minimize future edits
- **API keys:** Never commit `.env` files or expose API keys
- **Dependencies:** Add new packages to the tool's (or service's) `requirements.txt`
- **Logic vs. visuals (World Builder):** Business logic, validation and labels belong in the backend; the frontend only lays out what the API returns
- **Separation:** Keep tools independent; don't share code or data folders between them

## Code Style

- Use type hints for function signatures
- Keep functions focused and single-purpose
- Follow existing patterns in each tool
