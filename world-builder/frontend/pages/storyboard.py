"""Storyboard: one scene's shots, each with its frame and its text, and generation of the missing frames.

Every change (save, add, delete) first collects what is typed in the widgets,
so no unsaved edit is lost.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

import streamlit as st

import api
from shared.state import notify, show_notice
from shared.story import asset_names, dialogue_text, episode_url, parse_dialogue, pick_episode, scene_fields
from shared.worlds import render_world_switcher


def pick_scene(script: Dict) -> Optional[Dict]:
    scenes = [scene['id'] for scene in script['scenes']]
    if not scenes:
        st.info("This episode has no scenes yet. Add one from the Episode page.")
        return None
    headings = {scene['id']: scene['heading'] for scene in script['scenes']}
    current = st.session_state.current_scene if st.session_state.current_scene in scenes else scenes[0]
    chosen = st.selectbox(
        "Scene", scenes, index=scenes.index(current), format_func=lambda s: f"{s} · {headings[s]}".rstrip(" ·")
    )
    st.session_state.current_scene = chosen
    return next(scene for scene in script['scenes'] if scene['id'] == chosen)


def shot_key(prefix: str, shot: Dict, field: str) -> str:
    return f"{prefix}{shot['id']}_{field}"


def collect(edited: Dict, prefix: str) -> Dict:
    """The scene as currently typed: ``edited`` scene fields plus every shot's action and dialogue."""
    state = st.session_state
    shots = [
        {
            'id': shot['id'],
            'action': state[shot_key(prefix, shot, 'action')],
            'dialogue': parse_dialogue(state[shot_key(prefix, shot, 'dialogue')]),
        }
        for shot in edited['shots']
    ]
    return {**edited, 'shots': shots}


def save(world: str, episode: str, script: Dict, scene: Dict) -> Dict:
    scenes = [scene if s['id'] == scene['id'] else s for s in script['scenes']]
    return api.put(episode_url(world, episode), json={**script, 'scenes': scenes})


def next_shot_id(shots: List[Dict], unassigned: List[Dict]) -> str:
    """A fresh ``shot_N``. Counts unlinked frames too, so a new shot never inherits a removed one's images."""
    taken = [shot['id'] for shot in shots] + [frame['name'] for frame in unassigned]
    numbers = [int(m.group(1)) for name in taken if (m := re.fullmatch(r"shot_(\d+)", name))]
    return f"shot_{max(numbers, default=len(shots)) + 1}"


def generate(world: str, episode: str, scene_id: str, shot_ids: List[str], options: Dict) -> None:
    """Render each shot in turn, then rerun to show the new frames."""
    warnings = []
    with st.status(f"Generating {len(shot_ids)} frame(s)... each can take a few minutes.") as status:
        for shot_id in shot_ids:
            status.write(f"Rendering `{shot_id}`...")
            try:
                result = api.post(f"{episode_url(world, episode)}/scenes/{scene_id}/shots/{shot_id}/generate", json=options)
            except api.ApiError as exc:
                warnings.append(f"{shot_id}: {exc}")
                continue
            if result['warning']:
                warnings.append(f"{shot_id}: {result['warning']}")
    if warnings:
        notify('warning', "Some renders failed: " + "; ".join(warnings))
    notify('success', f"Generated {len(shot_ids)} frame(s).")


def render_shot(shot: Dict, prefix: str, number: int) -> Dict[str, bool]:
    """One storyboard row: the newest frame on the left, the text on the right."""
    image_col, text_col = st.columns([3, 2])
    with image_col:
        if shot.get('frames'):
            st.image(str(api.file_path(shot['frames'][0]['path'])), width='stretch')
            if len(shot['frames']) > 1:
                with st.expander(f"{len(shot['frames']) - 1} other take(s)"):
                    for frame in shot['frames'][1:]:
                        st.image(str(api.file_path(frame['path'])), caption=frame['label'], width='stretch')
        else:
            st.info("No frame yet.")
    with text_col:
        st.markdown(f"**{number}.** `{shot['id']}`")
        st.text_area("Action", value=shot['action'], height=110, key=shot_key(prefix, shot, 'action'))
        st.text_area(
            "Dialogue",
            value=dialogue_text(shot['dialogue']),
            height=90,
            key=shot_key(prefix, shot, 'dialogue'),
            help="One line each, as `character: line`. Dialogue is never drawn into the frame.",
        )
        generate_col, delete_col = st.columns(2)
        return {
            'generate': generate_col.button("Generate", key=shot_key(prefix, shot, 'generate'), width='stretch'),
            'delete': delete_col.button("Remove", key=shot_key(prefix, shot, 'remove'), width='stretch'),
        }


def main() -> None:
    world, _ = render_world_switcher()
    st.title("🎬 Storyboard")
    episode = pick_episode(world)
    if not episode:
        return
    script = api.get(episode_url(world, episode))
    scene = pick_scene(script)
    if not scene:
        return
    show_notice()
    if st.button("← Back to the script"):
        st.switch_page("pages/episode.py")

    names = asset_names(world)
    prefix = f"sb_{world}_{episode}_{scene['id']}_"
    edited = scene_fields(scene, names, prefix)

    options = api.options()
    ratio_col, quality_col, save_col, missing_col = st.columns(4)
    render_options = {
        'aspect_ratio': ratio_col.selectbox("Aspect ratio", options['aspect_ratios'], key='sb_ratio'),
        'quality': quality_col.selectbox("Quality", options['qualities'], key='sb_quality'),
    }
    missing = [shot['id'] for shot in scene['shots'] if not shot['frames']]
    save_clicked = save_col.button("Save storyboard", type="primary", width='stretch')
    missing_clicked = missing_col.button(
        f"Generate {len(missing)} missing frame(s)", disabled=not missing, width='stretch'
    )

    actions = {}
    for number, shot in enumerate(scene['shots'], start=1):
        st.divider()
        actions[shot['id']] = render_shot(shot, prefix, number)
    st.divider()
    add_clicked = st.button("＋ Add shot")

    for unassigned in scene['unassigned']:
        st.image(str(api.file_path(unassigned['path'])), caption=f"Not linked to a shot: {unassigned['label']}", width=300)

    # Act once every widget is drawn, so ``collect`` sees all of them.
    edited = collect(edited, prefix)
    to_generate = missing if missing_clicked else [i for i, a in actions.items() if a['generate']]
    removed = [i for i, a in actions.items() if a['delete']]
    if add_clicked:
        edited['shots'].append({'id': next_shot_id(edited['shots'], scene['unassigned']), 'action': "", 'dialogue': []})
    if removed:
        edited['shots'] = [shot for shot in edited['shots'] if shot['id'] not in removed]
        for key in [k for k in st.session_state if any(k.startswith(f"{prefix}{i}_") for i in removed)]:
            del st.session_state[key]
    if save_clicked or add_clicked or removed or to_generate:
        save(world, episode, script, edited)
        if to_generate:
            generate(world, episode, scene['id'], to_generate, render_options)
        notify('success', "Storyboard saved.")


main()
