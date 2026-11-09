"""Image generation with OpenAI (gpt-image-2), Gemini (Nano Banana 2) or Runware (Flux 2 Klein 4B), one provider per image.

Files are written to the folder the caller passes (an asset-type folder, or a
scene folder for shots) as ``{uuid8}-{label}``, with the extension of the
returned bytes (OpenAI PNG, Gemini and Runware JPEG). Characters, objects and
locations render at 2K and high quality: they are made once and every frame is
built from them. Final frames render at 1K (the size of the 768p video they
become) with OpenAI at medium quality. Every render gets a new uuid, so nothing
is ever overwritten.
"""

from __future__ import annotations

import base64
import mimetypes
import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Optional, Sequence

from PIL import Image

from app.assets import costs
from app.assets.prompt_manager import build_prompt

OPENAI_MODEL = "gpt-image-2"
GEMINI_MODEL = "gemini-nano-banana-2.1"
RUNWARE_MODEL = "runware:400@4"
RUNWARE_URL = "https://api.runware.ai/v1"
#: Provider -> the name the forms show. The price hints are rough (landscape, 2K, high quality - what
#: character, object and location renders always use); the exact figure is logged after each render.
PROVIDERS = {
    "openai": f"OpenAI {OPENAI_MODEL} (billed per token, varies)",
    "gemini": "Gemini Nano Banana 2 (~$0.05/image)",
    "runware": "Runware Flux 2 Klein 4B (~$0.015/image)",
}
DEFAULT_PROVIDER = "openai"
#: Rough USD per final frame (1K), shown on the Storyboard until the world's cost log has real ones.
#: OpenAI bills per token, so it has no fixed figure.
PRICE_ESTIMATES = {"openai": None, "gemini": 0.034, "runware": 0.007}
#: The models a final frame can use (all of them), and the default one.
FINAL_PROVIDERS = tuple(PROVIDERS)
DEFAULT_FINAL_PROVIDER = "gemini"

#: Friendly name -> the ratio Gemini takes.
ASPECT_RATIOS = {"landscape": "16:9", "square": "1:1", "portrait": "9:16"}

#: Resolution -> ratio -> the (width, height) OpenAI and Runware render (both sides divisible by 16).
#: Gemini takes the resolution name itself. 1K matches the 768p video a final frame becomes.
SIZES = {
    "2K": {"16:9": (2048, 1152), "1:1": (2048, 2048), "9:16": (1152, 2048)},
    "1K": {"16:9": (1360, 768), "1:1": (1024, 1024), "9:16": (768, 1360)},
}

#: Provider -> the most reference images it takes (the API limits).
MAX_REFERENCES = {"runware": 4, "openai": 16, "gemini": 14}

#: Quality -> (OpenAI ``quality``, Gemini ``thinking_level``). The Gemini model
#: rejects every thinking level but "high", so below that nothing is sent.
#: Runware has no quality setting: it always renders the same way.
QUALITY: dict[str, tuple[str, Optional[str]]] = {
    "low": ("low", None),
    "medium": ("medium", None),
    "high": ("high", "high"),
    # Final frames: OpenAI at medium (enough for a 768p video, and much cheaper), Gemini unchanged.
    "frame": ("medium", "high"),
}

#: Characters, objects and locations are always rendered like this; final
#: frames take their ratio from the episode, at high quality.
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


def _openai_bytes(prompt: str, size: str, quality: str, references: list[Path]) -> tuple[bytes, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=_api_key("OPENAI_API_KEY"))
    options = dict(model=OPENAI_MODEL, prompt=prompt, size=size, quality=quality, output_format="png")
    if references:
        handles = [path.open("rb") for path in references]
        try:
            result = client.images.edit(image=handles, **options)
        finally:
            for handle in handles:
                handle.close()
    else:
        result = client.images.generate(**options)

    if not result.data or not result.data[0].b64_json:
        raise RuntimeError("OpenAI returned no image data")
    return base64.b64decode(result.data[0].b64_json), result.usage


def _gemini_bytes(
    prompt: str, ratio: str, image_size: str, thinking_level: Optional[str], references: list[Path]
) -> tuple[bytes, Any]:
    from google import genai

    client = genai.Client(api_key=_api_key("GEMINI_API_KEY"))
    model_input: str | list[dict] = prompt
    if references:
        model_input = [{"type": "text", "text": prompt}] + [
            {
                "type": "image",
                "data": _base64(path),
                "mime_type": _mime_type(path),
            }
            for path in references
        ]
    config: dict[str, Any] = {}
    if thinking_level:
        config["generation_config"] = {"thinking_level": thinking_level}

    interaction = client.interactions.create(
        model=GEMINI_MODEL,
        input=model_input,
        # image/jpeg is the only image mime type the API accepts.
        response_format={"type": "image", "aspect_ratio": ratio, "image_size": image_size, "mime_type": "image/jpeg"},
        **config,
    )
    # Success has been reported under more than one status, so check for the image itself.
    output = getattr(interaction, "output_image", None)
    if output is None or not output.data:
        raise RuntimeError(f"Gemini returned no image data (status={getattr(interaction, 'status', None)})")
    return base64.b64decode(output.data), interaction.usage


def _runware_bytes(prompt: str, size: tuple[int, int], references: list[Path]) -> tuple[bytes, Optional[float]]:
    import httpx

    width, height = size
    task: dict[str, Any] = {
        "taskType": "imageInference",
        "taskUUID": str(uuid.uuid4()),
        "model": RUNWARE_MODEL,
        "positivePrompt": prompt,
        "width": width,
        "height": height,
        "steps": 4,
        "CFGScale": 3.5,
        "acceleration": "high",
        "numberResults": 1,
        "outputType": "base64Data",
        "outputFormat": "JPG",
        "outputQuality": 95,
        "deliveryMethod": "sync",
        # Reports the exact USD this task billed, on the image result (see ``cost`` below).
        "includeCost": True,
    }
    if references:
        task["inputs"] = {"referenceImages": [f"data:{_mime_type(path)};base64,{_base64(path)}" for path in references]}

    response = httpx.post(
        RUNWARE_URL, json=[task], headers={"Authorization": f"Bearer {_api_key('RUNWARE_API_KEY')}"}, timeout=180
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
    view: str = "establishing",
    aspect_ratio: str = ASSET_ASPECT_RATIO,
    quality: str = ASSET_QUALITY,
    resolution: str = ASSET_RESOLUTION,
) -> Path:
    """Render one image (an asset, or a shot's ``"final"`` frame) with one provider and save it as ``{uuid8}-{label}`` in ``directory``.

    ``clause`` says how ``references`` are used (see ``build_prompt``). Raises
    if the provider fails; nothing is written then. What it billed is appended
    to ``world``'s cost log (exact for Runware, estimated for OpenAI and Gemini).
    """
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {sorted(PROVIDERS)}")
    references = list(references)[: MAX_REFERENCES.get(provider)]
    prompt = build_prompt(asset_type, description, style, clause=clause if references else None, view=view)
    ratio = ASPECT_RATIOS[aspect_ratio]
    openai_quality, thinking_level = QUALITY[quality]
    if provider == "openai":
        width, height = SIZES[resolution][ratio]
        data, usage = _openai_bytes(prompt, f"{width}x{height}", openai_quality, references)
        usd, estimated = costs.openai_cost(usage), True
    elif provider == "runware":
        data, cost = _runware_bytes(prompt, SIZES[resolution][ratio], references)
        usd, estimated = cost, False
    else:
        data, usage = _gemini_bytes(prompt, ratio, resolution, thinking_level, references)
        usd, estimated = costs.gemini_cost(usage), True
    image_format = Image.open(BytesIO(data)).format
    path = directory / f"{uuid.uuid4().hex[:8]}-{label}{_EXTENSIONS.get(image_format, '.png')}"
    directory.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    try:
        costs.record(world, asset_type, label, provider, usd, estimated)
    except Exception:
        pass  # a logging bug must never cost an already-paid-for render.
    return path
