"""Script: the episode as a Fountain screenplay, written in plain text.

A bar at the top stays on screen as the page scrolls: it picks the view, says
what saving would change, opens the problems (syntax in the editor's text,
references the world does not have) and has Save and Discard. The views:

- **Write**: the editor, with a narrower cheat sheet of Fountain to copy from.
- **Preview**: the screenplay as it reads, unsaved edits included.
- **Breakdown**: one scene at a time (picked at the top): its locations, the
  characters and objects in it, then each shot's action and dialogue beside its
  characters, objects, clip length and checklist, as saved.

The app's own notes (ids, tags, lengths) are kept in the file but never shown
in the editor, so they cannot be deleted by accident. Save asks first, listing
the changes (removals first). Saving tags new and changed shots with the text
model and checks them against the checklist. Every save keeps the previous
script as a version, restorable from the sidebar; Reprocess reads a file
edited in another app.
"""

from __future__ import annotations

import html
from typing import Dict, List

import streamlit as st

import api
from shared.state import notify, show_notice
from shared.story import asset_names, episode_url, excerpt, pick_episode, reference_label
from shared.ui import plural, top_bar, view_picker
from shared.worlds import render_world_switcher

EDITOR_HEIGHT = 640

#: The views, with their icons, in the order the bar shows them.
VIEWS = {"Write": ":material/edit_note:", "Preview": ":material/article:", "Breakdown": ":material/view_list:"}

#: Characters escaped when script text is shown as Markdown.
MARKDOWN_SPECIAL = set("\\`*_{}[]<>()#+-.!|$~")

PAGE_CSS = """
<style>
/* Screenplays are written in a monospaced font; this page's only text area is the editor. */
.stTextArea textarea { font-family: 'Courier Prime', 'Courier New', monospace; font-size: 15px; line-height: 1.5; }
</style>
"""

#: Fountain to copy, as (what it is, how it is written). General on purpose: syntax, not story.
CHEAT_SHEET = [
    ("Title page (first lines of the script)", "Title: The episode's title\nSynopsis:\n    A line or two on the episode."),
    ("Scene heading", "INT. PLACE - DAY"),
    ("Scene heading outdoors", "EXT. PLACE - NIGHT"),
    ("Any other heading (starts with a period)", ".ANYWHERE AT ALL"),
    ("Scene summary (under the heading)", "= What this scene is about, in a line."),
    ("A shot: one paragraph of action", "What we see in this shot.\nMore lines with no blank line between them stay in the same shot."),
    ("Dialogue (right under the shot it belongs to)", "CHARACTER NAME\nWhat they say."),
    ("Dialogue with a parenthetical", "CHARACTER NAME\n(how they say it)\nWhat they say."),
    ("Voice over or off screen", "CHARACTER NAME (V.O.)\nWhat they say."),
    ("Transition", "CUT TO:"),
    ("A line in capitals that is action, not a name", "!A LINE IN CAPITALS"),
    ("A note to yourself (not part of any shot)", "[[A note to yourself.]]"),
    ("Text to ignore for now", "/* Anything in here is left out. */"),
]

#: How each preview element is drawn.
PREVIEW_CSS = """
<style>
.fountain { font-family: "Courier Prime", "Courier New", monospace; font-size: 15px; line-height: 1.5; padding: 16px 24px; }
.fountain p { margin: 0 0 12px 0; white-space: pre-wrap; }
.fountain .title { text-align: center; font-weight: bold; text-transform: uppercase; margin-top: 8px; }
.fountain .title_field { text-align: center; opacity: 0.8; }
.fountain .heading { font-weight: bold; text-transform: uppercase; margin-top: 24px; }
.fountain .synopsis { opacity: 0.6; font-style: italic; }
.fountain .section { opacity: 0.6; }
.fountain .character { margin: 12px 0 0 38%; text-transform: uppercase; }
.fountain .parenthetical { margin: 0 0 0 31%; }
.fountain .dialogue { margin: 0 20% 12px 22%; }
.fountain .transition { text-align: right; text-transform: uppercase; }
.fountain .centered { text-align: center; }
.fountain .character + .dialogue, .fountain .character + .parenthetical, .fountain .parenthetical + .dialogue { margin-top: 0; }
</style>
"""


def changes_line(summary: Dict) -> str:
    """``+1 scene · −2 shots · 3 shots modified`` (empty if nothing changed)."""
    scenes, shots = summary['scenes'], summary['shots']
    parts = []
    for count, sign, noun in ((scenes['added'], "+", "scene"), (scenes['removed'], "−", "scene"),
                              (shots['added'], "+", "shot"), (shots['removed'], "−", "shot")):
        if count:
            parts.append(f"{sign}{plural(count, noun)}")
    if scenes['modified']:
        parts.append(f"{plural(scenes['modified'], 'scene')} modified")
    if shots['modified']:
        parts.append(f"{plural(shots['modified'], 'shot')} modified")
    if shots['moved']:
        parts.append(f"{plural(shots['moved'], 'shot')} moved")
    return " · ".join(parts)


def files_line(counts: Dict) -> str:
    return " and ".join(plural(counts[key], noun) for key, noun in (("frames", "frame"), ("videos", "video")) if counts[key])


@st.dialog("Save the script?")
def confirm_save(world: str, episode: str, text: str, summary: Dict) -> None:
    """List what changes, removals first, and save only on Confirm."""
    if summary['scenes']['removed'] or summary['shots']['removed']:
        removed = []
        if summary['scenes']['removed']:
            removed.append(plural(summary['scenes']['removed'], "scene"))
        if summary['shots']['removed']:
            removed.append(plural(summary['shots']['removed'], "shot"))
        note = f" Their {files_line(summary['unlinked'])} stay on disk, unlinked." if files_line(summary['unlinked']) else ""
        st.warning(f"Removes {' and '.join(removed)}.{note}", icon=":material/delete:")
    st.markdown(f"**Changes:** {changes_line(summary)}")
    if files_line(summary['stale']):
        st.caption(f"{files_line(summary['stale'])} will be flagged as out of date, as their shots changed.")
    st.caption("New and changed shots are tagged and checked by the text model. The current script is kept as a "
               "version you can restore from the sidebar.")
    confirm_col, cancel_col = st.columns(2)
    if cancel_col.button("Cancel", width='stretch'):
        st.rerun()
    if confirm_col.button("Save", type="primary", width='stretch'):
        with st.spinner("Saving, and tagging new and changed shots..."):
            try:
                result = api.put(f"{episode_url(world, episode)}/text", json={'text': text})
            except api.ApiError as exc:
                st.error(str(exc))
                return
        st.session_state.drafts.pop((world, episode), None)
        st.session_state.script_revision += 1
        if result.get('warning'):
            notify('warning', f"Saved, but: {result['warning']}")
        notify('success', f"Saved: {changes_line(summary)}.")


@st.dialog("Reprocess the file?")
def confirm_reprocess(world: str, episode: str) -> None:
    """For a file edited in another app: fill in missing ids, tags and checklists. Nothing already there changes."""
    plan = api.get(f"{episode_url(world, episode)}/reprocess")
    todo = []
    if plan['ids']:
        todo.append(f"give {plural(plan['ids'], 'new scene or shot')} an id")
    if plan['untagged_scenes'] or plan['untagged_shots']:
        todo.append(f"tag {plural(plan['untagged_scenes'], 'scene')} and {plural(plan['untagged_shots'], 'shot')}")
    if plan['unchecked_shots']:
        todo.append(f"run the checklist on {plural(plan['unchecked_shots'], 'shot')}")
    if not todo:
        st.success("Nothing to fill in: every scene and shot has its id, tags and checklist.")
        return
    st.markdown("Reprocessing will " + ", ".join(todo) + ".")
    if plan['unlinked']:
        st.caption(f"{plural(plan['unlinked'], 'shot')} with frames or videos are no longer in the script. "
                   "Their files stay unlinked; restore an older version to link them again.")
    if st.button("Reprocess", type="primary"):
        with st.spinner("Reading the file and tagging..."):
            result = api.post(f"{episode_url(world, episode)}/reprocess")
        st.session_state.drafts.pop((world, episode), None)
        st.session_state.script_revision += 1
        if result.get('warning'):
            notify('warning', result['warning'])
        notify('success', "Reprocessed the file.")


def render_sidebar(world: str, episode: str, view: Dict, ratios: List[str]) -> None:
    url = episode_url(world, episode)
    with st.sidebar:
        key = f"ratio_{world}_{episode}"
        st.selectbox(
            "Aspect ratio", ratios, index=ratios.index(view['aspect_ratio']), key=key,
            help="Every frame of the episode uses this aspect ratio.",
            on_change=lambda: api.patch(url, json={'aspect_ratio': st.session_state[key]}),
        )
        if st.button("Reprocess file", icon=":material/sync:", width='stretch',
                     help="After editing script.fountain in another app: add missing ids, tags and checklists."):
            confirm_reprocess(world, episode)
        versions = api.get(f"{url}/versions")['versions']
        with st.popover("Versions", icon=":material/history:", width='stretch', disabled=not versions):
            st.caption("The script as it was before each save, newest first.")
            chosen = st.selectbox("Version", [v['name'] for v in versions],
                                  format_func=lambda name: next(v['saved_at'] for v in versions if v['name'] == name)
                                  .replace("T", " ").replace("+00:00", " UTC"))
            if chosen:
                st.code(api.get(f"{url}/versions/{chosen}")['text'], language=None, height=260)
                st.caption("Restoring keeps the current script as a version too, so it can be undone.")
                if st.button("Restore this version", icon=":material/restore:"):
                    api.post(f"{url}/versions/restore", json={'version': chosen})
                    st.session_state.drafts.pop((world, episode), None)
                    st.session_state.script_revision += 1
                    notify('success', "Restored the version.")


def unsaved_text(world: str, episode: str, view: Dict) -> str:
    """The editor's text: the unsaved draft if there is one, else the saved script."""
    return st.session_state.drafts.get((world, episode), view['text'])


def render_checks(lint: List[Dict], problems: List[Dict], text: str, column) -> None:
    """One button that opens the syntax problems (in the editor's text) and the references the world lacks (saved)."""
    count = len(lint) + len(problems)
    if not count:
        column.caption(":material/check: No problems")
        return
    lines = text.split("\n")
    with column.popover(f"{plural(count, 'problem')}", icon=":material/warning:", width='stretch'):
        if lint:
            st.markdown("**Syntax**")
            for item in lint:
                quoted = excerpt(lines[item['line']], 60) if item['line'] < len(lines) else ""
                st.markdown(f"- Line {item['line'] + 1} `{quoted}`: {item['message']}")
        if problems:
            st.markdown("**Not in this world** (as saved)")
            for problem in problems:
                st.markdown(f"- Line {problem['line'] + 1}: {problem['message']}")


def render_bar(world: str, episode: str, view: Dict, text: str, preview: Dict) -> None:
    """The view picker, what saving would change, the problems, Save and Discard: one row that stays on screen."""
    summary = preview['summary']
    unsaved = text != view['text']
    with top_bar():
        view_col, changes_col, checks_col, save_col, discard_col = st.columns(
            [3.2, 4, 1.6, 1.1, 1.1], vertical_alignment='center')
        view_picker(VIEWS, 'script_view', view_col)
        if summary['changed']:
            changes_col.markdown(f"**Unsaved:** {changes_line(summary)}")
        elif unsaved:
            changes_col.caption("Unsaved: only spacing or notes changed.")
        else:
            changes_col.caption("No unsaved changes.")
        render_checks(preview['lint'], view['problems'], text, checks_col)
        if save_col.button("Save", type="primary", width='stretch', disabled=not unsaved,
                           icon=":material/save:"):
            confirm_save(world, episode, text, summary)
        if discard_col.button("Discard", width='stretch', disabled=not unsaved, help="Go back to the saved script."):
            st.session_state.drafts.pop((world, episode), None)
            st.session_state.script_revision += 1
            st.rerun()


def render_write(world: str, episode: str, view: Dict) -> None:
    """The editor, with the cheat sheet in a narrower column beside it."""
    drafts = st.session_state.drafts
    key = f"editor_{world}_{episode}_{st.session_state.script_revision}"

    def keep_draft() -> None:
        drafts[(world, episode)] = st.session_state[key]

    editor_col, cheat_col = st.columns([5, 2], gap='medium')
    with editor_col:
        st.text_area(
            "Script", value=unsaved_text(world, episode, view), height=EDITOR_HEIGHT, key=key,
            on_change=keep_draft, label_visibility='collapsed',
        )
        st.caption("The changes above and the other views update when you click outside the editor "
                   "(or press Ctrl+Enter).")
    with cheat_col:
        render_cheat_sheet()


def render_preview(elements: List[Dict], unsaved: bool) -> None:
    """The screenplay as it reads, on a page of readable width."""
    _, page_col, _ = st.columns([1, 4, 1])
    with page_col:
        if unsaved:
            st.caption("Includes your unsaved edits.")
        body = "".join(f"<p class='{element['type']}'>{html.escape(element['text'])}</p>" for element in elements)
        with st.container(border=True):
            st.html(PREVIEW_CSS + f"<div class='fountain'>{body}</div>")


def save_tags(world: str, episode: str, path: str, field: str, key: str) -> None:
    try:
        api.patch(f"{episode_url(world, episode)}/{path}", json={field: st.session_state[key]})
    except api.ApiError as exc:
        st.session_state.notice = ('error', f"Could not save the tags: {exc}")


def tag_picker(label: str, options: List[str], current: List[str], key: str, save) -> None:
    # Keep names whose asset is gone, so a save never drops them silently.
    choices = options + [name for name in current if name not in options]
    st.multiselect(label, choices, default=current, format_func=reference_label, key=key,
                   on_change=save[0], args=save[1])


def md(text: str) -> str:
    """``text`` shown as written: Markdown and LaTeX characters escaped."""
    return "".join("\\" + char if char in MARKDOWN_SPECIAL else char for char in text)


def chips(names: List[str]) -> str:
    return " ".join(f":gray-badge[{md(reference_label(name))}]" for name in names) or ":gray[None]"


def step_scene(key: str, numbers: List[int], step: int) -> None:
    index = numbers.index(st.session_state[key]) + step
    st.session_state[key] = numbers[max(0, min(index, len(numbers) - 1))]


def render_shot(world: str, episode: str, scene: Dict, shot: Dict, names: Dict, durations: List[int],
                prefix: str) -> None:
    """One shot: its action and dialogue on the left, what was recognized in it on the right."""
    with st.container(border=True):
        text_col, tags_col = st.columns([3, 2], gap='medium')
        with text_col:
            st.markdown(f"**Shot {scene['number']}.{shot['number']}**")
            st.markdown(md(shot['action']))
            for line in shot['dialogue']:
                parenthetical = f" _{md(line['parenthetical'])}_" if line.get('parenthetical') else ""
                st.markdown(f"> **{md(line['cue'])}**{parenthetical}  \n> {md(line['text'])}")
        with tags_col:
            if not shot['id']:
                st.caption("Save or reprocess to tag this shot.")
                return
            for field in ('characters', 'objects'):
                key = f"{prefix}_{shot['id']}_{field}"
                tag_picker(field.capitalize(), names[field], shot[field], key,
                           (save_tags, (world, episode, f"shots/{shot['id']}", field, key)))
            length_col, check_col = st.columns([1, 2], vertical_alignment='bottom')
            key = f"{prefix}_{shot['id']}_duration"
            length_col.selectbox(
                "Length", durations, index=durations.index(shot['duration']), format_func=lambda s: f"{s} s",
                key=key, help="The clip's length on the Video page.",
                on_change=save_tags, args=(world, episode, f"shots/{shot['id']}", 'duration', key),
            )
            if shot['missing']:
                check_col.caption(":material/checklist: Not mentioned: " + ", ".join(shot['missing']).lower() + ".")
            elif shot['missing'] is None:
                check_col.caption(":material/checklist: Not checked yet.")
            else:
                check_col.caption(":material/check: Checklist complete.")


def render_breakdown(world: str, episode: str, view: Dict, durations: List[int], unsaved: bool) -> None:
    """One scene at a time: its locations, everyone and everything in it, then each shot with its tags."""
    if unsaved:
        st.info("The breakdown shows the saved script. Save to see your edits here.", icon=":material/info:")
    scenes = view['scenes']
    if not scenes:
        st.info("No scenes yet. Start one in **Write** with a heading such as `INT. PLACE - DAY`.")
        return
    numbers = [scene['number'] for scene in scenes]
    key = f"breakdown_scene_{world}_{episode}"
    if st.session_state.get(key) not in numbers:
        st.session_state[key] = numbers[0]
    pick_col, prev_col, next_col, stats_col = st.columns([5, 0.6, 0.6, 3], vertical_alignment='bottom')
    number = pick_col.selectbox("Scene", numbers, key=key,
                                format_func=lambda n: f"{n}. {scenes[n - 1]['heading']}")
    prev_col.button("", icon=":material/chevron_left:", help="Previous scene", width='stretch',
                    disabled=number == numbers[0], on_click=step_scene, args=(key, numbers, -1))
    next_col.button("", icon=":material/chevron_right:", help="Next scene", width='stretch',
                    disabled=number == numbers[-1], on_click=step_scene, args=(key, numbers, 1))
    scene = scenes[number - 1]
    seconds = sum(shot['duration'] for shot in scene['shots'])
    stats_col.caption(f"Scene {number} of {len(scenes)} · {plural(len(scene['shots']), 'shot')} · {seconds} s")

    st.markdown(f"### {md(scene['heading'])}")
    if scene.get('summary'):
        st.caption(md(scene['summary']))
    names = asset_names(world)
    prefix = f"tags_{world}_{episode}_{st.session_state.script_revision}"
    loc_col, chars_col, objs_col = st.columns(3, gap='medium')
    with loc_col:
        if scene['id']:
            loc_key = f"{prefix}_{scene['id']}_loc"
            tag_picker("Locations", names['locations'], scene['locations'], loc_key,
                       (save_tags, (world, episode, f"scenes/{scene['id']}", 'locations', loc_key)))
        else:
            st.caption("Save or reprocess to tag this scene.")
    in_scene = {field: list(dict.fromkeys(name for shot in scene['shots'] for name in shot[field]))
                for field in ('characters', 'objects')}
    chars_col.markdown(f"**Characters in this scene**  \n{chips(in_scene['characters'])}")
    objs_col.markdown(f"**Objects in this scene**  \n{chips(in_scene['objects'])}")
    st.caption("Tags are filled in by the text model when you save. Change them here; your choice then stays.")
    for shot in scene['shots']:
        render_shot(world, episode, scene, shot, names, durations, prefix)
    if not scene['shots']:
        st.caption("No shots in this scene yet: a shot is a paragraph of action under the heading.")


def render_cheat_sheet() -> None:
    st.markdown("**Cheat sheet**")
    st.caption("Copy a block with the icon at its top right. A blank line goes between blocks.")
    with st.container(height=EDITOR_HEIGHT - 60, border=False):
        for label, snippet in CHEAT_SHEET:
            st.caption(label)
            st.code(snippet, language=None, wrap_lines=True)
        st.caption("Full syntax: fountain.io/syntax")


def render_notices(view: Dict) -> None:
    """Missing ids and unlinked files, which need a step from the sidebar."""
    if view['needs_ids']:
        st.info(f"{plural(view['needs_ids'], 'scene or shot')} in the file have no id yet (added in another app?). "
                "Use **Reprocess file** in the sidebar.", icon=":material/sync:")
    if view['unlinked']:
        st.info(f"{plural(len(view['unlinked']), 'removed shot')} still have frames or videos on disk. Restore an "
                "older version from **Versions** in the sidebar to link them again.", icon=":material/link_off:")


def main() -> None:
    world, _ = render_world_switcher()
    st.html(PAGE_CSS)
    episode = pick_episode(world, st.sidebar)
    if not episode:
        return
    view = api.get(episode_url(world, episode))
    options = api.options()
    render_sidebar(world, episode, view, options['aspect_ratios'])
    text = unsaved_text(world, episode, view)
    preview = api.post(f"{episode_url(world, episode)}/preview", json={'text': text})
    render_bar(world, episode, view, text, preview)
    show_notice()
    render_notices(view)

    current = st.session_state.script_view
    if current == "Preview":
        render_preview(preview['elements'], text != view['text'])
    elif current == "Breakdown":
        render_breakdown(world, episode, view, options['video']['durations'], text != view['text'])
    else:
        render_write(world, episode, view)


main()
