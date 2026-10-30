"""Asset library and generation. Every path in and out is relative to the data folder."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.assets.generation import ASPECT_RATIOS, PROVIDERS, QUALITY, generate_asset
from app.assets.library import REFERENCE_TYPES, facets, is_asset, list_assets, parse_asset
from app.assets.prompt_manager import ASSET_DIRS, STYLES, build_prompt
from app.assets.worlds import DEFAULT_WORLD, list_worlds, slugify, transfer_asset
from app.settings import DATA_DIR, resolve

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
    """Everything the Create form offers. ``None`` in ``styles`` means "follow the references"."""
    return {
        "asset_types": list(ASSET_DIRS),
        "reference_types": list(REFERENCE_TYPES),
        "styles": list(STYLES) + [None],
        "aspect_ratios": list(ASPECT_RATIOS),
        "qualities": list(QUALITY),
        "default_world": DEFAULT_WORLD,
    }


@router.get("")
def get_assets(
    world: Optional[str] = None,
    asset_type: Optional[str] = None,
    style: Optional[str] = None,
    provider: Optional[str] = None,
) -> Dict:
    """One world's assets (or every world's), newest first. ``facets`` ignore the filters."""
    if asset_type is not None and asset_type not in ASSET_DIRS:
        raise HTTPException(400, f"unknown asset type: {asset_type}")
    everything = list_assets(world)
    wanted = {"asset_type": asset_type, "style": style, "provider": provider}
    visible = [a for a in everything if all(v is None or a[k] == v for k, v in wanted.items())]
    return {"assets": visible, "facets": facets(everything), "total": len(everything)}


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


@router.post("/generate")
def generate(
    asset_type: Annotated[str, Form()],
    name: Annotated[str, Form()],
    description: Annotated[str, Form()],
    world: Annotated[str, Form()] = DEFAULT_WORLD,
    style: Annotated[Optional[str], Form()] = None,
    aspect_ratio: Annotated[str, Form()] = "landscape",
    quality: Annotated[str, Form()] = "low",
    provider: Annotated[str, Form()] = "both",
    references: Annotated[List[str], Form()] = [],
    uploads: Annotated[List[UploadFile], File()] = [],
) -> Dict:
    """Generate one asset and return what was saved. Takes as long as the providers do.

    Leave ``style`` out to take the art style from the references. Characters,
    objects and locations take ``uploads`` (never saved); scenes take
    ``references``, paths of existing assets in the same world.
    """
    slug = slugify(name)
    if not slug:
        raise HTTPException(422, "That name has no usable characters - try letters or digits.")
    _check_world(world)
    if aspect_ratio not in ASPECT_RATIOS:
        raise HTTPException(422, f"aspect_ratio must be one of {sorted(ASPECT_RATIOS)}")
    if quality not in QUALITY:
        raise HTTPException(422, f"quality must be one of {sorted(QUALITY)}")
    if provider not in (*PROVIDERS, "both"):
        raise HTTPException(422, "provider must be 'openai', 'gemini' or 'both'")

    library_refs = [_library_path(path) for path in references]
    for path in library_refs:
        if not path.is_relative_to(DATA_DIR / world):
            raise HTTPException(
                422,
                f"reference {path.name} belongs to another world; an asset in "
                f"{world!r} can only be built from {world!r} references",
            )
    try:
        build_prompt(asset_type, description, style, with_references=bool(library_refs or uploads))
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
            references=library_refs + upload_refs,
            aspect_ratio=aspect_ratio,
            quality=quality,
            provider=provider,
            world=world,
        )

    assets = [parse_asset(path, asset_type, world) for path in results.values() if isinstance(path, Path)]
    errors = "; ".join(f"{p}: {exc}" for p, exc in results.items() if isinstance(exc, Exception))
    if not assets:
        raise HTTPException(502, errors)
    # With provider="both", one provider may fail while the other image is saved.
    return {"assets": assets, "warning": errors or None}
