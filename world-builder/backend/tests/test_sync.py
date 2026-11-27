"""Carrying ids from the saved script to an edited one."""

from app.assets import fountain, sync

SAVED = """INT. KITCHEN - DAY [[wb: id=s1]]

Mara walks in. [[wb: id=a]]

She sees the lantern on the table. [[wb: id=b]]

EXT. GARDEN - NIGHT [[wb: id=s2]]

The fox waits by the gate. [[wb: id=c]]
"""


def ids(text: str):
    old, new = fountain.parse(SAVED), fountain.parse(text)
    result = sync.match(old, new)
    shot_ids = [[old["scenes"][p[0]]["shots"][p[1]]["note"]["id"] if p else None for p in scene] for scene in result["shots"]]
    scene_ids = [old["scenes"][i]["note"]["id"] if i is not None else None for i in result["scenes"]]
    return scene_ids, shot_ids, result["summary"]


def test_unchanged_keeps_everything():
    scenes, shots, summary = ids(fountain.strip_notes(SAVED))
    assert scenes == ["s1", "s2"] and shots == [["a", "b"], ["c"]]
    assert not summary["changed"]


def test_edit_insert_and_delete():
    text = """INT. KITCHEN - DAY

Mara walks in slowly.

A new shot of the window.

EXT. GARDEN - NIGHT
"""
    scenes, shots, summary = ids(text)
    assert scenes == ["s1", "s2"]
    assert shots == [["a", None], []]
    assert summary["shots"] == {"added": 1, "removed": 2, "modified": 1, "moved": 0}


def test_rewritten_beyond_recognition_is_a_new_shot():
    text = fountain.strip_notes(SAVED).replace("The fox waits by the gate.", "Rain hammers the empty street.")
    _, shots, summary = ids(text)
    assert shots[1] == [None]
    assert summary["shots"]["added"] == 1 and summary["shots"]["removed"] == 1


def test_moving_a_shot_to_another_scene_keeps_it():
    text = """INT. KITCHEN - DAY

Mara walks in.

EXT. GARDEN - NIGHT

She sees the lantern on the table.

The fox waits by the gate.
"""
    scenes, shots, summary = ids(text)
    assert scenes == ["s1", "s2"]
    assert shots == [["a"], ["b", "c"]]
    assert summary["shots"]["moved"] == 1


def test_reordering_scenes_keeps_ids():
    text = """EXT. GARDEN - NIGHT

The fox waits by the gate.

INT. KITCHEN - DAY

Mara walks in.

She sees the lantern on the table.
"""
    scenes, shots, summary = ids(text)
    assert scenes == ["s2", "s1"]
    assert shots == [["c"], ["a", "b"]]
    assert summary["shots"]["removed"] == 0 and summary["shots"]["added"] == 0


def test_renamed_scene_heading_keeps_scene():
    text = fountain.strip_notes(SAVED).replace("INT. KITCHEN - DAY", "INT. KITCHEN - NIGHT")
    scenes, _, summary = ids(text)
    assert scenes == ["s1", "s2"]
    assert summary["scenes"] == {"added": 0, "removed": 0, "modified": 1}
