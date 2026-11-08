"""Shot videos with Runware (MiniMax H3 Fast): a shot's final frame, animated.

A video starts from the shot's final frame (its first frame) and is prompted
with the shot's text (the scene's heading and summary, the shot's action and
the scene's cast) and the world's style. It renders at 768p, the highest
resolution H3 Fast offers, with no dialogue or voices. The file is saved in the scene folder as
``{uuid8}-{shot}-video.mp4``; every render gets a new uuid, so nothing is overwritten.

Videos take minutes, so the task is sent with async delivery and polled with
``getResponse`` until it finishes. What it billed (Runware's ``includeCost``)
is appended to the world's cost log; if Runware reports no cost, the list
price below is logged instead, marked ``estimated``.
"""

from __future__ import annotations

import base64
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image

from app.assets import costs
from app.assets.generation import RUNWARE_URL, _api_key

VIDEO_MODEL = "minimax:h3@fast"
VIDEO_MODEL_NAME = "MiniMax H3 Fast"
VIDEO_RESOLUTION = "768p"
#: Runware's list price for H3 Fast at 768p (checked 2026-11-08). Only used for the price
#: shown before a render and when Runware reports no cost; the logged figure is the billed one.
USD_PER_SECOND = 0.08
#: Clip lengths offered (H3 Fast renders 5 to 15 seconds).
DURATIONS = (5, 6, 8, 10, 15)
DEFAULT_DURATION = 6

#: The frame is sent at about the output size: a 2K still would only add upload time.
_FRAME_MAX_SIDE = 1366
#: How long to wait for one video, and how often to ask.
_TIMEOUT_SECONDS = 540
_POLL_SECONDS = 5

#: Comes after the shot and the style, so it has the last word on what moves and what is heard.
VIDEO_DIRECTION = (
    "Animate the attached image as the first frame of this shot. It is fact, not inspiration: keep its "
    "characters, their designs and costumes, the location, the composition and the art style exactly, and "
    "keep that style consistent in every frame. Move only what the shot describes, with natural, readable "
    "motion and a steady camera unless the shot asks for camera movement. Do not cut to another shot. "
    "Sound: no dialogue, no voices, no narration, no singing and no lip-sync; ambient sound and effects only."
)


def build_video_prompt(description: str, style: str) -> str:
    """The prompt for one shot video: what happens, the world's style, then how to animate the frame."""
    if not style.strip():
        raise ValueError("this world has no style yet - write one in Manage worlds")
    if not description.strip():
        raise ValueError("description must not be empty")
    return "\n\n".join([description.strip(), f"Style: {style.strip()}", VIDEO_DIRECTION])


def price(duration: int) -> float:
    """The list price of one clip of ``duration`` seconds."""
    return round(USD_PER_SECOND * duration, 4)


def _frame_data_uri(frame: Path) -> str:
    """The final frame as a JPEG data URI, scaled down so its longest side is at most ``_FRAME_MAX_SIDE``."""
    image = Image.open(frame).convert("RGB")
    image.thumbnail((_FRAME_MAX_SIDE, _FRAME_MAX_SIDE))
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def _post(tasks: list) -> Dict:
    import httpx

    response = httpx.post(
        RUNWARE_URL, json=tasks, headers={"Authorization": f"Bearer {_api_key('RUNWARE_API_KEY')}"}, timeout=120
    )
    body = response.json()
    if body.get("errors"):
        raise RuntimeError("; ".join(error.get("message", str(error)) for error in body["errors"]))
    response.raise_for_status()
    return body


def _video_result(task_uuid: str) -> Optional[Dict]:
    """The finished result of the task, ``None`` while it is still processing. Raises if it failed."""
    body = _post([{"taskType": "getResponse", "taskUUID": task_uuid}])
    for item in body.get("data", []):
        if item.get("taskUUID") not in (None, task_uuid):
            continue
        status = item.get("status")
        if status == "error":
            raise RuntimeError(item.get("message") or "Runware reported the video failed")
        if item.get("videoURL") or item.get("videoBase64Data"):
            return item
    return None


def _runware_video(prompt: str, frame: Path, duration: int) -> Tuple[bytes, Optional[float]]:
    import httpx

    task_uuid = str(uuid.uuid4())
    task: Dict[str, Any] = {
        "taskType": "videoInference",
        "taskUUID": task_uuid,
        "model": VIDEO_MODEL,
        "positivePrompt": prompt,
        "duration": duration,
        "resolution": VIDEO_RESOLUTION,
        "inputs": {"frameImages": [{"image": _frame_data_uri(frame), "frame": "first"}]},
        "outputType": "URL",
        "outputFormat": "MP4",
        "numberResults": 1,
        "deliveryMethod": "async",
        # Reports the exact USD this task billed, on the video result.
        "includeCost": True,
    }
    _post([task])

    deadline = time.monotonic() + _TIMEOUT_SECONDS
    result = None
    while result is None:
        if time.monotonic() > deadline:
            raise RuntimeError(f"the video was not ready after {_TIMEOUT_SECONDS // 60} minutes (task {task_uuid})")
        time.sleep(_POLL_SECONDS)
        result = _video_result(task_uuid)

    if result.get("videoBase64Data"):
        data = base64.b64decode(result["videoBase64Data"])
    else:
        download = httpx.get(result["videoURL"], timeout=120, follow_redirects=True)
        download.raise_for_status()
        data = download.content
    return data, result.get("cost")


def generate_video(world: str, label: str, description: str, style: str, frame: Path, directory: Path,
                   duration: int = DEFAULT_DURATION) -> Path:
    """Render one shot video from its final ``frame`` and save it as ``{uuid8}-{label}.mp4`` in ``directory``.

    Raises if Runware fails; nothing is written then. What it billed is appended to ``world``'s cost log.
    """
    if duration not in DURATIONS:
        raise ValueError(f"duration must be one of {list(DURATIONS)} seconds")
    prompt = build_video_prompt(description, style)
    data, cost = _runware_video(prompt, frame, duration)
    path = directory / f"{uuid.uuid4().hex[:8]}-{label}.mp4"
    directory.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    try:
        usd, estimated = (cost, False) if cost is not None else (price(duration), True)
        costs.record(world, "video", label, "runware", usd, estimated)
    except Exception:
        pass  # a logging bug must never cost an already-paid-for render.
    return path
