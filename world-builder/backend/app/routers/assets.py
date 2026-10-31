"""Characters, objects and locations: create, edit, and generate their variations. Assets live in each world's ``world.json``.

Every image is rendered landscape at high quality, by one provider. A
character or object variation is rendered from the asset's preferred image (the
design to keep) once there is one. A location's variations are the fixed views
of ``LOCATION_VIEWS``: the establishing view from the description, the others
from the establishing view. Nothing here removes a file.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Dict, List, Optional, Tuple

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.assets import library, story
from app.assets.generation import (
    ASPECT_RATIOS, DEFAULT_FINAL_PROVIDER, DEFAULT_PROVIDER, FINAL_PROVIDERS, PROVIDERS, generate_image,
)
from app.assets.prompt_manager import ASSET_DIRS, LOCATION_VIEWS, STYLES, build_prompt, variation_description
from app.assets.worlds import DEFAULT_WORLD, list_worlds, read_style, slugify, world_dir

router = APIRouter(prefix="/assets", tags=["assets"])

#: Asset types whose variations are named freely. Locations have their fixed views instead.
VARIABLE_TYPES = ("character", "object")
ESTABLISHING = next(iter(LOCATION_VIEWS))
#: How many variations of one asset render at once. Provider rate limits are the ceiling.
PARALLEL_RENDERS = 4


class NewAsset(BaseModel):
    world: str
    asset_type: str
    name: str
    description: str


class AssetEdit(BaseModel):
    world: str
    asset_type: str
    name: str
    new_name: Optional[str] = None
    description: Optional[str] = None
    preferred: Optional[str] = None


class Regenerate(BaseModel):
    world: str
    asset_type: str
    name: str
    #: One variation, or every one when left out.
    variation: Optional[str] = None
    provider: str = DEFAULT_PROVIDER


def _check(world: str, asset_type: str, allowed=tuple(ASSET_DIRS)) -> None:
    if world not in list_worlds():
        raise HTTPException(404, f"no world called {world!r}")
    if asset_type not in allowed:
        raise HTTPException(422, f"asset_type must be one of {sorted(allowed)}")


def check_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise HTTPException(422, f"provider must be one of {sorted(PROVIDERS)}")


def _asset(world: str, asset_type: str, name: str) -> Dict:
    asset = library.get_asset(world, asset_type, name)
    if asset is None:
        raise HTTPException(404, f"no {asset_type} called {name!r}")
    return asset


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _keep_uploads(world: str, label: str, uploads: List[UploadFile]) -> List[Path]:
    """Save uploaded references in the world's ``references/`` folder, so a regenerate can use them again."""
    directory = library.references_dir(world)
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, upload in enumerate(uploads):
        # Keep the extension: both providers read the image type off it.
        suffix = Path(upload.filename or "").suffix.lower() or ".png"
        path = directory / f"{uuid.uuid4().hex[:8]}-{label}-ref{index + 1}{suffix}"
        path.write_bytes(upload.file.read())
        paths.append(path)
    return paths


def _anchor(world: str, asset_type: str, asset: Dict, variation: str) -> Optional[Path]:
    """The image a variation is drawn from: a location's establishing view, or the preferred image. Never itself."""
    if asset_type == "location":
        candidates = [ESTABLISHING, asset["preferred"]] if variation != ESTABLISHING else []
    else:
        candidates = [asset["preferred"]]
    for name in candidates:
        source = library.variation_named(asset, name)
        if source and name != variation and (path := library.image_path(world, asset_type, source)).is_file():
            return path
    return None


def _render(world: str, asset_type: str, asset: Dict, variation: str, change: str, provider: str,
            uploads: List[Path]) -> Path:
    """Render one variation of ``asset`` (as ``world.json`` has it now). Raises 502 if the provider fails."""
    style = read_style(world)
    subject = asset["description"] or asset["name"].replace("_", " ")
    anchor = _anchor(world, asset_type, asset, variation)
    options: Dict = {}
    if asset_type == "location":
        description = subject
        references, clause = ([anchor], "view") if anchor else (uploads, "location")
        options["view"] = variation
    elif anchor:
        description = variation_description(subject, variation, change or variation.replace("_", " "))
        references, clause = [anchor, *uploads], "variation"
    else:
        description = f"{subject}\n\n{change}".strip()
        references, clause = uploads, asset_type
    try:
        build_prompt(asset_type, description, style)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        return generate_image(
            asset_type=asset_type, label=f"{asset['name']}-{variation}", description=description, style=style,
            directory=world_dir(world) / ASSET_DIRS[asset_type], provider=provider, references=references,
            clause=clause, **options,
        )
    except Exception as exc:  # any provider failure: the client gets the reason
        raise HTTPException(502, f"{provider}: {exc}") from exc


def _render_and_save(world: str, asset_type: str, name: str, variation: str, change: str, provider: str,
                     uploads: List[Path]) -> Dict:
    asset = _asset(world, asset_type, name)
    path = _render(world, asset_type, asset, variation, change, provider, uploads)
    entry = {
        "name": variation, "description": change, "provider": provider,
        "image": path.name, "references": [p.name for p in uploads],
    }
    return library.put_variation(world, asset_type, name, entry)


def _render_many(world: str, asset_type: str, name: str, jobs: List[Tuple[str, str, List[Path]]],
                 provider: str, anchor: Optional[str] = None) -> Dict:
    """Render ``(variation, change, uploads)`` jobs, each saved as it lands.

    The ``anchor`` job (the image the others are drawn from) renders first, on
    its own; if it fails nothing else is tried. The rest render in parallel.
    """
    first = [job for job in jobs if job[0] == anchor]
    rest = [job for job in jobs if job[0] != anchor]

    def render(job: Tuple[str, str, List[Path]]) -> Optional[str]:
        variation, change, uploads = job
        try:
            _render_and_save(world, asset_type, name, variation, change, provider, uploads)
        except HTTPException as exc:
            return f"{variation} failed: {exc.detail}"
        return None

    failures = [failure for failure in map(render, first) if failure]
    if not failures and rest:
        with ThreadPoolExecutor(max_workers=PARALLEL_RENDERS) as pool:
            failures = [failure for failure in pool.map(render, rest) if failure]
    return {"asset": library.view_asset(world, asset_type, name), "warning": "; ".join(failures) or None}


@router.get("/options")
def options() -> Dict:
    """What the forms offer. ``styles`` are the presets a new world can start from; ``aspect_ratios`` are for episodes."""
    return {
        "asset_types": list(ASSET_DIRS),
        "styles": STYLES,
        "providers": PROVIDERS,
        "default_provider": DEFAULT_PROVIDER,
        "final_providers": list(FINAL_PROVIDERS),
        "default_final_provider": DEFAULT_FINAL_PROVIDER,
        "aspect_ratios": list(ASPECT_RATIOS),
        "shot_types": story.SHOT_TYPES,
        "location_views": list(LOCATION_VIEWS),
        "default_world": DEFAULT_WORLD,
    }


@router.get("")
def get_assets(world: str, asset_type: Optional[str] = None) -> Dict:
    """One world's characters, objects and locations, in ``world.json`` order, each with its variations."""
    _check(world, asset_type or "character")
    return {"assets": _call(library.list_assets, world, asset_type)}


@router.post("", status_code=201)
def create(body: NewAsset) -> Dict:
    """A new asset: a name and a description, with no images yet."""
    _check(body.world, body.asset_type)
    name = slugify(body.name)
    if not name:
        raise HTTPException(422, "That name has no usable characters - try letters or digits.")
    if not body.description.strip():
        raise HTTPException(422, "Describe the asset.")
    return {"asset": _call(library.create_asset, body.world, body.asset_type, name, body.description.strip())}


@router.patch("")
def edit(body: AssetEdit) -> Dict:
    """Rename an asset, change its description, or pick its preferred variation. ``world.json`` only.

    A rename also updates every scene that points at the asset.
    """
    _check(body.world, body.asset_type)
    _asset(body.world, body.asset_type, body.name)
    if body.description is not None and not body.description.strip():
        raise HTTPException(422, "The description must not be empty.")
    name = _call(library.edit_asset, body.world, body.asset_type, body.name,
                 new_name=body.new_name, description=body.description, preferred=body.preferred)
    if name != body.name:
        story.rename_references(body.world, ASSET_DIRS[body.asset_type], body.name, name)
    return {"asset": library.view_asset(body.world, body.asset_type, name)}


@router.delete("", status_code=204)
def remove(world: str, asset_type: str, name: str, variation: Optional[str] = None) -> None:
    """Drop an asset (or one of its variations) from ``world.json``. Its image files stay in the data folder."""
    _check(world, asset_type)
    if variation:
        _call(library.remove_variation, world, asset_type, name, variation)
    else:
        _call(library.remove_asset, world, asset_type, name)


@router.post("/variations")
def add_variation(
    world: Annotated[str, Form()],
    asset_type: Annotated[str, Form()],
    name: Annotated[str, Form()],
    variation: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    provider: Annotated[str, Form()] = DEFAULT_PROVIDER,
    uploads: Annotated[List[UploadFile], File()] = [],
) -> Dict:
    """Generate a named variation of a character or object (new clothes, older, broken...).

    The first one is drawn from the asset's description; later ones from its
    preferred image, with ``description`` saying what changes. ``uploads`` are
    inspiration, kept for regenerating.
    """
    _check(world, asset_type, VARIABLE_TYPES)
    check_provider(provider)
    asset = _asset(world, asset_type, name)
    slug = slugify(variation)
    if not slug:
        raise HTTPException(422, "Give the variation a name.")
    if library.variation_named(asset, slug) is not None:
        raise HTTPException(409, f"{name!r} already has a variation called {slug!r}.")
    references = _keep_uploads(world, f"{name}-{slug}", uploads)
    return {"asset": _render_and_save(world, asset_type, name, slug, description.strip(), provider, references)}


@router.post("/views")
def add_views(
    world: Annotated[str, Form()],
    name: Annotated[str, Form()],
    provider: Annotated[str, Form()] = DEFAULT_PROVIDER,
    uploads: Annotated[List[UploadFile], File()] = [],
) -> Dict:
    """Render every fixed view a location is missing: the establishing view first, when missing, then the rest in parallel.

    ``uploads`` go to the establishing view (when it is missing); the other
    views are drawn from it. Views already made are kept if another one fails.
    """
    _check(world, "location")
    check_provider(provider)
    asset = _asset(world, "location", name)
    missing = [view for view in LOCATION_VIEWS if library.variation_named(asset, view) is None]
    if not missing:
        raise HTTPException(409, f"{name!r} already has every view - regenerate one instead.")
    references = _keep_uploads(world, f"{name}-{ESTABLISHING}", uploads) if ESTABLISHING in missing else []
    jobs = [(view, "", references if view == ESTABLISHING else []) for view in missing]
    return _render_many(world, "location", name, jobs, provider, anchor=ESTABLISHING)


@router.post("/regenerate")
def regenerate(body: Regenerate) -> Dict:
    """Re-render one variation, or all of them, from the asset's current description and their saved references.

    "All" renders the preferred image (or a location's establishing view)
    first, so the others, rendered in parallel after it, are drawn from its new render.
    Each variation points at its new image; the old file stays on disk.
    """
    _check(body.world, body.asset_type)
    check_provider(body.provider)
    asset = _asset(body.world, body.asset_type, body.name)
    first = None
    if body.variation is not None:
        if library.variation_named(asset, body.variation) is None:
            raise HTTPException(404, f"{body.name!r} has no variation called {body.variation!r}")
        names = [body.variation]
    else:
        first = ESTABLISHING if body.asset_type == "location" else asset["preferred"]
        names = sorted((v["name"] for v in asset["variations"]), key=lambda n: n != first)
        if not names:
            raise HTTPException(409, f"{body.name!r} has no variations yet.")
    jobs = []
    for variation_name in names:
        variation = library.variation_named(asset, variation_name)
        jobs.append((variation_name, variation["description"], library.reference_files(body.world, variation)))
    return _render_many(body.world, body.asset_type, body.name, jobs, body.provider, anchor=first)
