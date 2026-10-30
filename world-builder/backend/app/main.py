"""World Builder API. Run from ``backend/`` with ``uvicorn app.main:app --reload``."""

from __future__ import annotations

from fastapi import FastAPI

from app.routers import assets, worlds

TAGS = [
    {"name": "assets", "description": "Browse, generate, move and delete character, object, location and scene images."},
    {"name": "worlds", "description": "The settings assets are grouped into."},
]

app = FastAPI(title="World Builder API", openapi_tags=TAGS)
app.include_router(assets.router)
app.include_router(worlds.router)


@app.get("/health", include_in_schema=False)
def health() -> dict:
    return {"status": "ok"}
