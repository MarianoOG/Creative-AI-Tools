"""Asset image generation via OpenAI (gpt-image-2) and Gemini (Nano Banana 2).

Both providers sit behind one interface: :meth:`AssetImageGenerator.generate_asset`
and its four per-type wrappers. Prompts come from :mod:`prompt_manager`, renders
are written under ``<DATA_DIR>/assets/<world>/<asset-type-dir>/``, and the
methods return the :class:`Path` written.

OpenAI emits PNG, Gemini JPEG; bytes are stored provider-native and output is
always 2K. See the README for why.
"""

from __future__ import annotations

import base64
import mimetypes
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Any, Literal, Optional, Sequence

from PIL import Image

from app.assets.prompt_manager import ASSET_DIRS, REFERENCE_STYLE_SLUG, AssetType, build_prompt
from app.settings import ASSETS_DIR

IMG_DIR = ASSETS_DIR

#: The world every asset belongs to unless one is named. Lives here rather than
#: in :mod:`app.assets.worlds` because this module owns the write path, and
#: ``app.assets.worlds`` imports it from here.
DEFAULT_WORLD = "default"

OPENAI_MODEL = "gpt-image-2"
GEMINI_MODEL = "gemini-nano-banana-2.1"

AspectRatio = Literal["landscape", "square", "portrait", "16:9", "1:1", "9:16"]
Quality = Literal["low", "medium", "high"]
Provider = Literal["openai", "gemini"]

#: What a generate call returns: one path, or one per provider for "both" — where
#: a failed provider's slot holds its exception instead.
RenderResult = Path | dict[str, Path | Exception]

#: Gemini takes this string directly in `response_format`.
IMAGE_SIZE = "2K"

#: Friendly names -> the ratio strings the Gemini API accepts.
ASPECT_RATIOS: dict[str, str] = {
    "landscape": "16:9",
    "square": "1:1",
    "portrait": "9:16",
    "16:9": "16:9",
    "1:1": "1:1",
    "9:16": "9:16",
}

#: gpt-image-2 takes explicit pixels, not a ratio; both dimensions must be
#: divisible by 16. These are the 2K rows, verified against the live API.
OPENAI_SIZES: dict[str, str] = {
    "1:1": "2048x2048",
    "16:9": "2048x1152",
    "9:16": "1152x2048",
}

#: friendly quality -> (openai `quality`, gemini `thinking_level`). Gemini has no
#: quality field; its dial is `thinking_level`, and gemini-3.1-flash-image 400s on
#: every value except "high". `None` means "send nothing and take the model
#: default" — the only cheap path available today.
QUALITY: dict[str, tuple[Quality, str | None]] = {
    "low": ("low", None),
    "medium": ("medium", None),
    "high": ("high", "high"),
}

#: Extension per format sniffed off the returned bytes.
_EXTENSIONS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}


def save_image(
    data: bytes,
    filename: str,
    asset_type: AssetType,
    world: str = DEFAULT_WORLD,
    dpi: int | None = None,
) -> Path:
    """Write image bytes into ``assets/<world>/<asset-type-dir>/`` and return the path.

    ``filename`` is a stem: the extension comes from the actual format of
    ``data``, so a JPEG never ends up named ``.png``. ``dpi`` tags the file with
    a physical resolution (300 for print) — without one a printer guesses.

    The world is its own argument and never part of ``filename``: separators are
    rejected below, and the gallery parses the stem right to left, so a world
    name in there would make that parse ambiguous.
    """
    stem = Path(filename).stem
    if not stem or any(sep in filename for sep in ("/", "\\")):
        raise ValueError(f"filename must be a bare name, got {filename!r}")
    if asset_type not in ASSET_DIRS:
        raise ValueError(
            f"asset_type must be one of {sorted(ASSET_DIRS)}, got {asset_type!r}"
        )
    if not world or world in (".", "..") or any(sep in world for sep in ("/", "\\")):
        raise ValueError(f"world must be a bare folder name, got {world!r}")

    image = Image.open(BytesIO(data))
    image_format = image.format or "PNG"
    directory = IMG_DIR / world / ASSET_DIRS[asset_type]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}{_EXTENSIONS.get(image_format, '.png')}"

    if dpi is None:
        path.write_bytes(data)
    else:
        # quality="keep" reuses the source quantization tables, so tagging a JPEG
        # with DPI does not re-compress it. Ignored for PNG (lossless).
        image.save(path, format=image_format, dpi=(dpi, dpi), quality="keep")
    return path


def _resolve(aspect_ratio: str, quality: str) -> tuple[str, Quality, str | None]:
    """Validate the friendly arguments -> (ratio, openai quality, thinking_level)."""
    ratio = ASPECT_RATIOS.get(aspect_ratio)
    if ratio is None:
        raise ValueError(
            f"aspect_ratio must be one of {sorted(ASPECT_RATIOS)}, got {aspect_ratio!r}"
        )
    if quality not in QUALITY:
        raise ValueError(f"quality must be one of {sorted(QUALITY)}, got {quality!r}")
    return (ratio, *QUALITY[quality])


def _as_paths(reference_images: Sequence[Path | str] | None) -> list[Path]:
    """Normalise the reference argument and fail early on a missing file."""
    paths = [Path(p) for p in reference_images or ()]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"reference image not found: {path}")
    return paths


def _check_world(references: list[Path], world: str) -> None:
    """Refuse references belonging to a world other than the one being written.

    This is the real enforcement of "no scenes from another world's assets" - the
    scoped picker in the UI is only the half a caller can bypass. Uploaded
    references live in a temporary directory outside the library and so are exempt:
    only a file that is already *in* the library is claimed by a world.
    """
    root = IMG_DIR.resolve()
    world_root = (IMG_DIR / world).resolve()
    for path in references:
        resolved = path.resolve()
        if resolved.is_relative_to(root) and not resolved.is_relative_to(world_root):
            raise ValueError(
                f"reference {path.name} belongs to another world; an asset in "
                f"{world!r} can only be built from {world!r} references"
            )


class AssetImageGenerator:
    """Generate character, object, location and scene images from both providers."""

    def __init__(
        self,
        gemini_api_key: str | None = None,
        openai_api_key: str | None = None,
    ) -> None:
        # The environment is already loaded by :mod:`app.settings`.
        self._gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        self._openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        self._gemini_client = None
        self._openai_client = None
        # One generator serves several generations at once. Without the lock two
        # threads can each build a client, and the one that loses the race is
        # garbage-collected - closing its connection - while still in use.
        self._clients_lock = threading.Lock()

    # Clients are built lazily so a missing key only breaks its own provider.
    @property
    def gemini(self):
        with self._clients_lock:
            if self._gemini_client is None:
                if not self._gemini_api_key:
                    raise RuntimeError("GEMINI_API_KEY is not set (see backend/.env)")
                from google import genai

                self._gemini_client = genai.Client(api_key=self._gemini_api_key)
            return self._gemini_client

    @property
    def openai(self):
        with self._clients_lock:
            if self._openai_client is None:
                if not self._openai_api_key:
                    raise RuntimeError("OPENAI_API_KEY is not set (see backend/.env)")
                from openai import OpenAI

                self._openai_client = OpenAI(api_key=self._openai_api_key)
            return self._openai_client

    def _openai_bytes(
        self, prompt: str, ratio: str, quality: Quality, references: list[Path]
    ) -> bytes:
        if references:
            # References go through `images.edit`. No `input_fidelity`: gpt-image-2
            # rejects it outright, so reference adherence rests on the prompt's
            # REFERENCE_CLAUSE alone on this provider.
            handles = [path.open("rb") for path in references]
            try:
                result = self.openai.images.edit(
                    model=OPENAI_MODEL,
                    image=handles,
                    prompt=prompt,
                    size=OPENAI_SIZES[ratio],
                    quality=quality,
                    output_format="png",
                )
            finally:
                for handle in handles:
                    handle.close()
        else:
            result = self.openai.images.generate(
                model=OPENAI_MODEL,
                prompt=prompt,
                size=OPENAI_SIZES[ratio],
                quality=quality,
                output_format="png",
            )

        if not result.data or not result.data[0].b64_json:
            raise RuntimeError("OpenAI returned no image data")
        return base64.b64decode(result.data[0].b64_json)

    def _gemini_bytes(
        self, prompt: str, ratio: str, thinking_level: str | None, references: list[Path]
    ) -> bytes:
        # Without references the input is a plain string; with them it becomes one
        # text block followed by one image block per reference.
        model_input: str | list[dict] = prompt
        if references:
            model_input = [{"type": "text", "text": prompt}]
            for path in references:
                model_input.append(
                    {
                        "type": "image",
                        "data": base64.b64encode(path.read_bytes()).decode(),
                        "mime_type": mimetypes.guess_type(path.name)[0] or "image/png",
                    }
                )

        # `thinking_level` is only sent for quality="high", so it is unpacked
        # rather than passed as None. Typed loosely: `create` is heavily
        # overloaded and a narrower dict confuses the checker.
        # (Do not add `delivery`: the SDK types it but the API rejects both of
        # its values, and the response is inline base64 either way.)
        config: dict[str, Any] = {}
        if thinking_level:
            config["generation_config"] = {"thinking_level": thinking_level}

        interaction = self.gemini.interactions.create(
            model=GEMINI_MODEL,
            input=model_input,
            # `response_format` supersedes the deprecated generation_config.image_config.
            response_format={
                "type": "image",
                "aspect_ratio": ratio,
                "image_size": IMAGE_SIZE,
                "mime_type": "image/jpeg",  # The only image mime type the API accepts.
            },
            **config,
        )

        # Terminal success has been reported as both "completed" and "succeeded",
        # so image data — not the status — is the real success test.
        output = getattr(interaction, "output_image", None)
        if output is None or not output.data:
            status = getattr(interaction, "status", None)
            raise RuntimeError(f"Gemini returned no image data (status={status})")
        return base64.b64decode(output.data)

    def _render(
        self,
        provider: Provider,
        prompt: str,
        filename: str,
        asset_type: AssetType,
        aspect_ratio: AspectRatio,
        quality: Quality,
        references: list[Path],
        world: str,
    ) -> Path:
        """Call one provider with a finished prompt, save the bytes, return the path.

        ``references`` is already normalised: :meth:`generate_asset` is the only
        entry point, so it calls :func:`_as_paths` once for both providers.
        """
        ratio, openai_quality, thinking_level = _resolve(aspect_ratio, quality)
        if provider == "openai":
            data = self._openai_bytes(prompt, ratio, openai_quality, references)
        else:
            data = self._gemini_bytes(prompt, ratio, thinking_level, references)
        return save_image(data, filename, asset_type, world)

    def _render_both(
        self,
        prompt: str,
        filename: str,
        asset_type: AssetType,
        aspect_ratio: AspectRatio,
        quality: Quality,
        references: list[Path],
        world: str,
    ) -> dict[str, Path | Exception]:
        """Render the same prompt with both providers, concurrently, and save both.

        Returns ``{"openai": Path, "gemini": Path}``. A provider that fails puts
        its exception in its slot rather than raising, so one failure never
        discards the other provider's image.
        """
        stem = Path(filename).stem
        results: dict[str, Path | Exception] = {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                provider: pool.submit(
                    self._render,
                    provider,
                    prompt,
                    f"{stem}_{provider}",
                    asset_type,
                    aspect_ratio,
                    quality,
                    references,
                    world,
                )
                for provider in ("openai", "gemini")
            }
            for provider, future in futures.items():
                try:
                    results[provider] = future.result()
                except Exception as exc:  # surfaced per-provider, not raised
                    results[provider] = exc
        return results

    def generate_asset(
        self,
        asset_type: AssetType,
        name: str,
        description: str,
        style: Optional[str],
        reference_images: Sequence[Path | str] | None = None,
        aspect_ratio: AspectRatio = "landscape",
        quality: Quality = "low",
        provider: Literal["openai", "gemini", "both"] = "both",
        world: str = DEFAULT_WORLD,
    ) -> RenderResult:
        """Build the prompt for ``asset_type`` and render it.

        Files are named ``{name}_{style}_{uuid8}_{provider}`` inside
        ``assets/<world>/<asset-type-dir>/``. The uuid is minted once per call, so
        re-rendering the same name and style keeps every attempt and a
        ``provider="both"`` run shares one uuid across its pair; see the README.

        ``world`` decides both where the file lands and which references are
        allowed: anything already in the library must belong to that same world.

        ``provider="both"`` returns the per-provider dict (it appends the provider
        suffix itself); a single provider returns its :class:`Path`.
        """
        references = _as_paths(reference_images)
        _check_world(references, world)
        prompt = build_prompt(
            asset_type, description, style, with_references=bool(references)
        )
        # style=None still needs a token in the filename's style slot for the
        # gallery to group on.
        style_slug = style or REFERENCE_STYLE_SLUG
        uid = uuid.uuid4().hex[:8]
        if provider == "both":
            return self._render_both(
                prompt,
                f"{name}_{style_slug}_{uid}",
                asset_type,
                aspect_ratio,
                quality,
                references,
                world,
            )
        if provider in ("openai", "gemini"):
            return self._render(
                provider,
                prompt,
                f"{name}_{style_slug}_{uid}_{provider}",
                asset_type,
                aspect_ratio,
                quality,
                references,
                world,
            )
        raise ValueError(
            f"provider must be 'openai', 'gemini' or 'both', got {provider!r}"
        )

    # Per-type entry points. They differ only in the asset type they pass through
    # and share every keyword argument of :meth:`generate_asset`.

    def generate_character(
        self, name: str, description: str, style: Optional[str], **kwargs
    ) -> RenderResult:
        """Turnaround sheet: front, side and back on white."""
        return self.generate_asset("character", name, description, style, **kwargs)

    def generate_object(
        self, name: str, description: str, style: Optional[str], **kwargs
    ) -> RenderResult:
        """Turnaround sheet: front and side orthographic views on white."""
        return self.generate_asset("object", name, description, style, **kwargs)

    def generate_location(
        self, name: str, description: str, style: Optional[str], **kwargs
    ) -> RenderResult:
        """Empty background plate — no characters anywhere in the frame."""
        return self.generate_asset("location", name, description, style, **kwargs)

    def generate_scene(
        self, name: str, description: str, style: Optional[str], **kwargs
    ) -> RenderResult:
        """Finished frame. ``description`` is the situation being depicted; pass
        the character/object/location sheets as ``reference_images``."""
        return self.generate_asset("scene", name, description, style, **kwargs)
