"""Script: the whole episode, scene by scene and shot by shot, all editable in place, saved as you go.

The script is text only: nothing is generated here. Each shot here is just
its action. Its type is set, and its frame made, on the Storyboard page; its
camera move and clip length are set, and its video made, on the Video page.

Every field saves the whole episode as soon as it changes (a text field when
you leave it), so there is no Save button. Adding, removing and deleting also
save everything typed first, so no edit is lost.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import streamlit as st

import api
from shared.state import notify, show_notice
from shared.story import REFERENCE_FIELDS, asset_names, episode_url, pick_episode, scene_fields
from shared.ui import show_errors
from shared.worlds import render_world_switcher


def scene_prefix(world: str, episode: str, scene_id: str) -> str:
    """Widget keys of a scene. They carry ``script_revision``, so every field reloads after shots are renumbered."""
    return f"sc_{world}_{episode}_{st.session_state.script_revision}_{scene_id}_"


def shot_key(prefix: str, shot: Dict, field: str) -> str:
    return f"{prefix}{shot['id']}_{field}"


def typed_script(world: str, episode: str, script: Dict) -> Dict:
    """The episode as currently typed on the page: the loaded ``script`` with every field's value.

    A shot is sent as its id and action only, so its type, camera move, length and files stay as saved.
    """
    state = st.session_state
    scenes = []
    for scene in script['scenes']:
        prefix = scene_prefix(world, episode, scene['id'])
        scenes.append({
            **scene,
            'heading': state.get(f"{prefix}heading", scene['heading']),
            'summary': state.get(f"{prefix}summary", scene['summary']),
            **{field: state.get(f"{prefix}{field}", scene[field]) for field in REFERENCE_FIELDS},
            'shots': [
                {'id': shot['id'], 'action': state.get(shot_key(prefix, shot, 'action'), shot['action'])}
                for shot in scene['shots']
            ],
        })
    return {
        **script,
        'title': state.get(f"title_{episode}", script['title']),
        'synopsis': state.get(f"synopsis_{episode}", script['synopsis']),
        'aspect_ratio': state.get(f"ratio_{episode}", script['aspect_ratio']),
        'scenes': scenes,
    }


def save_typed(world: str, episode: str, script: Dict) -> None:
    """Every field's on_change: save the whole episode as typed. The fields keep their keys, so nothing reloads."""
    try:
        api.put(episode_url(world, episode), json=typed_script(world, episode, script))
    except api.ApiError as exc:
        st.session_state.notice = ('error', f"Could not save the script: {exc}")


def render_header(episode: str, script: Dict, ratios: List[str], save: Dict) -> None:
    """The episode's title, synopsis and aspect ratio as fields, each saved as soon as it changes."""
    st.text_input("Title", value=script['title'], key=f"title_{episode}", **save)
    st.text_area("Synopsis", value=script['synopsis'], height=90, key=f"synopsis_{episode}", **save)
    st.selectbox(
        "Aspect ratio", ratios, index=ratios.index(script['aspect_ratio']), key=f"ratio_{episode}",
        help="Every frame of the episode uses this aspect ratio.", **save,
    )


def action_height(text: str) -> int:
    """Tall enough to read the whole action without scrolling, within reason."""
    lines = sum(max(1, math.ceil(len(line) / 90)) for line in text.splitlines() or [""])
    return min(400, max(68, 24 * lines + 20))


def render_shot(shot: Dict, prefix: str, save: Dict) -> Dict[str, bool]:
    """One shot: its number, its action and a remove button. Its type is set on the Storyboard, and its
    video's camera move and length on the Video page."""
    id_col, action_col, remove_col = st.columns([1, 10, 0.6], vertical_alignment='top')
    id_col.markdown(f"**{shot['id']}**")
    action_col.text_area(
        "Action", value=shot['action'], height=action_height(shot['action']),
        label_visibility='collapsed', placeholder="What happens in this shot", key=shot_key(prefix, shot, 'action'), **save,
    )
    removed = remove_col.button(
        "", icon=":material/delete:", help="Remove the shot", key=shot_key(prefix, shot, 'remove'), width='stretch'
    )
    return {'remove': removed}


def render_scene(scene: Dict, number: int, prefix: str, names: Dict, save: Dict) -> Dict:
    """A scene's heading, summary, references and shots, all as fields saved as soon as they change.
    Returns what was clicked."""
    title_col, delete_col = st.columns([4, 1], vertical_alignment='center')
    title_col.subheader(f"Scene {number} · `{scene['id']}`")
    with delete_col.popover("Delete", width='stretch'):
        st.warning(f"All {len(scene['shots'])} shots of **{scene['id']}** will be removed from the script (the folder is kept, hidden).")
        delete_clicked = st.button("Delete scene", icon=":material/delete:", key=f"{prefix}delete")
    scene_fields(scene, names, prefix, **save)

    st.markdown("**Shots**")
    shots = {
        shot['id']: render_shot(shot, prefix, save) for shot in scene['shots']
    }
    add_clicked = st.button("Add shot", icon=":material/add:", key=f"{prefix}add")
    return {'shots': shots, 'add': add_clicked, 'delete': delete_clicked}


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
    st.sidebar.caption("Every change saves on its own (a text field when you leave it).")
    show_notice()
    save = {'on_change': save_typed, 'args': (world, episode, script)}
    render_header(episode, script, options['aspect_ratios'], save)

    names = asset_names(world)
    actions = {}
    for number, scene in enumerate(script['scenes'], start=1):
        st.divider()
        actions[scene['id']] = render_scene(scene, number, scene_prefix(world, episode, scene['id']), names, save)
    st.divider()
    new_scene, new_scene_clicked = render_new_scene(len(script['scenes']))

    # Act once every widget is drawn, so ``typed_script`` sees all of them.
    typed = typed_script(world, episode, script)
    deleted = None
    changed = new_scene_clicked
    for scene in typed['scenes']:
        clicked = actions[scene['id']]
        removed = [shot_id for shot_id, shot_clicks in clicked['shots'].items() if shot_clicks['remove']]
        if removed:
            scene['shots'] = [shot for shot in scene['shots'] if shot['id'] not in removed]
        if clicked['add']:
            # The backend numbers it; an id no shot has keeps it from taking another shot's frames.
            scene['shots'].append({'id': "new", 'action': ""})
        if clicked['delete']:
            deleted = scene['id']
        changed = changed or bool(removed) or clicked['add'] or clicked['delete']

    if not changed:
        return
    with show_errors():
        api.put(episode_url(world, episode), json=typed)
        # Shots are renumbered on save: new widget keys make every field reload from the saved script.
        st.session_state.script_revision += 1
        if deleted:
            api.delete(f"{episode_url(world, episode)}/scenes/{deleted}")
            notify('success', f"Deleted **{deleted}**.")
        elif new_scene_clicked:
            created = api.post(f"{episode_url(world, episode)}/scenes", json={'name': new_scene})
            notify('success', f"Added **{created['name']}**.")
        else:
            st.rerun()


main()
