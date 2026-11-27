"""Script: the episode as a Fountain screenplay, written in plain text, with a live preview beside it.

The left column is the editor; the right one has three tabs: the screenplay
**Preview**, the **Shots** (each scene's locations and each shot's characters,
objects, clip length and checklist) and a **Cheat sheet** of Fountain to copy
from. The app's own notes (ids, tags, lengths) are kept in the file but never
shown in the editor, so they cannot be deleted by accident.

Under the editor, a line says what saving would change, and the syntax
problems are listed by line. Save asks first, listing the changes (removals
first). Saving tags new and changed shots with the text model and checks
them against the checklist. Every save keeps the previous script as a version,
restorable from the sidebar; Reprocess reads a file edited in another app.
"""

from __future__ import annotations

import html
from typing import Dict, List

import streamlit as st

import api
from shared.state import notify, show_notice
from shared.story import asset_names, episode_url, excerpt, pick_episode, reference_label
from shared.ui import plural
from shared.worlds import render_world_switcher

EDITOR_HEIGHT = 720

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
.fountain { font-family: "Courier Prime", "Courier New", monospace; font-size: 14px; line-height: 1.45; }
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


def render_editor(world: str, episode: str, view: Dict) -> None:
    """The editor, the pending changes, Save and Discard, and the syntax problems."""
    drafts = st.session_state.drafts
    key = f"editor_{world}_{episode}_{st.session_state.script_revision}"

    def keep_draft() -> None:
        drafts[(world, episode)] = st.session_state[key]

    text = st.text_area(
        "Script", value=drafts.get((world, episode), view['text']), height=EDITOR_HEIGHT, key=key,
        on_change=keep_draft, label_visibility='collapsed',
    )
    st.caption("The preview and the changes below update when you click outside the editor (or press Ctrl+Enter).")
    preview = api.post(f"{episode_url(world, episode)}/preview", json={'text': text})
    summary = preview['summary']
    changed_col, save_col, discard_col = st.columns([3, 1, 1], vertical_alignment='center')
    if summary['changed']:
        changed_col.markdown(f"**Unsaved:** {changes_line(summary)}")
    elif text != view['text']:
        changed_col.caption("Only spacing or notes changed.")
    else:
        changed_col.caption("No unsaved changes.")
    unsaved = text != view['text']
    if save_col.button("Save", type="primary", width='stretch', disabled=not unsaved):
        confirm_save(world, episode, text, summary)
    if discard_col.button("Discard", width='stretch', disabled=not unsaved, help="Go back to the saved script."):
        drafts.pop((world, episode), None)
        st.session_state.script_revision += 1
        st.rerun()

    lines = text.split("\n")
    if preview['lint']:
        with st.expander(f"Syntax · {plural(len(preview['lint']), 'thing')} to look at", expanded=True,
                         icon=":material/spellcheck:"):
            for item in preview['lint']:
                quoted = excerpt(lines[item['line']], 60) if item['line'] < len(lines) else ""
                st.markdown(f"- Line {item['line'] + 1} `{quoted}`: {item['message']}")
    st.session_state.script_elements = preview['elements']


def render_preview(elements: List[Dict]) -> None:
    body = "".join(
        f"<p class='{element['type']}'>{html.escape(element['text'])}</p>" for element in elements
    )
    with st.container(height=EDITOR_HEIGHT, border=True):
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


def render_shots(world: str, episode: str, view: Dict, durations: List[int], unsaved: bool) -> None:
    """Each scene's locations, and each shot's characters, objects, clip length and checklist, as saved."""
    if unsaved:
        st.info("This shows the saved script. Save to see your edits here.", icon=":material/info:")
    st.caption("Tags are filled in by the text model when you save. Change them here; your choice then stays.")
    names = asset_names(world)
    prefix = f"tags_{world}_{episode}_{st.session_state.script_revision}"
    with st.container(height=EDITOR_HEIGHT - 60, border=False):
        for scene in view['scenes']:
            st.markdown(f"#### {scene['number']}. {scene['heading']}")
            if not scene['id']:
                st.caption("Save or reprocess to tag this scene.")
                continue
            key = f"{prefix}_{scene['id']}_loc"
            tag_picker("Locations", names['locations'], scene['locations'], key,
                       (save_tags, (world, episode, f"scenes/{scene['id']}", 'locations', key)))
            for shot in scene['shots']:
                st.markdown(f"**Shot {scene['number']}.{shot['number']}** · {excerpt(shot['action'], 120)}")
                if not shot['id']:
                    st.caption("Save or reprocess to tag this shot.")
                    continue
                chars_col, objs_col, length_col = st.columns([4, 4, 2])
                for column, field in ((chars_col, 'characters'), (objs_col, 'objects')):
                    with column:
                        key = f"{prefix}_{shot['id']}_{field}"
                        tag_picker(field.capitalize(), names[field], shot[field], key,
                                   (save_tags, (world, episode, f"shots/{shot['id']}", field, key)))
                key = f"{prefix}_{shot['id']}_duration"
                length_col.selectbox(
                    "Length", durations, index=durations.index(shot['duration']), format_func=lambda s: f"{s} s",
                    key=key, help="The clip's length on the Video page.",
                    on_change=save_tags, args=(world, episode, f"shots/{shot['id']}", 'duration', key),
                )
                if shot['missing']:
                    st.caption(":material/checklist: Not mentioned: " + ", ".join(shot['missing']).lower() + ".")
                elif shot['missing'] is None:
                    st.caption(":material/checklist: Not checked yet.")
            st.divider()


def render_cheat_sheet() -> None:
    st.caption("Copy a block with the icon at its top right, then paste it where you want it in the script. "
               "A blank line goes between blocks.")
    with st.container(height=EDITOR_HEIGHT - 40, border=False):
        for label, snippet in CHEAT_SHEET:
            st.markdown(f"**{label}**")
            st.code(snippet, language=None)
        st.caption("Full syntax: fountain.io/syntax")


def render_problems(view: Dict) -> None:
    """What the saved script refers to that the world does not have, unlinked files and missing ids."""
    if view['needs_ids']:
        st.info(f"{plural(view['needs_ids'], 'scene or shot')} in the file have no id yet (added in another app?). "
                "Use **Reprocess file** in the sidebar.", icon=":material/sync:")
    if view['unlinked']:
        st.info(f"{plural(len(view['unlinked']), 'removed shot')} still have frames or videos on disk. Restore an "
                "older version from **Versions** in the sidebar to link them again.", icon=":material/link_off:")
    if view['problems']:
        with st.expander(f"References · {plural(len(view['problems']), 'thing')} the world does not have",
                         icon=":material/person_search:"):
            for problem in view['problems']:
                st.markdown(f"- Line {problem['line'] + 1}: {problem['message']}")


def main() -> None:
    world, _ = render_world_switcher()
    # Screenplays are written in a monospaced font; this page's only text area is the editor.
    st.html("<style>.stTextArea textarea { font-family: 'Courier Prime', 'Courier New', monospace; "
            "font-size: 15px; line-height: 1.5; }</style>")
    episode = pick_episode(world, st.sidebar)
    if not episode:
        return
    view = api.get(episode_url(world, episode))
    options = api.options()
    render_sidebar(world, episode, view, options['aspect_ratios'])
    st.title(view['title'])
    show_notice()
    render_problems(view)

    editor_col, side_col = st.columns(2)
    with editor_col:
        render_editor(world, episode, view)
    unsaved = st.session_state.drafts.get((world, episode), view['text']) != view['text']
    with side_col:
        preview_tab, shots_tab, cheat_tab = st.tabs(["Preview", "Shots", "Cheat sheet"])
        with preview_tab:
            render_preview(st.session_state.script_elements)
        with shots_tab:
            render_shots(world, episode, view, options['video']['durations'], unsaved)
        with cheat_tab:
            render_cheat_sheet()


main()
