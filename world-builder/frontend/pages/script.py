"""Script: the whole episode, scene by scene and shot by shot, all editable in place.

The script is text only: nothing is generated here. The frames are made on the
Storyboard page.

Every change (save, add, remove, delete) first collects what is typed
anywhere on the page and saves the whole episode, so no unsaved edit is lost.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Tuple

import streamlit as st

import api
from shared.state import notify, show_notice
from shared.story import asset_names, episode_url, pick_episode, references_markdown, scene_fields
from shared.worlds import render_world_switcher


def render_header(episode: str, script: Dict) -> Tuple[Dict, bool]:
    """The episode's title, synopsis and aspect ratio. Returns them as typed, and whether Save was clicked."""
    options = api.options()
    with st.expander("Edit title, synopsis and aspect ratio"):
        title = st.text_input("Title", value=script['title'], key=f"title_{episode}")
        synopsis = st.text_area("Synopsis", value=script['synopsis'], key=f"synopsis_{episode}")
        ratios = options['aspect_ratios']
        aspect_ratio = st.selectbox(
            "Aspect ratio", ratios, index=ratios.index(script['aspect_ratio']), key=f"ratio_{episode}"
        )
        st.caption("Every frame of the episode uses this aspect ratio.")
        clicked = st.button("Save", key=f"save_header_{episode}")
    st.title(script['title'])
    if script['synopsis']:
        st.write(f"*{script['synopsis']}*")
    fields = {'title': title, 'synopsis': synopsis, 'aspect_ratio': aspect_ratio}
    return fields, clicked


def shot_key(prefix: str, shot: Dict, field: str) -> str:
    return f"{prefix}{shot['id']}_{field}"


def action_height(text: str) -> int:
    """Tall enough to read the whole action without scrolling, within reason."""
    lines = sum(max(1, math.ceil(len(line) / 90)) for line in text.splitlines() or [""])
    return min(400, max(68, 24 * lines + 20))


def next_shot_id(shots: List[Dict]) -> str:
    """A fresh ``shot_N``."""
    taken = [shot['id'] for shot in shots]
    numbers = [int(m.group(1)) for name in taken if (m := re.fullmatch(r"shot_(\d+)", name))]
    return f"shot_{max(numbers, default=len(shots)) + 1}"


def render_shot(shot: Dict, prefix: str, number: int, shot_types: List[str]) -> Dict[str, bool]:
    """One shot: its type and action, with a remove button."""
    id_col, type_col, remove_col = st.columns([1, 3, 0.4], vertical_alignment='center')
    id_col.markdown(f"**{number}.** `{shot['id']}`")
    type_col.selectbox(
        "Shot type", shot_types, index=shot_types.index(shot['type']) if shot['type'] in shot_types else None,
        placeholder="Shot type", label_visibility='collapsed', key=shot_key(prefix, shot, 'type'),
    )
    removed = remove_col.button(
        "", icon=":material/delete:", help="Remove the shot", key=shot_key(prefix, shot, 'remove'), width='stretch'
    )
    st.text_area(
        "Action", value=shot['action'], height=action_height(shot['action']),
        label_visibility='collapsed', placeholder="What happens in this shot", key=shot_key(prefix, shot, 'action'),
    )
    return {'remove': removed}


def render_scene(scene: Dict, number: int, prefix: str, names: Dict, shot_types: List[str]) -> Tuple[Dict, Dict]:
    """A scene's heading, summary, references and shots. Returns the scene's fields as typed, and what was clicked."""
    st.subheader(f"{number}. {scene['heading'] or scene['id']}")
    edit_col, delete_col = st.columns([4, 1])
    with edit_col.expander("Edit heading, summary and references"):
        edited = scene_fields(scene, names, prefix)
    with delete_col.popover("Delete", width='stretch'):
        st.warning(f"All {len(scene['shots'])} shots of **{scene['id']}** will be removed from the script (the folder is kept, hidden).")
        delete_clicked = st.button("Delete scene", icon=":material/delete:", key=f"{prefix}delete")
    if scene['summary']:
        st.write(scene['summary'])
    if references_markdown(scene):
        st.caption(references_markdown(scene))

    shots = {
        shot['id']: render_shot(shot, prefix, shot_number, shot_types)
        for shot_number, shot in enumerate(scene['shots'], start=1)
    }
    add_clicked = st.button("Add shot", icon=":material/add:", key=f"{prefix}add")
    return edited, {'shots': shots, 'add': add_clicked, 'delete': delete_clicked}


def collect(edited: Dict, prefix: str) -> Dict:
    """The scene as currently typed: ``edited`` scene fields plus every shot's type and action."""
    state = st.session_state
    shots = [
        {'id': shot['id'], 'type': state[shot_key(prefix, shot, 'type')], 'action': state[shot_key(prefix, shot, 'action')]}
        for shot in edited['shots']
    ]
    return {**edited, 'shots': shots}


def render_new_scene(count: int) -> Tuple[str, bool]:
    name_col, button_col = st.columns([3, 1])
    name = name_col.text_input("New scene", placeholder=f"scene{count + 1}", label_visibility='collapsed')
    clicked = button_col.button("Add scene", icon=":material/add:", width='stretch')
    return name or f"scene{count + 1}", clicked


def main() -> None:
    world, _ = render_world_switcher()
    episode = pick_episode(world)
    if not episode:
        return
    script = api.get(episode_url(world, episode))
    header, header_clicked = render_header(episode, script)
    show_notice()

    options = api.options()
    _, save_col = st.columns([3, 1])
    save_clicked = save_col.button("Save script", type="primary", width='stretch')

    names = asset_names(world)
    shot_types = options.get('shot_types', [])
    scenes = []
    for number, scene in enumerate(script['scenes'], start=1):
        st.divider()
        prefix = f"sc_{world}_{episode}_{scene['id']}_"
        edited, actions = render_scene(scene, number, prefix, names, shot_types)
        scenes.append((scene['id'], prefix, edited, actions))
    st.divider()
    new_scene, new_scene_clicked = render_new_scene(len(script['scenes']))

    # Act once every widget is drawn, so ``collect`` sees all of them.
    deleted = None
    changed = save_clicked or header_clicked or new_scene_clicked
    edited_scenes = []
    for scene_id, prefix, edited, actions in scenes:
        edited = collect(edited, prefix)
        removed = [shot_id for shot_id, clicked in actions['shots'].items() if clicked['remove']]
        if removed:
            edited['shots'] = [shot for shot in edited['shots'] if shot['id'] not in removed]
            for key in [k for k in st.session_state if any(k.startswith(f"{prefix}{i}_") for i in removed)]:
                del st.session_state[key]
        if actions['add']:
            edited['shots'].append({'id': next_shot_id(edited['shots']), 'type': None, 'action': ""})
        if actions['delete']:
            deleted = scene_id
        changed = changed or bool(removed) or actions['add'] or actions['delete']
        edited_scenes.append(edited)

    if not changed:
        return
    try:
        api.put(episode_url(world, episode), json={**script, **header, 'scenes': edited_scenes})
        if deleted:
            api.delete(f"{episode_url(world, episode)}/scenes/{deleted}")
            notify('success', f"Deleted **{deleted}**.")
        if new_scene_clicked:
            created = api.post(f"{episode_url(world, episode)}/scenes", json={'name': new_scene})
            notify('success', f"Added **{created['name']}**.")
    except api.ApiError as exc:
        st.error(str(exc))
        return
    notify('success', "Script saved.")


main()
