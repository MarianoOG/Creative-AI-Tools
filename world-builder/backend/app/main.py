"""World Builder API. Run from ``backend/`` with ``uvicorn app.main:app --reload``."""

from __future__ import annotations

from fastapi import FastAPI

from app.routers import assets, story, worlds

TAGS = [
    {"name": "assets", "description": "Browse, generate, move and delete character, object and location images."},
    {"name": "worlds", "description": "The settings assets are grouped into, each with its own style."},
    {"name": "story", "description": "Episodes, scenes and storyboard shots, with their scripts."},
]

app = FastAPI(title="World Builder API", openapi_tags=TAGS)
app.include_router(assets.router)
app.include_router(worlds.router)
app.include_router(story.router)


@app.get("/health", include_in_schema=False)
def health() -> dict:
    return {"status": "ok"}
