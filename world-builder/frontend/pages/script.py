"""Script: the whole episode, scene by scene and shot by shot, all editable in place.

The script is text only: nothing is generated here. The frames are made on the
Storyboard page.

Every change (save, add, remove, delete) first collects what is typed
anywhere on the page and saves the whole episode, so no unsaved edit is lost.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import streamlit as st

import api
from shared.state import notify, show_notice
from shared.story import asset_names, episode_url, pick_episode, scene_fields
from shared.ui import show_errors
from shared.worlds import render_world_switcher


def render_header(episode: str, script: Dict, ratios: List[str]) -> Dict:
    """The episode's title, synopsis and aspect ratio as fields. Returns them as typed."""
    title = st.text_input("Title", value=script['title'], key=f"title_{episode}")
    synopsis = st.text_area("Synopsis", value=script['synopsis'], height=90, key=f"synopsis_{episode}")
    aspect_ratio = st.selectbox(
        "Aspect ratio", ratios, index=ratios.index(script['aspect_ratio']), key=f"ratio_{episode}",
        help="Every frame of the episode uses this aspect ratio.",
    )
    return {'title': title, 'synopsis': synopsis, 'aspect_ratio': aspect_ratio}


def shot_key(prefix: str, shot: Dict, field: str) -> str:
    return f"{prefix}{shot['id']}_{field}"


def action_height(text: str) -> int:
    """Tall enough to read the whole action without scrolling, within reason."""
    lines = sum(max(1, math.ceil(len(line) / 90)) for line in text.splitlines() or [""])
    return min(400, max(68, 24 * lines + 20))


def render_shot(shot: Dict, prefix: str, shot_types: List[str]) -> Dict[str, bool]:
    """One shot: its number, type and action, with a remove button."""
    id_col, type_col, remove_col = st.columns([1, 3, 0.4], vertical_alignment='center')
    id_col.markdown(f"**{shot['id']}**")
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
    """A scene's heading, summary, references and shots, all as fields. Returns the scene as typed, and what was clicked."""
    title_col, delete_col = st.columns([4, 1], vertical_alignment='center')
    title_col.subheader(f"Scene {number} · `{scene['id']}`")
    with delete_col.popover("Delete", width='stretch'):
        st.warning(f"All {len(scene['shots'])} shots of **{scene['id']}** will be removed from the script (the folder is kept, hidden).")
        delete_clicked = st.button("Delete scene", icon=":material/delete:", key=f"{prefix}delete")
    edited = scene_fields(scene, names, prefix)

    st.markdown("**Shots**")
    shots = {
        shot['id']: render_shot(shot, prefix, shot_types) for shot in scene['shots']
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
    episode = pick_episode(world, st.sidebar)
    if not episode:
        return
    script = api.get(episode_url(world, episode))
    options = api.options()
    save_clicked = st.sidebar.button("Save script", type="primary", width='stretch')
    show_notice()
    header = render_header(episode, script, options['aspect_ratios'])

    names = asset_names(world)
    shot_types = options.get('shot_types', [])
    scenes = []
    for number, scene in enumerate(script['scenes'], start=1):
        st.divider()
        prefix = f"sc_{world}_{episode}_{st.session_state.script_revision}_{scene['id']}_"
        edited, actions = render_scene(scene, number, prefix, names, shot_types)
        scenes.append((scene['id'], prefix, edited, actions))
    st.divider()
    new_scene, new_scene_clicked = render_new_scene(len(script['scenes']))

    # Act once every widget is drawn, so ``collect`` sees all of them.
    deleted = None
    changed = save_clicked or new_scene_clicked
    edited_scenes = []
    for scene_id, prefix, edited, actions in scenes:
        edited = collect(edited, prefix)
        removed = [shot_id for shot_id, clicked in actions['shots'].items() if clicked['remove']]
        if removed:
            edited['shots'] = [shot for shot in edited['shots'] if shot['id'] not in removed]
        if actions['add']:
            # The backend numbers it; an id no shot has keeps it from taking another shot's frames.
            edited['shots'].append({'id': "new", 'type': None, 'action': ""})
        if actions['delete']:
            deleted = scene_id
        changed = changed or bool(removed) or actions['add'] or actions['delete']
        edited_scenes.append(edited)

    if not changed:
        return
    with show_errors():
        api.put(episode_url(world, episode), json={**script, **header, 'scenes': edited_scenes})
        # Shots are renumbered on save: new widget keys make every field reload from the saved script.
        st.session_state.script_revision += 1
        if deleted:
            api.delete(f"{episode_url(world, episode)}/scenes/{deleted}")
            notify('success', f"Deleted **{deleted}**.")
        elif new_scene_clicked:
            created = api.post(f"{episode_url(world, episode)}/scenes", json={'name': new_scene})
            notify('success', f"Added **{created['name']}**.")
        else:
            notify('success', "Script saved.")


main()
