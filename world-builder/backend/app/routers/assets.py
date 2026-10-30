"""Characters, objects and locations: listing, generation, moves. Every path in and out is relative to the data folder."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.assets.generation import ASPECT_RATIOS, PROVIDERS, QUALITY, generate_asset
from app.assets.library import is_asset, list_assets, parse_asset
from app.assets.prompt_manager import ASSET_DIRS, STYLES, build_prompt
from app.assets.worlds import DEFAULT_WORLD, list_worlds, read_style, slugify, transfer_asset, world_dir
from app.settings import resolve

router = APIRouter(prefix="/assets", tags=["assets"])


class TransferRequest(BaseModel):
    paths: List[str]
    target: str
    copy_assets: bool = False


def _library_path(relative_path: str) -> Path:
    """Resolve a path the client sent, refusing anything that is not a library file."""
    try:
        path = resolve(relative_path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not is_asset(path):
        raise HTTPException(404, f"not a library asset: {relative_path}")
    return path


def _check_world(world: str) -> None:
    if world not in list_worlds():
        raise HTTPException(404, f"no world called {world!r}")


@router.get("/options")
def options() -> Dict:
    """What the forms offer. ``styles`` are the presets a new world can start from."""
    return {
        "asset_types": list(ASSET_DIRS),
        "styles": STYLES,
        "aspect_ratios": list(ASPECT_RATIOS),
        "qualities": list(QUALITY),
        "default_world": DEFAULT_WORLD,
    }


@router.get("")
def get_assets(world: Optional[str] = None, asset_type: Optional[str] = None) -> Dict:
    """One world's characters, objects and locations (or every world's), newest first."""
    if asset_type is not None and asset_type not in ASSET_DIRS:
        raise HTTPException(400, f"unknown asset type: {asset_type}")
    return {"assets": list_assets(world, asset_type)}


@router.delete("", status_code=204)
def remove_asset(path: str) -> None:
    _library_path(path).unlink()


@router.post("/transfer")
def transfer(request: TransferRequest) -> Dict:
    """Move or duplicate assets into another world. Per-file failures are reported, not raised."""
    _check_world(request.target)
    done: List[str] = []
    failed: List[str] = []
    for relative_path in request.paths:
        try:
            transfer_asset(_library_path(relative_path), request.target, copy=request.copy_assets)
            done.append(relative_path)
        except (HTTPException, ValueError, OSError) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else exc
            failed.append(f"{Path(relative_path).name} - {detail}")
    return {"done": done, "failed": failed}


def save_renders(results: Dict, asset_type: str, world: str) -> Dict:
    """Turn ``generate_asset`` results into a response; 502 only if every provider failed."""
    assets = [parse_asset(path, asset_type, world) for path in results.values() if isinstance(path, Path)]
    errors = "; ".join(f"{p}: {exc}" for p, exc in results.items() if isinstance(exc, Exception))
    if not assets:
        raise HTTPException(502, errors)
    # With provider="both", one provider may fail while the other image is saved.
    return {"assets": assets, "warning": errors or None}


def check_render_options(aspect_ratio: str, quality: str, provider: str) -> None:
    if aspect_ratio not in ASPECT_RATIOS:
        raise HTTPException(422, f"aspect_ratio must be one of {sorted(ASPECT_RATIOS)}")
    if quality not in QUALITY:
        raise HTTPException(422, f"quality must be one of {sorted(QUALITY)}")
    if provider not in (*PROVIDERS, "both"):
        raise HTTPException(422, "provider must be 'openai', 'gemini' or 'both'")


@router.post("/generate")
def generate(
    asset_type: Annotated[str, Form()],
    name: Annotated[str, Form()],
    description: Annotated[str, Form()],
    world: Annotated[str, Form()] = DEFAULT_WORLD,
    aspect_ratio: Annotated[str, Form()] = "landscape",
    quality: Annotated[str, Form()] = "low",
    provider: Annotated[str, Form()] = "both",
    uploads: Annotated[List[UploadFile], File()] = [],
) -> Dict:
    """Generate one character, object or location in the world's style. Takes as long as the providers do.

    ``uploads`` are inspiration references, used for the call and never saved.
    """
    slug = slugify(name)
    if not slug:
        raise HTTPException(422, "That name has no usable characters - try letters or digits.")
    _check_world(world)
    check_render_options(aspect_ratio, quality, provider)
    if asset_type not in ASSET_DIRS:
        raise HTTPException(422, f"asset_type must be one of {sorted(ASSET_DIRS)}")
    style = read_style(world)
    try:
        build_prompt(asset_type, description, style, with_references=bool(uploads))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    with tempfile.TemporaryDirectory() as tmpdir:
        # Keep the extension: both providers read the image type off it.
        upload_refs = []
        for index, upload in enumerate(uploads):
            path = Path(tmpdir) / f"reference_{index}{Path(upload.filename or '').suffix.lower() or '.png'}"
            path.write_bytes(upload.file.read())
            upload_refs.append(path)

        results = generate_asset(
            asset_type,
            slug,
            description.strip(),
            style,
            world_dir(world) / ASSET_DIRS[asset_type],
            references=upload_refs,
            aspect_ratio=aspect_ratio,
            quality=quality,
            provider=provider,
        )
    return save_renders(results, asset_type, world)
