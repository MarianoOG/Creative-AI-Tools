"""Video: each shot's final frame animated into a clip (Runware MiniMax H3 Fast at 768p), and a zip of them all.

A clip starts from the shot's final frame and is prompted with the world's
style, the shot's text (the scene's heading, summary and cast, and the shot's
type and action) and its camera move, with no dialogue or voices. Each shot's
camera move and clip length are saved with the shot (also editable on the
Script page). A shot needs its final frame first (the Storyboard page). Every
clip is a paid render, so its price is shown before each button; the billed
figure lands in the world's cost log.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import streamlit as st

import api
from shared.state import show_notice
from shared.story import build_zip, episode_url, export_files, generate_shots, pick_episode, shots_in_order
from shared.ui import grid, plural
from shared.worlds import render_world_switcher


def clip_price(video: Dict, shot: Dict) -> float:
    return video['usd_per_second'] * shot['duration']


def money(usd: float) -> str:
    """A price for a label. The dollar sign is escaped, as two in one label would render as LaTeX."""
    return f"\\${usd:.2f}"


def save_setting(world: str, episode: str, scene_id: str, shot_id: str, field: str, key: str) -> None:
    """Save one shot's ``camera`` or ``duration`` as picked in widget ``key``. Runs as the widget's on_change."""
    try:
        script = api.get(episode_url(world, episode))
        for scene in script['scenes']:
            for shot in scene['shots']:
                if scene['id'] == scene_id and shot['id'] == shot_id:
                    shot[field] = st.session_state[key]
        api.put(episode_url(world, episode), json=script)
        # The Script page's fields reload from the saved script, so it never saves the old value back.
        st.session_state.script_revision += 1
    except api.ApiError as exc:
        st.session_state.notice = ('error', f"Could not save {scene_id}/{shot_id}: {exc}")


def render_settings(world: str, episode: str, scene: Dict, shot: Dict, video: Dict) -> None:
    """The shot's camera move and clip length, saved as soon as either changes."""
    camera_col, length_col = st.columns([3, 2])
    prefix = f"video_{world}_{episode}_{scene['id']}_{shot['id']}_{st.session_state.script_revision}_"
    camera_col.selectbox(
        "Camera", video['camera_moves'], index=video['camera_moves'].index(shot['camera']),
        key=f"{prefix}camera", on_change=save_setting,
        args=(world, episode, scene['id'], shot['id'], 'camera', f"{prefix}camera"),
    )
    length_col.selectbox(
        "Length", video['durations'], index=video['durations'].index(shot['duration']),
        format_func=lambda seconds: f"{seconds} s", key=f"{prefix}duration", on_change=save_setting,
        args=(world, episode, scene['id'], shot['id'], 'duration', f"{prefix}duration"),
    )


def render_grid(world: str, episode: str, script: Dict, video: Dict) -> List[Tuple[str, str]]:
    """Every shot's clip (or its frame, until there is one), scene by scene, with its camera move,
    length and a priced button below each. Returns the ones clicked."""
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
                render_settings(world, episode, scene, shot, video)
                label = "Regenerate video" if shot.get('video_path') else "Generate video"
                if st.button(f"{label} · {money(clip_price(video, shot))}", key=f"video_{scene['id']}_{shot['id']}",
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
    prices = {(scene['id'], shot['id']): clip_price(video, shot) for scene, shot in shots}
    if not framed:
        st.info("No shot has a final frame yet. Generate them on the Storyboard, then animate them here.")
        if st.button("Go to the Storyboard"):
            st.switch_page("pages/storyboard.py")
        return

    info_col, action_col = st.columns([3, 2], vertical_alignment='bottom')
    info_col.caption(
        f"{video['model']} at {video['resolution']}, no voices · **{money(video['usd_per_second'])} per second** "
        "of clip (list price; the billed figure is logged). Each shot's camera move and length are saved with it."
    )

    with_video = {(scene['id'], shot['id']) for scene, shot in shots if shot.get('video_path')}
    missing = [key for key in framed if key not in with_video]
    generate_all = regenerate_all = False
    with action_col:
        if missing:
            generate_all = st.button(
                f"Generate {plural(len(missing), 'video')} · {money(sum(prices[key] for key in missing))}",
                type="primary", width='stretch',
            )
        if with_video:
            # Regenerate all stays one small icon beside Export; it asks first, as every clip is a paid render.
            refresh_col, export_col = st.columns([1, 4], vertical_alignment='bottom')
            with refresh_col.popover("", icon=":material/refresh:", help="Regenerate all videos", width='stretch'):
                st.write(f"Render all {plural(len(framed), 'video')} again for about "
                         f"**{money(sum(prices[key] for key in framed))}**? The current files stay on disk.")
                regenerate_all = st.button("Regenerate all", icon=":material/refresh:", type="primary")
            export_col.download_button(
                "Export all videos", data=build_zip(export_files(script, 'video_path')),
                file_name=f"{world}_{episode}_videos.zip", mime="application/zip",
                icon=":material/download:", width='stretch',
            )
    if len(framed) < len(shots):
        st.caption(f"{plural(len(shots) - len(framed), 'shot')} without a final frame can't be animated yet.")

    st.divider()
    clicked = render_grid(world, episode, script, video)
    if regenerate_all:
        to_generate = framed
    else:
        to_generate = missing if generate_all else clicked
    if to_generate:
        generate_shots(world, episode, to_generate, "video", action="video")


main()
