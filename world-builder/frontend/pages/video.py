"""Video: each shot's final frame animated into a clip (Runware MiniMax H3 Fast at 768p), and a zip of them all.

A clip starts from the shot's final frame and is prompted with the world's
style and the shot's text (the scene's heading, summary and cast, and the
shot's action), with no dialogue or voices. A shot needs its final frame first
(the Storyboard page). Every clip is a paid render, so its price is shown
before each button; the billed figure lands in the world's cost log.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import streamlit as st

import api
from shared.state import show_notice
from shared.story import build_zip, episode_url, export_files, generate_shots, pick_episode, shots_in_order
from shared.ui import grid, plural
from shared.worlds import render_world_switcher


def money(usd: float) -> str:
    """A price for a label. The dollar sign is escaped, as two in one label would render as LaTeX."""
    return f"\\${usd:.2f}"


def render_grid(script: Dict, clip_price: float) -> List[Tuple[str, str]]:
    """Every shot's clip (or its frame, until there is one), scene by scene, with a button below each. Returns the ones clicked."""
    clicked = []
    for scene in script['scenes']:
        if not scene['shots']:
            continue
        st.subheader(scene['heading'] or scene['id'])
        for column, shot in grid(scene['shots']):
            with column:
                if shot.get('video_path'):
                    st.video(str(api.file_path(shot['video_path'])))
                elif shot.get('final_path'):
                    st.image(str(api.file_path(shot['final_path'])), width='stretch')
                else:
                    st.info(f"`{shot['id']}`: no final frame yet. Generate it on the Storyboard first.")
                    continue
                label = "Regenerate video" if shot.get('video_path') else "Generate video"
                if st.button(f"{label} · {money(clip_price)}", key=f"video_{scene['id']}_{shot['id']}",
                             width='stretch'):
                    clicked.append((scene['id'], shot['id']))
    return clicked


def main() -> None:
    world, _ = render_world_switcher()
    st.title("Video")
    episode = pick_episode(world)
    if not episode:
        return
    script = api.get(episode_url(world, episode))
    show_notice()
    shots = shots_in_order(script)
    if not shots:
        st.info("This episode has no shots yet. Write them on the Script page.")
        return

    video = api.options()['video']
    framed = [(scene['id'], shot['id']) for scene, shot in shots if shot.get('final_path')]
    if not framed:
        st.info("No shot has a final frame yet. Generate them on the Storyboard, then animate them here.")
        if st.button("Go to the Storyboard"):
            st.switch_page("pages/storyboard.py")
        return

    duration_col, action_col = st.columns([3, 2], vertical_alignment='bottom')
    duration = duration_col.selectbox(
        "Clip length", video['durations'], index=video['durations'].index(video['default_duration']),
        format_func=lambda seconds: f"{seconds} s", key=f"video_duration_{world}_{episode}",
    )
    clip_price = video['usd_per_second'] * duration
    duration_col.caption(
        f"{video['model']} at {video['resolution']}, no voices · {money(video['usd_per_second'])}/s, "
        f"so **{money(clip_price)} per clip** (list price; the billed figure is logged)."
    )

    with_video = {(scene['id'], shot['id']) for scene, shot in shots if shot.get('video_path')}
    missing = [key for key in framed if key not in with_video]
    generate_all = regenerate_all = False
    with action_col:
        if missing:
            generate_all = st.button(
                f"Generate {plural(len(missing), 'video')} · {money(clip_price * len(missing))}",
                type="primary", width='stretch',
            )
        if with_video:
            # Regenerate all stays one small icon beside Export; it asks first, as every clip is a paid render.
            refresh_col, export_col = st.columns([1, 4], vertical_alignment='bottom')
            with refresh_col.popover("", icon=":material/refresh:", help="Regenerate all videos", width='stretch'):
                st.write(f"Render all {plural(len(framed), 'video')} again for about "
                         f"**{money(clip_price * len(framed))}**? The current files stay on disk.")
                regenerate_all = st.button("Regenerate all", icon=":material/refresh:", type="primary")
            export_col.download_button(
                "Export all videos", data=build_zip(export_files(script, 'video_path')),
                file_name=f"{world}_{episode}_videos.zip", mime="application/zip",
                icon=":material/download:", width='stretch',
            )
    if len(framed) < len(shots):
        st.caption(f"{plural(len(shots) - len(framed), 'shot')} without a final frame can't be animated yet.")

    st.divider()
    clicked = render_grid(script, clip_price)
    if regenerate_all:
        to_generate = framed
    else:
        to_generate = missing if generate_all else clicked
    if to_generate:
        generate_shots(world, episode, to_generate, "video", {'duration': duration}, action="video")


main()
