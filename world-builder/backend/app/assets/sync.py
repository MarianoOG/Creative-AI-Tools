"""Carry scene and shot ids from the saved script to an edited one, and say what changed. No AI, no I/O.

The editor shows the script without the app's notes, so an edited script
comes back with no ids. :func:`match` finds, for each scene and shot in it,
the one it was in the saved script:

1. Shots, in story order, are compared as text (:func:`fountain.shot_text`).
   Runs of identical shots match as they are.
2. Between those runs, an edited shot matches the saved one it is most like
   (``SIMILAR`` or closer), in order. Anything less alike is a new shot, and the
   saved one is removed: rewriting a shot beyond recognition makes a new one.
3. A saved shot that turns up unchanged elsewhere (another place or scene) has moved.
4. A scene keeps the id of the saved scene most of its matched shots came from,
   else of a saved scene with the same (or a similar) heading and summary.

What matched keeps its id and its note (tags, clip length); everything else is new.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from app.assets.fountain import shot_text

#: How alike (0 to 1) an edited shot or scene must be to a saved one to keep its id.
SIMILAR = 0.5


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def _flat(parsed: Dict) -> List[Tuple[int, Dict]]:
    return [(number, shot) for number, scene in enumerate(parsed["scenes"]) for shot in scene["shots"]]


def _scene_text(scene: Dict) -> str:
    return f"{scene['heading']}\n{scene['summary']}"


def match(old: Dict, new: Dict) -> Dict[str, Any]:
    """Match ``new`` (parsed, without ids) to ``old`` (parsed, with ids in its notes).

    Returns ``scenes`` (one per new scene: the old scene's index, or ``None``)
    and ``shots`` (one list per new scene: each shot's old ``(scene, shot)``
    index, or ``None``), plus ``summary`` (see :func:`summarise`).
    """
    old_flat, new_flat = _flat(old), _flat(new)
    old_keys = [shot_text(shot) for _, shot in old_flat]
    new_keys = [shot_text(shot) for _, shot in new_flat]
    pairs: Dict[int, int] = {}  # new flat index -> old flat index
    matcher = SequenceMatcher(None, old_keys, new_keys, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            pairs.update({j1 + k: i1 + k for k in range(i2 - i1)})
        elif tag == "replace":
            used = set()
            for j in range(j1, j2):
                scores = [(_ratio(old_keys[i], new_keys[j]), i) for i in range(i1, i2) if i not in used]
                # Keep the story order: never pair with a saved shot before the last one paired.
                scores = [(score, i) for score, i in scores if not used or i > max(used)]
                best = max(scores, default=(0.0, None))
                if best[1] is not None and best[0] >= SIMILAR:
                    pairs[j] = best[1]
                    used.add(best[1])
    # Moves: an unmatched new shot identical to an unmatched saved one.
    taken = set(pairs.values())
    moves = set()
    for j, key in enumerate(new_keys):
        if j in pairs:
            continue
        i = next((i for i, other in enumerate(old_keys) if i not in taken and other == key), None)
        if i is not None:
            pairs[j] = i
            moves.add(j)
            taken.add(i)

    old_index = {id(shot): (scene, number) for scene, s in enumerate(old["scenes"])
                 for number, shot in enumerate(s["shots"])}
    shots: List[List[Optional[Tuple[int, int]]]] = [[None] * len(scene["shots"]) for scene in new["scenes"]]
    reordered = set()
    for j, (scene_number, shot) in enumerate(new_flat):
        if j in pairs:
            pair = old_index[id(old_flat[pairs[j]][1])]
            shots[scene_number][new["scenes"][scene_number]["shots"].index(shot)] = pair
            if j in moves:
                reordered.add(pair)

    scenes = _match_scenes(old, new, shots)
    return {"scenes": scenes, "shots": shots, "summary": summarise(old, new, scenes, shots, reordered)}


def _match_scenes(old: Dict, new: Dict, shots: List[List[Optional[Tuple[int, int]]]]) -> List[Optional[int]]:
    scenes: List[Optional[int]] = [None] * len(new["scenes"])
    used = set()
    # 1. Where most of a scene's matched shots came from.
    for number, matched in enumerate(shots):
        votes: Dict[int, int] = {}
        for pair in matched:
            if pair is not None:
                votes[pair[0]] = votes.get(pair[0], 0) + 1
        for candidate, _ in sorted(votes.items(), key=lambda item: -item[1]):
            if candidate not in used:
                scenes[number] = candidate
                used.add(candidate)
                break
    # 2. The same heading and summary, then a similar one, in order.
    for threshold in (1.0, SIMILAR):
        for number, scene in enumerate(new["scenes"]):
            if scenes[number] is not None:
                continue
            scores = [(_ratio(_scene_text(other), _scene_text(scene)), index)
                      for index, other in enumerate(old["scenes"]) if index not in used]
            best = max(scores, default=(0.0, None))
            if best[1] is not None and best[0] >= threshold:
                scenes[number] = best[1]
                used.add(best[1])
    return scenes


def summarise(old: Dict, new: Dict, scenes: List[Optional[int]], shots: List[List[Optional[Tuple[int, int]]]],
              reordered: set) -> Dict[str, Any]:
    """How many scenes and shots are added, removed, modified and moved; the shots, by old ``(scene, shot)``."""
    kept_scenes = {index for index in scenes if index is not None}
    scene_counts = {
        "added": sum(1 for index in scenes if index is None),
        "removed": len(old["scenes"]) - len(kept_scenes),
        "modified": sum(
            1 for number, index in enumerate(scenes)
            if index is not None and _scene_text(old["scenes"][index]) != _scene_text(new["scenes"][number])
        ),
    }
    modified, moved, kept = [], [], set()
    for scene_number, matched in enumerate(shots):
        for shot_number, pair in enumerate(matched):
            if pair is None:
                continue
            kept.add(pair)
            old_shot = old["scenes"][pair[0]]["shots"][pair[1]]
            new_shot = new["scenes"][scene_number]["shots"][shot_number]
            if shot_text(old_shot) != shot_text(new_shot):
                modified.append(pair)
            elif scenes[scene_number] != pair[0] or pair in reordered:
                moved.append(pair)
    removed = [(s, n) for s, scene in enumerate(old["scenes"]) for n in range(len(scene["shots"])) if (s, n) not in kept]
    shot_counts = {
        "added": sum(1 for matched in shots for pair in matched if pair is None),
        "removed": len(removed),
        "modified": len(modified),
        "moved": len(moved),
    }
    return {
        "scenes": scene_counts,
        "shots": shot_counts,
        "modified_shots": modified,
        "removed_shots": removed,
        "changed": any(scene_counts.values()) or any(shot_counts.values()),
    }

