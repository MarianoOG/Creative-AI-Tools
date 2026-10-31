"""Worlds: create, rename and delete the settings assets are grouped into, and edit their style."""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter
from pydantic import BaseModel

from app.assets.library import list_assets
from app.assets.story import list_episodes
from app.assets.worlds import create_world, delete_world, list_worlds, read_style, rename_world, write_style
from app.routers.common import call, check_world

router = APIRouter(prefix="/worlds", tags=["worlds"])


class WorldName(BaseModel):
    name: str
    style: str = ""


class Style(BaseModel):
    style: str


@router.get("")
def get_worlds() -> Dict:
    """Every world with its asset and episode counts."""
    return {
        "worlds": [
            {"name": w, "asset_count": len(list_assets(w)), "episode_count": len(list_episodes(w))}
            for w in list_worlds()
        ]
    }


@router.post("", status_code=201)
def post_world(body: WorldName) -> Dict:
    return {"name": call(create_world, body.name, body.style)}


@router.patch("/{world}")
def patch_world(world: str, body: WorldName) -> Dict:
    return {"name": call(rename_world, world, body.name)}


@router.delete("/{world}", status_code=204)
def remove_world(world: str) -> None:
    call(delete_world, world)


@router.get("/{world}/style")
def get_style(world: str) -> Dict:
    """The world's style (in ``world.json``): every image generated in it uses this style."""
    return {"style": call(read_style, world)}


@router.put("/{world}/style")
def put_style(world: str, body: Style) -> Dict:
    check_world(world)
    call(write_style, world, body.style)
    return {"style": read_style(world)}
