"""Worlds - create, rename and delete the settings assets are grouped into.

Rename and delete are held only for a world a running generation is about to
write into; every other world stays editable while renders are in flight.
"""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import jobs
from app.assets.library import list_assets
from app.assets.worlds import create_world, delete_world, list_worlds, rename_world

router = APIRouter(prefix="/worlds", tags=["worlds"])


class WorldName(BaseModel):
    name: str


def _hold_if_busy(world: str) -> None:
    if world in jobs.busy_worlds():
        raise HTTPException(
            409, f"A generation is writing into {world}. Try again when it lands."
        )


@router.get("")
def get_worlds(request: Request) -> Dict:
    """Every world with its size and whether a generation is writing into it.

    ``migration_skipped`` lists files the startup migration into ``default``
    left behind because the name was already taken there.
    """
    busy = jobs.busy_worlds()
    return {
        "worlds": [
            {"name": world, "asset_count": len(list_assets(world=world)), "busy": world in busy}
            for world in list_worlds()
        ],
        "migration_skipped": request.app.state.migration_skipped,
    }


@router.post("", status_code=201)
def post_world(body: WorldName) -> Dict:
    """A new, empty world. Safe mid-generation: nothing can be writing into it."""
    try:
        return {"name": create_world(body.name)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/{world}")
def patch_world(world: str, body: WorldName) -> Dict:
    _hold_if_busy(world)
    try:
        return {"name": rename_world(world, body.name)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/{world}", status_code=204)
def remove_world(world: str) -> None:
    _hold_if_busy(world)
    try:
        delete_world(world)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
