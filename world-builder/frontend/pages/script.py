"""Script: the whole episode, scene by scene and shot by shot, all editable in place.

The script is the main thing. Each shot's reference frame sits small beside its
text: a quick low detailed view in the world's style, drawn from text alone
with the episode's model and aspect ratio. Regenerating replaces a shot's
frame; the old file stays on disk. The finished frames are made on the
Storyboard page.

Every change (save, add, remove, generate, delete) first collects what is typed
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
from shared.worlds import model_select, render_world_switcher


def render_header(episode: str, script: Dict) -> Tuple[Dict, bool]:
    """The episode's title, synopsis and frame settings. Returns them as typed, and whether Save was clicked."""
    options = api.options()
    with st.expander("Edit title, synopsis and reference frame settings"):
        title = st.text_input("Title", value=script['title'], key=f"title_{episode}")
        synopsis = st.text_area("Synopsis", value=script['synopsis'], key=f"synopsis_{episode}")
        model_col, ratio_col = st.columns(2)
        with model_col:
            provider = model_select(options, key=f"provider_{episode}", default=script['provider'])
        ratios = options['aspect_ratios']
        aspect_ratio = ratio_col.selectbox(
            "Aspect ratio", ratios, index=ratios.index(script['aspect_ratio']), key=f"ratio_{episode}"
        )
        st.caption("Every reference frame of the episode uses this model and aspect ratio, as a quick low detailed view.")
        clicked = st.button("Save", key=f"save_header_{episode}")
    st.title(script['title'])
    if script['synopsis']:
        st.write(f"*{script['synopsis']}*")
    fields = {'title': title, 'synopsis': synopsis, 'provider': provider, 'aspect_ratio': aspect_ratio}
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
    """One shot: its type and action, with its reference frame small on the right."""
    text_col, image_col = st.columns([5, 1])
    with text_col:
        id_col, type_col = st.columns([1, 3], vertical_alignment='center')
        id_col.markdown(f"**{number}.** `{shot['id']}`")
        type_col.selectbox(
            "Shot type", shot_types, index=shot_types.index(shot['type']) if shot['type'] in shot_types else None,
            placeholder="Shot type", label_visibility='collapsed', key=shot_key(prefix, shot, 'type'),
        )
        st.text_area(
            "Action", value=shot['action'], height=action_height(shot['action']),
            label_visibility='collapsed', placeholder="What happens in this shot", key=shot_key(prefix, shot, 'action'),
        )
    with image_col:
        if shot.get('path'):
            st.image(str(api.file_path(shot['path'])), width='stretch')
        else:
            st.caption("No frame yet.")
        generate_col, remove_col = st.columns(2)
        return {
            'generate': generate_col.button(
                "", icon=":material/refresh:" if shot.get('path') else ":material/image:",
                help="Regenerate the frame" if shot.get('path') else "Generate the frame",
                key=shot_key(prefix, shot, 'generate'), width='stretch',
            ),
            'remove': remove_col.button(
                "", icon=":material/delete:", help="Remove the shot", key=shot_key(prefix, shot, 'remove'), width='stretch'
            ),
        }


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


def generate(world: str, episode: str, shots: List[Tuple[str, str]]) -> None:
    """Render each ``(scene, shot)`` reference frame in turn, then rerun to show them."""
    warnings = []
    with st.status(f"Generating {len(shots)} frame(s)... each can take a few minutes.") as status:
        for scene_id, shot_id in shots:
            status.write(f"Rendering `{scene_id}` · `{shot_id}`...")
            try:
                api.post(f"{episode_url(world, episode)}/scenes/{scene_id}/shots/{shot_id}/generate")
            except api.ApiError as exc:
                warnings.append(f"{scene_id}/{shot_id}: {exc}")
    if warnings:
        notify('warning', "Some renders failed: " + "; ".join(warnings))
    notify('success', f"Generated {len(shots)} frame(s).")


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
    missing = [(scene['id'], shot['id']) for scene in script['scenes'] for shot in scene['shots'] if not shot.get('path')]
    settings_col, save_col, missing_col = st.columns([2, 1, 1])
    settings_col.caption(f"Reference frames: {options['providers'][script['provider']]} · {script['aspect_ratio']} · low detailed view.")
    save_clicked = save_col.button("Save script", type="primary", width='stretch')
    missing_clicked = missing_col.button(f"Generate {len(missing)} missing frame(s)", disabled=not missing, width='stretch')

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
    to_generate = list(missing) if missing_clicked else []
    deleted = None
    changed = save_clicked or header_clicked or missing_clicked or new_scene_clicked
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
        to_generate += [(scene_id, shot_id) for shot_id, clicked in actions['shots'].items() if clicked['generate']]
        changed = changed or bool(removed) or actions['add'] or actions['delete']
        edited_scenes.append(edited)

    if not (changed or to_generate):
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
    if to_generate:
        generate(world, episode, to_generate)
    notify('success', "Script saved.")


main()
