"""Creative AI Tools API - all the logic behind the Streamlit frontend.

Run locally from ``backend/``:

    uvicorn app.main:app --reload

Interactive docs at ``/docs``. Run it as a single process (no ``--workers``):
the background job registry lives in this process's memory.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import jobs
from app.assets.worlds import ensure_migrated
from app.routers import assets, jobs as jobs_router, worlds, youtube
from app.settings import ASSETS_DIR

TAGS = [
    {"name": "assets", "description": "Browse, generate, move and delete character, object, location and scene images."},
    {"name": "worlds", "description": "The settings assets are grouped into."},
    {"name": "jobs", "description": "Follow background generations and searches."},
    {"name": "youtube", "description": "Creator Discovery: find YouTube creators for partnerships."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Folded in once per process: until it has run, a pre-world tree would read
    # as worlds called "characters", "objects" and so on.
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    app.state.migration_skipped = ensure_migrated()
    yield
    # Wait for in-flight paid work rather than dropping it.
    jobs.shutdown()


app = FastAPI(title="Creative AI Tools API", openapi_tags=TAGS, lifespan=lifespan)
for module in (assets, worlds, jobs_router, youtube):
    app.include_router(module.router)


@app.get("/health", include_in_schema=False)
def health() -> dict:
    return {"status": "ok"}
