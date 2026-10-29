"""Asset library and generation.

Every path in and out is relative to the shared data folder: the frontend opens
the files itself, read-only, from its own mount of that folder.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app import jobs
from app.assets.generation import ASPECT_RATIOS, DEFAULT_WORLD, IMG_DIR, QUALITY, AssetImageGenerator
from app.assets.library import (
    REFERENCE_TYPES,
    delete_asset,
    facets,
    filter_assets,
    list_assets,
    parse_stem,
)
from app.assets.prompt_manager import ASSET_DIRS, STYLES, build_prompt
from app.assets.worlds import copy_asset, list_worlds, move_asset, slugify
from app.settings import resolve

router = APIRouter(prefix="/assets", tags=["assets"])

#: Only the friendly spellings. ``ASPECT_RATIOS`` also holds the raw `16:9`,
#: `1:1` and `9:16` keys, which would show up as duplicate options.
ASPECT_RATIO_OPTIONS = ("landscape", "square", "portrait")

#: An uploaded reference, read in the request: (filename, bytes).
Blob = Tuple[str, bytes]

#: One generator for the whole process. The constructor only reads the
#: environment; both API clients are lazy, so a missing key fails per-provider at
#: call time rather than here.
_generator = AssetImageGenerator()


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
    if not path.is_relative_to(IMG_DIR.resolve()) or not path.is_file():
        raise HTTPException(404, f"not a library asset: {relative_path}")
    return path


@router.get("/options")
def options() -> Dict:
    """Everything the Create form offers. ``None`` in ``styles`` is the
    follow-the-references mode; it is listed last so it is never the default."""
    return {
        "asset_types": list(ASSET_DIRS),
        "reference_types": list(REFERENCE_TYPES),
        "styles": list(STYLES) + [None],
        "aspect_ratios": list(ASPECT_RATIO_OPTIONS),
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
    """One world's assets (or every world's), newest first.

    ``facets`` are built from the unfiltered listing, so the filter options stay
    put while a filter is applied.
    """
    if asset_type is not None and asset_type not in ASSET_DIRS:
        raise HTTPException(400, f"unknown asset type: {asset_type}")
    everything = list_assets(world=world)
    visible = filter_assets(everything, asset_type=asset_type, style=style, provider=provider)
    return {
        "assets": [asset.to_dict() for asset in visible],
        "facets": facets(everything),
        "total": len(everything),
    }


@router.delete("", status_code=204)
def remove_asset(path: str) -> None:
    delete_asset(_library_path(path))


@router.post("/transfer")
def transfer(request: TransferRequest) -> Dict:
    """Move or duplicate assets into another world.

    Per-file failures are collected rather than aborting the batch: a single
    name already taken in the target should not strand the other twenty.
    """
    if request.target not in list_worlds():
        raise HTTPException(404, f"no world called {request.target!r}")

    done: List[str] = []
    failed: List[str] = []
    for relative_path in request.paths:
        try:
            path = _library_path(relative_path)
            if request.copy_assets:
                copy_asset(path, request.target)
            else:
                move_asset(path, request.target)
            done.append(relative_path)
        except (HTTPException, ValueError, OSError) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else exc
            failed.append(f"{Path(relative_path).name} - {detail}")
    return {"done": done, "failed": failed}


def _run(
    fields: Dict,
    blobs: Sequence[Blob],
    library_refs: Sequence[Path],
    progress,
) -> Dict:
    """The worker. Touches only the generator and the disk.

    Uploads are written into a ``TemporaryDirectory`` owned by this call rather
    than by the request, so nothing disappears underneath a generation the user
    has walked away from. The extension is preserved because Gemini reads the
    mime type off the filename and OpenAI infers it from the multipart upload - a
    suffix-less file would send a JPEG labelled as PNG.
    """
    progress("Generating...")
    with tempfile.TemporaryDirectory() as tmpdir:
        references = list(library_refs)
        for index, (filename, data) in enumerate(blobs):
            suffix = Path(filename).suffix.lower() or ".png"
            path = Path(tmpdir) / f"reference_{index}{suffix}"
            path.write_bytes(data)
            references.append(path)

        result = _generator.generate_asset(
            fields["asset_type"],
            fields["name"],
            fields["description"],
            fields["style"],
            reference_images=references,
            aspect_ratio=fields["aspect_ratio"],
            quality=fields["quality"],
            provider=fields["provider"],
            world=fields["world"],
        )

    # ``generate_asset`` returns a bare Path for a single provider and the
    # per-provider dict for "both"; jobs always carry the dict shape.
    results = result if isinstance(result, dict) else {fields["provider"]: result}

    landed = [
        parse_stem(path.stem, fields["asset_type"], fields["world"], path, path.stat().st_mtime)
        for path in results.values()
        if isinstance(path, Path)
    ]
    failed = {
        provider: str(value) for provider, value in results.items() if isinstance(value, Exception)
    }
    text = "; ".join(f"{provider}: {message}" for provider, message in failed.items())
    if not landed:
        raise RuntimeError(text)
    # One provider of a "both" run died. The other image was still saved, so
    # this must not read as a failed job - but it did cost a call.
    return {"assets": [asset.to_dict() for asset in landed], "warning": text or None}


@router.post("/generate", status_code=202)
async def generate(
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
    """Start one generation in the background and return its job.

    Leave ``style`` out to take the art style from the references. Characters,
    objects and locations take ``uploads`` (never saved); scenes take
    ``references``, paths of existing assets in the same world.

    Everything that can be checked without a paid call is checked here, so a
    bad form is a 4xx now rather than a failed job later.
    """
    slug = slugify(name)
    if not slug:
        raise HTTPException(422, "That name has no usable characters - try letters or digits.")
    if world not in list_worlds():
        raise HTTPException(404, f"no world called {world!r}")
    if aspect_ratio not in ASPECT_RATIOS:
        raise HTTPException(422, f"aspect_ratio must be one of {sorted(ASPECT_RATIOS)}")
    if quality not in QUALITY:
        raise HTTPException(422, f"quality must be one of {sorted(QUALITY)}")
    if provider not in ("openai", "gemini", "both"):
        raise HTTPException(422, "provider must be 'openai', 'gemini' or 'both'")

    library_refs = [_library_path(path) for path in references]
    blobs = [(upload.filename or "reference.png", await upload.read()) for upload in uploads]
    try:
        build_prompt(asset_type, description, style, with_references=bool(library_refs or blobs))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    fields = {
        "asset_type": asset_type,
        "name": slug,
        "description": description.strip(),
        "style": style,
        "aspect_ratio": aspect_ratio,
        "quality": quality,
        "provider": provider,
        "world": world,
    }
    label = f"{slug} · {asset_type} · {world} · {provider}"
    job = jobs.submit(
        "asset",
        label,
        lambda progress: _run(fields, blobs, library_refs, progress),
        world=world,
    )
    return job.to_dict()
