"""Tags and checklist with a cheap, fast language model (Claude Haiku on Runware by default).

One call reads the scenes and shots that changed and returns, for each:

- **tags**: the world's locations in each scene, and its characters and objects
  in each shot, by asset name (``mara`` or ``mara:older``). Only names the world has are kept.
- **checklist**: which of :data:`CHECKLIST` each shot's text does not mention.
  It only says what is missing, never what it should be: the writer decides.

The model is ``TEXT_MODEL`` (env), called through Runware's OpenAI-compatible
endpoint with the Runware key. Nothing here writes files.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

from app.assets.generation import RUNWARE_URL, _api_key

TEXT_MODEL = os.environ.get("TEXT_MODEL", "anthropic:claude@haiku-5.5")

#: What every shot is checked for. The model only says which are not mentioned.
CHECKLIST = [
    "Framing (how wide or close)",
    "Camera angle",
    "Camera movement",
    "Who or what is in frame",
    "What happens",
]

_SYSTEM = (
    "You annotate a screenplay for a storyboard tool. You never rewrite or judge the writing, and you never "
    "suggest how a shot should be: the writer decides. Answer with one JSON object only, no prose."
)


def _assets_block(world: Dict) -> str:
    lines = []
    for folder in ("characters", "locations", "objects"):
        lines.append(f"{folder.upper()}:")
        for asset in world.get(folder, []):
            variations = [v["name"] for v in asset.get("variations", [])]
            extra = f" (variations: {', '.join(variations)})" if len(variations) > 1 else ""
            lines.append(f"- {asset['name']}: {asset.get('description', '').strip()[:300]}{extra}")
        if not world.get(folder):
            lines.append("- (none)")
    return "\n".join(lines)


def build_prompt(world: Dict, scenes: List[Dict]) -> str:
    """``scenes``: each with ``key``, ``heading``, ``summary``, ``tag`` (whether to tag its locations)
    and ``shots`` (each with ``key``, ``action`` and ``dialogue`` text)."""
    script = []
    for scene in scenes:
        script.append(f"SCENE {scene['key']}{' (tag locations)' if scene['tag'] else ''}: {scene['heading']}")
        if scene["summary"]:
            script.append(f"  Summary: {scene['summary']}")
        for shot in scene["shots"]:
            script.append(f"  SHOT {shot['key']}: {shot['action']}")
            if shot["dialogue"]:
                script.append(f"    Dialogue: {shot['dialogue']}")
    checklist = "\n".join(f"- {item}" for item in CHECKLIST)
    return f"""The world's assets, by name:

{_assets_block(world)}

The script (only these scenes and shots need answers; a scene shown without "(tag locations)" is context only):

{chr(10).join(script)}

For each SCENE marked "(tag locations)": the location names (from LOCATIONS) where it happens.
For each SHOT:
- "characters": the CHARACTERS seen in that shot, and "objects": the OBJECTS seen in it. Use the exact names
  above, and add ":variation" (e.g. "mara:older") only when the text clearly asks for that variation.
  Leave out anyone or anything not in the lists.
- "missing": which of these the shot's text does not mention at all (an empty list if it covers them all):
{checklist}
  Use the item names exactly as written. Do not suggest values.

Answer with JSON shaped like:
{{"scenes": {{"<scene key>": {{"locations": ["..."]}}}},
 "shots": {{"<shot key>": {{"characters": ["..."], "objects": ["..."], "missing": ["..."]}}}}}}"""


def _json(text: str) -> Dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise RuntimeError("the model did not answer with JSON")
    return json.loads(match.group())


def _clean(names: Any, allowed: set) -> List[str]:
    """Only names the world has (``name`` or ``name:variation`` of a known name), each once."""
    result = []
    for name in names if isinstance(names, list) else []:
        name = str(name).strip()
        if name.split(":")[0] in allowed and name not in result:
            result.append(name)
    return result


def tag(world: Dict, scenes: List[Dict]) -> Dict[str, Any]:
    """Ask the model. Returns ``{"scenes": {key: [locations]}, "shots": {key: {"chars", "objs", "missing"}}}``.

    Raises if the call fails or the answer is not JSON.
    """
    from openai import OpenAI

    client = OpenAI(api_key=_api_key("RUNWARE_API_KEY"), base_url=RUNWARE_URL, timeout=120)
    response = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": build_prompt(world, scenes)}],
        max_tokens=8000,
        temperature=0,
    )
    answer = _json(response.choices[0].message.content or "")
    names = {folder: {asset["name"] for asset in world.get(folder, [])} for folder in ("characters", "locations", "objects")}
    result: Dict[str, Any] = {"scenes": {}, "shots": {}}
    for key, scene in (answer.get("scenes") or {}).items():
        result["scenes"][str(key)] = _clean((scene or {}).get("locations"), names["locations"])
    for key, shot in (answer.get("shots") or {}).items():
        shot = shot or {}
        result["shots"][str(key)] = {
            "chars": _clean(shot.get("characters"), names["characters"]),
            "objs": _clean(shot.get("objects"), names["objects"]),
            "missing": [item for item in CHECKLIST if item in (shot.get("missing") or [])],
        }
    return result
