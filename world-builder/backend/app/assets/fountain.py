"""Fountain screenplays: parsing, the app's hidden notes, the linter and preview elements. Pure text, no I/O.

Fountain (https://fountain.io) is plain text that reads as a screenplay. This
module understands the parts a storyboard needs:

- the **title page** (``Title:``, ``Synopsis:`` and any other ``Key: value`` lines at the top),
- **scene headings** (``INT. KITCHEN - DAY``, or any line forced with a leading ``.``),
- **synopses** (``= ...``), read as the scene's summary,
- **action**: each action paragraph (lines with no blank line between them) is one **shot**,
- **dialogue** (a name in capitals, an optional ``(parenthetical)``, then the lines),
  which belongs to the shot before it,
- transitions, sections, page breaks, centered text, user notes ``[[...]]`` and
  the boneyard ``/* ... */``, which are kept in the text and ignored for shots.

The app keeps what it needs about each scene and shot in a note of its own,
``[[wb: id=a3f9c2; dur=8; chars=fox, mara:older; objs=lantern]]``, at the end
of the scene heading or of the shot's last action line. These notes are hidden
in the app's editor (:func:`strip_notes`) and written back on save
(:func:`annotate`). A note's keys: ``id`` (scenes and shots), ``loc``
(a scene's locations), ``chars`` and ``objs`` (a shot's characters and
objects) and ``dur`` (a shot's clip length in seconds). A tag key that is
present but empty means "tagged, nothing in it"; a missing one means "not tagged yet".
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

#: The app's own notes. Always on one line.
_WB_NOTE = re.compile(r"[ \t]*\[\[wb:([^\]\n]*)\]\]")
#: User notes and the boneyard, possibly over several lines.
_USER_NOTE = re.compile(r"\[\[.*?\]\]", re.S)
_BONEYARD = re.compile(r"/\*.*?\*/", re.S)

_HEADING = re.compile(r"^(INT|EXT|EST|INT\.?/EXT|I/E)[.\s]", re.I)
_SCENE_NUMBER = re.compile(r"\s*#[\w.\-]+#\s*$")
_TITLE_KEY = re.compile(r"^([A-Za-z][A-Za-z ]*):(.*)$")
#: A heading someone forgot to start with INT./EXT.: capitals, a dash, a time of day.
_HEADING_LIKE = re.compile(
    r"^[A-Z0-9 .'/&,]+ - .*(DAY|NIGHT|MORNING|EVENING|AFTERNOON|DAWN|DUSK|LATER|CONTINUOUS|SAME)$"
)
#: Note keys holding lists.
LIST_KEYS = ("loc", "chars", "objs")


# --- notes -----------------------------------------------------------------

def parse_note(body: str) -> Dict[str, Any]:
    """``id=a3f9; chars=fox, mara`` -> ``{"id": "a3f9", "chars": ["fox", "mara"]}``."""
    note: Dict[str, Any] = {}
    for part in body.split(";"):
        key, sep, value = part.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            continue
        note[key] = [item.strip() for item in value.split(",") if item.strip()] if key in LIST_KEYS else value
    return note


def format_note(note: Dict[str, Any]) -> str:
    """The inverse of :func:`parse_note`, in a fixed key order. Empty if there is nothing to say."""
    parts = []
    for key in ("id", "dur", *LIST_KEYS):
        if key not in note or note[key] is None:
            continue
        value = note[key]
        parts.append(f"{key}={', '.join(value) if isinstance(value, list) else value}")
    return f"[[wb: {'; '.join(parts)}]]" if parts else ""


def strip_notes(text: str) -> str:
    """The text as the editor shows it: without the app's notes. The user's own notes stay."""
    return _WB_NOTE.sub("", text)


def _mask(pattern: re.Pattern, text: str) -> str:
    """Blank out every match, keeping its line breaks so line numbers do not move."""
    return pattern.sub(lambda match: "\n" * match.group().count("\n"), text)


# --- parsing ---------------------------------------------------------------

def _is_heading(line: str) -> bool:
    return bool(_HEADING.match(line)) or (line.startswith(".") and not line.startswith(".."))


def _heading_text(line: str) -> str:
    line = _SCENE_NUMBER.sub("", line)
    return line[1:].strip() if line.startswith(".") else line.strip()


def _name_part(line: str) -> str:
    """A character cue without its extension (``(V.O.)``) and dual-dialogue caret."""
    return re.sub(r"\(.*?\)", "", line).replace("^", "").strip()


def _is_cue(line: str) -> bool:
    if line.startswith("@"):
        return True
    name = _name_part(line)
    return bool(name) and any(c.isalpha() for c in name) and name == name.upper() and not line.endswith("TO:")


def _is_transition(line: str) -> bool:
    return (line.isupper() and line.endswith("TO:")) or (line.startswith(">") and not line.endswith("<"))


def cue_name(line: str) -> str:
    """The character a cue names, as a world asset name would spell it (``MARA JONES (V.O.)`` -> ``mara_jones``)."""
    return re.sub(r"[^a-z0-9]+", "_", _name_part(line.lstrip("@")).lower()).strip("_")


def _title_page(lines: List[str]) -> Tuple[Dict[str, str], int]:
    """The title page's keys and the index of the first body line. A script without one starts at 0."""
    if not lines or not _TITLE_KEY.match(lines[0]):
        return {}, 0
    page: Dict[str, str] = {}
    key = None
    index = 0
    while index < len(lines) and lines[index].strip():
        line = lines[index]
        match = _TITLE_KEY.match(line)
        if match and not line[:1].isspace():
            key = match.group(1).strip().lower()
            page[key] = match.group(2).strip()
        elif key:
            page[key] = (page[key] + "\n" + line.strip()).strip()
        index += 1
    return page, index


def parse(text: str) -> Dict[str, Any]:
    """Read a Fountain script.

    Returns ``title``, ``synopsis``, ``title_page`` (every key, lowercased),
    ``scenes`` (each with ``heading``, ``summary``, ``line``, ``note`` and
    ``shots``, each shot with ``action``, ``dialogue``, ``start``, ``end`` and ``note``),
    ``elements`` (what the preview shows) and ``lint`` (problems, by line).
    Line numbers are 0-based indexes into ``text.split("\\n")``; ``note`` is the
    app's note found there (``{}`` if none).
    """
    raw_lines = text.split("\n")
    # The app's notes, by line; then the text without them, then with user notes and the boneyard blanked.
    found: List[Tuple[int, Dict[str, Any]]] = []
    for number, line in enumerate(raw_lines):
        for match in _WB_NOTE.finditer(line):
            found.append((number, parse_note(match.group(1))))
    stripped = strip_notes(text)
    clean = _mask(_BONEYARD, _mask(_USER_NOTE, stripped))
    lines = clean.split("\n")
    lint: List[Dict[str, Any]] = []
    for opener, closer, what in (("[[", "]]", "note"), ("/*", "*/", "boneyard comment")):
        leftover = clean.find(opener)
        if leftover >= 0:
            lint.append({"line": clean[:leftover].count("\n"), "message": f"This {what} is never closed with {closer}, "
                         "so it is read as text."})

    page, index = _title_page(lines)
    elements: List[Dict[str, str]] = []
    if page:
        elements.append({"type": "title", "text": page.get("title", "")})
        for key, value in page.items():
            if key != "title":
                elements.append({"type": "title_field", "text": f"{key.capitalize()}: {value}"})
    scenes: List[Dict[str, Any]] = []

    def blank(position: int) -> bool:
        return position < 0 or position >= len(lines) or not lines[position].strip()

    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        after_blank = blank(index - 1)
        scene = scenes[-1] if scenes else None
        if line.startswith("==="):
            index += 1
            continue
        if line.startswith("#"):
            elements.append({"type": "section", "text": line.lstrip("#").strip()})
            index += 1
            continue
        if line.startswith("=") and not line.startswith("=="):
            synopsis = line[1:].strip()
            elements.append({"type": "synopsis", "text": synopsis})
            if scene is not None:
                scene["summary"] = (scene["summary"] + "\n" + synopsis).strip()
            index += 1
            continue
        if after_blank and _is_heading(line):
            scenes.append({"heading": _heading_text(line), "summary": "", "line": index, "note": {}, "shots": []})
            elements.append({"type": "heading", "text": _heading_text(line)})
            index += 1
            continue
        if after_blank and _is_transition(line):
            elements.append({"type": "transition", "text": line.lstrip(">").strip()})
            index += 1
            continue
        if after_blank and not line.startswith("!") and _is_cue(line) and not blank(index + 1):
            end = index + 1
            while not blank(end):
                end += 1
            dialogue = {"character": cue_name(line), "cue": line.lstrip("@").strip(), "parenthetical": "", "text": ""}
            elements.append({"type": "character", "text": dialogue["cue"]})
            for position in range(index + 1, end):
                said = lines[position].strip()
                if said.startswith("(") and said.endswith(")"):
                    elements.append({"type": "parenthetical", "text": said})
                    dialogue["parenthetical"] = (dialogue["parenthetical"] + " " + said).strip()
                else:
                    elements.append({"type": "dialogue", "text": said})
                    dialogue["text"] = (dialogue["text"] + "\n" + said).strip()
            if scene is not None and scene["shots"]:
                scene["shots"][-1]["dialogue"].append(dialogue)
            else:
                lint.append({"line": index, "message": "Dialogue before any action line belongs to no shot. "
                             "Add an action line above it that says what we see."})
            index = end
            continue
        # Action: the paragraph up to the next blank line is one shot.
        start = index
        while not blank(index):
            index += 1
        paragraph = [lines[position].strip() for position in range(start, index)]
        paragraph[0] = paragraph[0][1:] if paragraph[0].startswith("!") else paragraph[0]
        action = "\n".join(paragraph).strip()
        centered = all(part.startswith(">") and part.endswith("<") for part in paragraph)
        elements.append({"type": "centered" if centered else "action", "text": action})
        if scene is None:
            lint.append({"line": start, "message": "Text before the first scene heading is in no scene, so it is no "
                         "shot. Start the script with a heading such as INT. PLACE - DAY."})
            continue
        scene["shots"].append({"action": action, "dialogue": [], "start": start, "end": index - 1, "note": {}})

    _attach_notes(scenes, found)
    lint += _lint(lines, scenes, page_end=_title_page(lines)[1])
    lint.sort(key=lambda item: item["line"])
    return {
        "title": page.get("title", ""),
        "synopsis": page.get("synopsis", ""),
        "title_page": page,
        "scenes": scenes,
        "elements": elements,
        "lint": lint,
    }


def _attach_notes(scenes: List[Dict], found: List[Tuple[int, Dict]]) -> None:
    """Give each note to the heading or shot on its line; a note on a line of its own goes to the one before it."""
    targets: List[Tuple[int, int, Dict]] = []  # (first line, last line, scene or shot)
    for scene in scenes:
        targets.append((scene["line"], scene["line"], scene))
        targets += [(shot["start"], shot["end"], shot) for shot in scene["shots"]]
    for line, note in found:
        owner = next((target for first, last, target in targets if first <= line <= last), None)
        if owner is None:
            before = [target for first, last, target in targets if last < line and not target["note"]]
            owner = before[-1] if before else None
        if owner is not None and not owner["note"]:
            owner["note"] = note


def _lint(lines: List[str], scenes: List[Dict], page_end: int) -> List[Dict[str, Any]]:
    """Common Fountain mistakes, by line. None of them stops a save."""
    found = []

    def blank(position: int) -> bool:
        return position < 0 or position >= len(lines) or not lines[position].strip()

    for number in range(page_end, len(lines)):
        line = lines[number].strip()
        if not line or not blank(number - 1) or _is_heading(line):
            continue
        if _HEADING_LIKE.match(line):
            found.append({"line": number, "message": "This looks like a scene heading. Start it with INT. or EXT. "
                          "(or a period) so it is read as one."})
        elif line.endswith(":") and line.isupper() and not line.endswith("TO:") and blank(number + 1):
            found.append({"line": number, "message": "Transitions end in TO: (CUT TO:). Start the line with > to "
                          "make any other line one."})
        elif (blank(number + 1) and re.fullmatch(r"[A-Z][A-Z0-9 .'\-]*(\s*\(.*\))?", line)
              and len(_name_part(line).split()) <= 3 and not line.endswith(".")):
            found.append({"line": number, "message": "A name on its own, with a blank line under it, is read as "
                          "action. Put what they say on the next line, with no blank line in between."})
    for scene in scenes:
        if not scene["shots"]:
            found.append({"line": scene["line"], "message": "This scene has no action yet, so it has no shots."})
    return found


# --- writing the notes back --------------------------------------------------

def annotate(text: str, scene_notes: List[Dict], shot_notes: List[List[Dict]]) -> str:
    """``text`` (any notes of the app's are dropped first) with one note per scene heading and per shot.

    ``scene_notes[i]`` goes on scene ``i``'s heading; ``shot_notes[i][j]`` at the end
    of shot ``j`` of scene ``i``. Both follow :func:`parse`'s order.
    """
    clean = strip_notes(text)
    lines = clean.split("\n")
    parsed = parse(clean)
    for scene, scene_note, notes in zip(parsed["scenes"], scene_notes, shot_notes):
        if format_note(scene_note):
            lines[scene["line"]] = lines[scene["line"]].rstrip() + " " + format_note(scene_note)
        for shot, note in zip(scene["shots"], notes):
            if format_note(note):
                lines[shot["end"]] = lines[shot["end"]].rstrip() + " " + format_note(note)
    return "\n".join(lines)


def shot_text(shot: Dict) -> str:
    """A shot's words for comparing versions: its action, then who says what."""
    said = [f"{line['cue']} {line['parenthetical']} {line['text']}".strip() for line in shot["dialogue"]]
    return "\n".join([shot["action"], *said]).strip()


def force_action(paragraph: str) -> str:
    """``paragraph`` written so it reads as one action paragraph (a leading ``!`` where it would read as something else)."""
    paragraph = re.sub(r"\n\s*\n+", "\n", paragraph.strip()) or "(No action yet.)"
    probe = parse(f".PROBE\n\n{paragraph}\n")
    shots = probe["scenes"][0]["shots"] if probe["scenes"] else []
    if len(shots) == 1 and shots[0]["action"] == paragraph and not shots[0]["dialogue"]:
        return paragraph
    return "!" + paragraph


def force_heading(heading: str) -> str:
    heading = " ".join(heading.split())
    return heading if _HEADING.match(heading) else "." + heading
