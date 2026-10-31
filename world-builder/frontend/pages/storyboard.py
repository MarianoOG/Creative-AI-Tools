"""Storyboard: an episode's final frames in a grid, their generation, and a zip of them all.

A final frame is the finished image of a shot, rendered once by OpenAI, Gemini or Runware (Flux 2 Klein) at high quality from
the shot's text and the designs of everything the scene lists, in the world's
style. Any one, or once all exist every one, can be
regenerated; the old file stays on disk.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import streamlit as st

import api
from shared.state import show_notice
from shared.story import episode_url, generate_shots, pick_episode
from shared.ui import grid
from shared.worlds import render_world_switcher


def shots_in_order(script: Dict) -> List[Tuple[Dict, Dict]]:
    return [(scene, shot) for scene in script['scenes'] for shot in scene['shots']]


@st.cache_data(show_spinner=False, max_entries=4)
def build_zip(files: Tuple[Tuple[str, str], ...]) -> bytes:
    """A zip of ``(name in the zip, data-relative path)`` pairs. Cached on the paths, which change with every render."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_STORED) as archive:  # images are already compressed
        for name, path in files:
            archive.write(api.file_path(path), name)
    return buffer.getvalue()


def export_files(script: Dict) -> Tuple[Tuple[str, str], ...]:
    """Every final frame, named in story order (``01_scene1_01_shot_1.png``) so the files sort as the episode runs."""
    files = []
    for scene_number, scene in enumerate(script['scenes'], start=1):
        for shot_number, shot in enumerate(scene['shots'], start=1):
            if shot.get('final_path'):
                suffix = Path(shot['final_path']).suffix
                files.append((f"{scene_number:02}_{scene['id']}_{shot_number:02}_{shot['id']}{suffix}", shot['final_path']))
    return tuple(files)


def render_grid(script: Dict) -> List[Tuple[str, str]]:
    """Every shot's final frame, scene by scene, with a Regenerate button below each. Returns the ones clicked."""
    clicked = []
    for scene in script['scenes']:
        if not scene['shots']:
            continue
        st.subheader(scene['heading'] or scene['id'])
        for column, shot in grid(scene['shots']):
            with column:
                if shot.get('final_path'):
                    st.image(str(api.file_path(shot['final_path'])), width='stretch')
                else:
                    st.info(f"`{shot['id']}`: no frame yet.")
                label = "Regenerate" if shot.get('final_path') else "Generate"
                if st.button(label, key=f"final_{scene['id']}_{shot['id']}", width='stretch'):
                    clicked.append((scene['id'], shot['id']))
    return clicked


def main() -> None:
    world, _ = render_world_switcher()
    st.title("Storyboard")
    episode = pick_episode(world)
    if not episode:
        return
    script = api.get(episode_url(world, episode))
    show_notice()
    shots = shots_in_order(script)
    if not shots:
        st.info("This episode has no shots yet. Write them on the Script page.")
        return

    options = api.options()
    providers = options['final_providers']
    model_col, action_col = st.columns([3, 2], vertical_alignment='bottom')
    provider = model_col.selectbox(
        "Model", providers, index=providers.index(script['final_provider']),
        format_func=options['providers'].get, key=f"final_provider_{world}_{episode}",
    )
    missing = [(scene['id'], shot['id']) for scene, shot in shots if not shot.get('final_path')]
    generate_all = regenerate_all = False
    with action_col:
        if missing:
            generate_all = st.button(
                f"Generate {len(missing)} frame(s)", type="primary", width='stretch'
            )
        else:
            # Regenerate all stays one small icon beside Export; it asks first, as every frame is a paid render.
            refresh_col, export_col = st.columns([1, 4], vertical_alignment='bottom')
            with refresh_col.popover("", icon=":material/refresh:", help="Regenerate all frames", width='stretch'):
                st.write(f"Render all {len(shots)} frames again? The current files stay on disk.")
                regenerate_all = st.button("Regenerate all", icon=":material/refresh:", type="primary")
            export_col.download_button(
                "Export all frames", data=build_zip(export_files(script)), file_name=f"{world}_{episode}.zip",
                mime="application/zip", type="primary", icon=":material/download:", width='stretch',
            )

    st.divider()
    clicked = render_grid(script)
    if regenerate_all:
        to_generate = [(scene['id'], shot['id']) for scene, shot in shots]
    else:
        to_generate = missing if generate_all else clicked
    if to_generate:
        generate_shots(world, episode, to_generate, "frame", {'provider': provider})


main()
