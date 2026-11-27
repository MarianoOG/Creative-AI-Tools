"""The Fountain parser, the app's notes and the linter."""

from app.assets import fountain

SCRIPT = """Title: The Lantern
Synopsis:
    A girl finds a lantern.

INT. KITCHEN - DAY [[wb: id=s1; loc=kitchen]]

= Mara finds the lantern still warm.

Wide. MARA steps in.
She stops. [[her note]] [[wb: id=a1; dur=8; chars=mara]]

MARA
(whispering)
Who lit this?

Close on the lantern.

CUT TO:

EXT. GARDEN - NIGHT

The fox waits.
"""


def test_title_page_scenes_and_shots():
    parsed = fountain.parse(SCRIPT)
    assert parsed["title"] == "The Lantern"
    assert parsed["synopsis"] == "A girl finds a lantern."
    kitchen, garden = parsed["scenes"]
    assert kitchen["heading"] == "INT. KITCHEN - DAY"
    assert kitchen["summary"] == "Mara finds the lantern still warm."
    assert kitchen["note"] == {"id": "s1", "loc": ["kitchen"]}
    first, second = kitchen["shots"]
    assert first["action"] == "Wide. MARA steps in.\nShe stops."  # the user's note is not part of the action
    assert first["note"] == {"id": "a1", "dur": "8", "chars": ["mara"]}
    assert first["dialogue"] == [
        {"character": "mara", "cue": "MARA", "parenthetical": "(whispering)", "text": "Who lit this?"}
    ]
    assert second["action"] == "Close on the lantern." and second["note"] == {}
    assert [shot["action"] for shot in garden["shots"]] == ["The fox waits."]
    assert not parsed["lint"]


def test_strip_and_annotate_round_trip():
    clean = fountain.strip_notes(SCRIPT)
    assert "[[wb:" not in clean and "[[her note]]" in clean
    parsed = fountain.parse(SCRIPT)
    scene_notes = [scene["note"] for scene in parsed["scenes"]]
    shot_notes = [[shot["note"] for shot in scene["shots"]] for scene in parsed["scenes"]]
    assert fountain.annotate(clean, scene_notes, shot_notes) == SCRIPT


def test_note_on_its_own_line_goes_to_the_shot_before():
    parsed = fountain.parse("INT. A - DAY\n\nSomething happens.\n[[wb: id=x]]\n")
    assert parsed["scenes"][0]["shots"][0]["note"] == {"id": "x"}


def test_empty_tag_means_tagged_with_nothing():
    note = fountain.parse_note("id=x; chars=; objs=lamp")
    assert note == {"id": "x", "chars": [], "objs": ["lamp"]}
    assert fountain.format_note(note) == "[[wb: id=x; chars=; objs=lamp]]"


def test_lint_catches_common_mistakes():
    text = "KITCHEN - DAY\n\nMara walks.\n\nMARA\n\nFADE OUT:\n\nINT. EMPTY - DAY\n"
    messages = {}
    for item in fountain.parse(text)["lint"]:
        messages.setdefault(item["line"], []).append(item["message"])
    assert "scene heading" in messages[0][0]
    assert "Text before the first scene heading" in messages[2][0]
    assert any("name on its own" in message for message in messages[4])
    assert any("TO:" in message for message in messages[6])
    assert "no action yet" in messages[8][0]
    unclosed = fountain.parse("INT. A - DAY\n\nShe waits. [[open note\n")["lint"]
    assert "never closed" in unclosed[0]["message"]


def test_dialogue_before_any_action_is_flagged():
    parsed = fountain.parse("INT. A - DAY\n\nMARA\nHello.\n")
    assert parsed["scenes"][0]["shots"] == []
    assert any("belongs to no shot" in item["message"] for item in parsed["lint"])


def test_forced_elements():
    parsed = fountain.parse(".THE VOID\n\n!SHOUTING LOUDLY\n\n@mcCLANE\nYippee.\n")
    scene = parsed["scenes"][0]
    assert scene["heading"] == "THE VOID"
    assert scene["shots"][0]["action"] == "SHOUTING LOUDLY"
    assert scene["shots"][0]["dialogue"][0]["cue"] == "mcCLANE"


def test_force_action_and_heading():
    assert fountain.force_action("She waits.") == "She waits."
    assert fountain.force_action("MARA") == "MARA"  # alone, a name is still action
    assert fountain.force_action("INT. ODD - DAY") == "!INT. ODD - DAY"
    assert fountain.force_action("BOB\nHi there.") == "!BOB\nHi there."
    assert fountain.force_heading("The kitchen") == ".The kitchen"
    assert fountain.force_heading("EXT. ROOF - NIGHT") == "EXT. ROOF - NIGHT"
