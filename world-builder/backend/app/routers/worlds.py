"""Worlds: create, rename and delete the settings assets are grouped into."""

from __future__ import annotations

from typing import Callable, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.assets.library import list_assets
from app.assets.worlds import create_world, delete_world, list_worlds, rename_world

router = APIRouter(prefix="/worlds", tags=["worlds"])


class WorldName(BaseModel):
    name: str


def _call(fn: Callable, *args: str):
    try:
        return fn(*args)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("")
def get_worlds() -> Dict:
    """Every world with its asset count."""
    return {"worlds": [{"name": w, "asset_count": len(list_assets(w))} for w in list_worlds()]}


@router.post("", status_code=201)
def post_world(body: WorldName) -> Dict:
    return {"name": _call(create_world, body.name)}


@router.patch("/{world}")
def patch_world(world: str, body: WorldName) -> Dict:
    return {"name": _call(rename_world, world, body.name)}


@router.delete("/{world}", status_code=204)
def remove_world(world: str) -> None:
    _call(delete_world, world)
