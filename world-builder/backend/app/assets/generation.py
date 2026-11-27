"""Image generation, all through Runware: OpenAI GPT-Image-2.6 (Sunburst or Flare), Google Nano Banana 2.1, or Black Forest Labs FLUX 3 Image or FLUX 3 Image Klein.

One model renders each image. Every model is reached with the one Runware key
and the same ``imageInference`` task; only the fields a model takes differ.
Files are written to the folder the caller passes (an asset-type folder, or a
shot folder for final frames) as ``{uuid8}-{label}``, as JPEG. Characters and
objects render at 2K and high quality; a location renders as one wide 3:1
panorama of the whole place, which final frames crop into whatever angle a shot
needs. Final frames render at 1K (the size of the 768p video they become), the
GPT models at medium quality. Every render gets a new uuid, so nothing is ever
overwritten. Runware reports what each task billed, so every logged cost is exact.
"""

from __future__ import annotations

import base64
import mimetypes
import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from PIL import Image

from app.assets import costs
from app.assets.prompt_manager import build_prompt

RUNWARE_URL = "https://api.runware.ai/v1"

#: Model key (what ``world.json``, ``episode.json`` and the API call ``provider``) -> its Runware model,
#: the name the forms show, and the most reference images it takes. Price hints are rough; the exact
#: figure is logged after each render.
MODELS: Dict[str, Dict[str, Any]] = {
    "gpt-image-sunburst": {
        "air": "openai:gpt-image@2.6-sunburst", "family": "gpt",
        "label": "GPT-Image-2.6 Sunburst (detailed, precise; ~$0.04-0.19/image)", "max_references": 16,
    },
    "gpt-image-flare": {
        "air": "openai:gpt-image@2.6-flare", "family": "gpt",
        "label": "GPT-Image-2.6 Flare (fast iteration; ~$0.06-0.19/image)", "max_references": 16,
    },
    "nano-banana": {
        "air": "google:nano-banana@2.1", "family": "nano-banana",
        "label": "Nano Banana 2.1 (~$0.03-0.05/image)", "max_references": 14,
    },
    "flux-3": {
        "air": "bfl:flux@3-image", "family": "flux-3",
        "label": "FLUX 3 Image (~$0.05-0.10/image)", "max_references": 10,
    },
    "flux-3-klein": {
        "air": "bfl:flux@3-image-klein", "family": "flux-3-klein",
        "label": "FLUX 3 Image Klein (cheapest and fast, ~$0.003-0.02/image)", "max_references": 4,
    },
}
#: The name each model shows in the forms.
PROVIDERS = {key: model["label"] for key, model in MODELS.items()}
DEFAULT_PROVIDER = "gpt-image-sunburst"
#: What episodes and variations made before everything went through Runware called their model.
LEGACY_PROVIDERS = {
    "openai": "gpt-image-sunburst", "gemini": "nano-banana", "runware": "flux-3-klein", "flux-klein": "flux-3-klein",
}
#: Rough USD per final frame (1K), shown on the Storyboard until the world's cost log has real ones.
PRICE_ESTIMATES = {"gpt-image-sunburst": 0.07, "gpt-image-flare": 0.17, "nano-banana": 0.034, "flux-3": 0.048,
                   "flux-3-klein": 0.004}
#: The models a final frame can use (all of them), and the default one.
FINAL_PROVIDERS = tuple(PROVIDERS)
DEFAULT_FINAL_PROVIDER = "nano-banana"


def model_key(provider: Optional[str]) -> Optional[str]:
    """A model key, translating the provider names older files used (``openai``, ``gemini``, ``runware``)."""
    return LEGACY_PROVIDERS.get(provider or "", provider)


#: Friendly name -> ratio. Locations always render as ``panorama``.
ASPECT_RATIOS = {"landscape": "16:9", "square": "1:1", "portrait": "9:16", "panorama": "3:1"}

#: Model family -> resolution -> ratio -> (width, height). The GPT models take any size (sides
#: divisible by 16, 1:3 to 3:1); Nano Banana only the sizes its table lists, and no 3:1 (its
#: "3:1" is 21:9); FLUX 3 Image likewise (its presets, 21:9 again); FLUX 3 Klein takes
#: any size up to 4096 a side (multiples of 16). 1K matches the 768p video.
SIZES: Dict[str, Dict[str, Dict[str, tuple[int, int]]]] = {
    "gpt": {
        "2K": {"16:9": (2048, 1152), "1:1": (2048, 2048), "9:16": (1152, 2048), "3:1": (3072, 1024)},
        "1K": {"16:9": (1360, 768), "1:1": (1024, 1024), "9:16": (768, 1360), "3:1": (1776, 592)},
    },
    "nano-banana": {
        "2K": {"16:9": (2752, 1536), "1:1": (2048, 2048), "9:16": (1536, 2752), "3:1": (3168, 1344)},
        "1K": {"16:9": (1376, 768), "1:1": (1024, 1024), "9:16": (768, 1376), "3:1": (1584, 672)},
    },
    "flux-3": {
        "2K": {"16:9": (2736, 1536), "1:1": (2048, 2048), "9:16": (1536, 2736), "3:1": (3136, 1344)},
        "1K": {"16:9": (1360, 768), "1:1": (1024, 1024), "9:16": (768, 1360), "3:1": (1568, 672)},
    },
    "flux-3-klein": {
        "2K": {"16:9": (2048, 1152), "1:1": (2048, 2048), "9:16": (1152, 2048), "3:1": (3072, 1024)},
        "1K": {"16:9": (1360, 768), "1:1": (1024, 1024), "9:16": (768, 1360), "3:1": (1776, 592)},
    },
}

#: Quality -> (GPT ``settings.quality``, Nano Banana ``settings.thinkingLevel``). FLUX 3 has no quality setting.
QUALITY: dict[str, tuple[str, Optional[str]]] = {
    "low": ("low", None),
    "medium": ("medium", None),
    "high": ("high", "high"),
    # Final frames: GPT at medium (enough for a 768p video, and much cheaper), Nano Banana unchanged.
    "frame": ("medium", "high"),
}

#: Characters and objects are always rendered like this; locations as a ``panorama``;
#: final frames take their ratio from the episode.
ASSET_ASPECT_RATIO = "landscape"
ASSET_QUALITY = "high"
ASSET_RESOLUTION = "2K"
#: Final frames only feed the video, so they render at its size.
FINAL_QUALITY = "frame"
FINAL_RESOLUTION = "1K"

_EXTENSIONS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}


def _api_key(name: str) -> str:
    key = os.environ.get(name)
    if not key:
        raise RuntimeError(f"{name} is not set (see backend/.env)")
    return key


def _mime_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "image/png"


def _base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def image_size(provider: str, aspect_ratio: str, resolution: str) -> tuple[int, int]:
    """The (width, height) ``provider`` renders for an aspect ratio name and a resolution."""
    return SIZES[MODELS[provider]["family"]][resolution][ASPECT_RATIOS[aspect_ratio]]


def runware_task(provider: str, prompt: str, size: tuple[int, int], quality: str,
                 references: Sequence[str] = ()) -> Dict[str, Any]:
    """The ``imageInference`` task for one image. ``references`` are already data URIs (or URLs)."""
    model = MODELS[provider]
    gpt_quality, thinking_level = QUALITY[quality]
    width, height = size
    task: Dict[str, Any] = {
        "taskType": "imageInference",
        "taskUUID": str(uuid.uuid4()),
        "model": model["air"],
        "positivePrompt": prompt,
        "width": width,
        "height": height,
        "numberResults": 1,
        "outputType": "base64Data",
        "outputFormat": "JPG",
        "outputQuality": 95,
        "deliveryMethod": "sync",
        # Reports the exact USD this task billed, on the image result.
        "includeCost": True,
    }
    if model["family"] == "gpt":
        task["settings"] = {"quality": gpt_quality}
    elif model["family"] == "nano-banana":
        if thinking_level:
            task["settings"] = {"thinkingLevel": thinking_level}
    # FLUX 3 takes no quality setting: Klein runs its default 16 steps, FLUX 3 Image has no steps at all.
    if references:
        task["inputs"] = {"referenceImages": list(references)}
    return task


def _runware_bytes(task: Dict[str, Any]) -> tuple[bytes, Optional[float]]:
    import httpx

    response = httpx.post(
        RUNWARE_URL, json=[task], headers={"Authorization": f"Bearer {_api_key('RUNWARE_API_KEY')}"}, timeout=300
    )
    body = response.json()
    if body.get("errors"):
        raise RuntimeError("; ".join(error.get("message", str(error)) for error in body["errors"]))
    response.raise_for_status()
    images = [item for item in body.get("data", []) if item.get("imageBase64Data")]
    if not images:
        raise RuntimeError("Runware returned no image data")
    return base64.b64decode(images[0]["imageBase64Data"]), images[0].get("cost")


def generate_image(
    world: str,
    asset_type: str,
    label: str,
    description: str,
    style: str,
    directory: Path,
    provider: str,
    references: Sequence[Path] = (),
    clause: Optional[str] = None,
    view: str = "panorama",
    aspect_ratio: str = ASSET_ASPECT_RATIO,
    quality: str = ASSET_QUALITY,
    resolution: str = ASSET_RESOLUTION,
) -> Path:
    """Render one image (an asset, or a shot's ``"final"`` frame) with one model and save it as ``{uuid8}-{label}`` in ``directory``.

    ``provider`` is a model key (see :data:`MODELS`; older names are translated).
    ``clause`` says how ``references`` are used (see ``build_prompt``). Raises
    if Runware fails; nothing is written then. What it billed is appended to
    ``world``'s cost log.
    """
    provider = model_key(provider)
    if provider not in MODELS:
        raise ValueError(f"provider must be one of {sorted(MODELS)}")
    references = list(references)[: MODELS[provider]["max_references"]]
    prompt = build_prompt(asset_type, description, style, clause=clause if references else None, view=view)
    task = runware_task(
        provider, prompt, image_size(provider, aspect_ratio, resolution), quality,
        [f"data:{_mime_type(path)};base64,{_base64(path)}" for path in references],
    )
    data, usd = _runware_bytes(task)
    image_format = Image.open(BytesIO(data)).format
    path = directory / f"{uuid.uuid4().hex[:8]}-{label}{_EXTENSIONS.get(image_format, '.jpg')}"
    directory.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    try:
        costs.record(world, asset_type, label, provider, usd, estimated=False)
    except Exception:
        pass  # a logging bug must never cost an already-paid-for render.
    return path
