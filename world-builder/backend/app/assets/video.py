"""Shot videos with Runware (MiniMax H3 Fast or Gemini Omni Flash 1.2): a shot's final frame, animated.

A video starts from the shot's final frame (its first frame) and is prompted
with the shot's text (the scene's heading and summary, the shot's action and
its tagged cast) and the world's style. The camera moves only as the action
says; a shot that says nothing about it keeps the camera still. H3 Fast renders at 768p, the highest
resolution it offers; Omni Flash at 720p. Neither has dialogue or voices (Omni Flash makes sound
natively and has no switch for it, so the prompt asks for ambient sound only). The file is saved in the scene folder as
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

#: Model key -> how it is called and shown. ``usd_per_second`` is Runware's list price at that
#: resolution, only used for the price shown before a render and when Runware reports no cost;
#: the logged figure is the billed one. ``durations`` are the clip lengths it renders from a frame.
VIDEO_MODELS: Dict[str, Dict[str, Any]] = {
    "minimax-h3-fast": {
        "air": "minimax:h3@fast", "name": "MiniMax H3 Fast", "resolution": "768p",
        "usd_per_second": 0.08,  # checked 2026-11-08
        "durations": (5, 6, 8, 10, 15),
    },
    "gemini-omni-flash-1.2": {
        "air": "google:gemini@omni-flash-1.2", "name": "Gemini Omni Flash 1.2", "resolution": "720p",
        "usd_per_second": 0.07,  # checked 2026-11-27; 3 to 15 s, but at most 10 s from a frame
        "durations": (5, 6, 8, 10),
    },
}
DEFAULT_VIDEO_MODEL = "minimax-h3-fast"
#: Clip lengths a shot can have (every length some model renders); a shot starts at the shortest.
DURATIONS = (5, 6, 8, 10, 15)
DEFAULT_DURATION = DURATIONS[0]

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
    "motion, and move the camera only as the shot describes; if it says nothing about the camera, keep it "
    "static. Do not cut to another shot. "
    "Sound: no dialogue, no voices, no narration, no singing and no lip-sync; ambient sound and effects only."
)


def build_video_prompt(description: str, style: str) -> str:
    """The prompt for one shot video: what happens (camera included), the world's style, then how to animate the frame."""
    if not style.strip():
        raise ValueError("this world has no style yet - write one in Manage worlds")
    if not description.strip():
        raise ValueError("description must not be empty")
    return "\n\n".join([description.strip(), f"Style: {style.strip()}", VIDEO_DIRECTION])


def price(duration: int, model: str = DEFAULT_VIDEO_MODEL) -> float:
    """The list price of one clip of ``duration`` seconds with ``model``."""
    return round(VIDEO_MODELS[model]["usd_per_second"] * duration, 4)


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


def _runware_video(prompt: str, frame: Path, duration: int, model: str,
                   end_frame: Optional[Path] = None) -> Tuple[bytes, Optional[float]]:
    import httpx

    frames = [{"image": _frame_data_uri(frame), "frame": "first"}]
    if end_frame:
        frames.append({"image": _frame_data_uri(end_frame), "frame": "last"})
    task_uuid = str(uuid.uuid4())
    task: Dict[str, Any] = {
        "taskType": "videoInference",
        "taskUUID": task_uuid,
        "model": VIDEO_MODELS[model]["air"],
        "positivePrompt": prompt,
        "duration": duration,
        "resolution": VIDEO_MODELS[model]["resolution"],
        "inputs": {"frameImages": frames},
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
                   duration: int = DEFAULT_DURATION, end_frame: Optional[Path] = None,
                   model: str = DEFAULT_VIDEO_MODEL) -> Path:
    """Render one shot video from its final ``frame`` and save it as ``{uuid8}-{label}.mp4`` in ``directory``.

    With ``end_frame`` (the next shot's final frame) the clip ends on it.

    Raises if Runware fails; nothing is written then. What it billed is appended to ``world``'s cost log.
    """
    if model not in VIDEO_MODELS:
        raise ValueError(f"the video model must be one of {list(VIDEO_MODELS)}")
    if duration not in VIDEO_MODELS[model]["durations"]:
        raise ValueError(f"{VIDEO_MODELS[model]['name']} renders clips of "
                         f"{', '.join(map(str, VIDEO_MODELS[model]['durations']))} seconds, not {duration}")
    prompt = build_video_prompt(description, style)
    data, cost = _runware_video(prompt, frame, duration, model, end_frame)
    path = directory / f"{uuid.uuid4().hex[:8]}-{label}.mp4"
    directory.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    try:
        usd, estimated = (cost, False) if cost is not None else (price(duration, model), True)
        costs.record(world, "video", label, "runware", usd, estimated)
    except Exception:
        pass  # a logging bug must never cost an already-paid-for render.
    return path
