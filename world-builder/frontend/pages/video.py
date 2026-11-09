"""Video: each shot's final frame animated into a clip (Runware MiniMax H3 Fast at 768p), and a zip of them all.

Each shot is a row: its frame on the left, its video on the right, so a
video that is missing, or older than a regenerated frame (flagged), stands out.
A clip starts from the shot's final frame and is prompted with the world's
style, the shot's text (the scene's heading, summary and cast, and the shot's
type and action) and its camera move, with no dialogue or voices. Each shot's
camera move and clip length are set only here, and saved with the shot. A shot needs its final frame first (the Storyboard page). Every
clip is a paid render, so its price is shown before each button; the billed
figure lands in the world's cost log.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import streamlit as st

import api
from shared.state import show_notice
from shared.story import (
    build_zip, episode_url, export_files, generate_shots, pick_episode, save_shot_setting, shots_in_order,
)
from shared.ui import plural
from shared.worlds import render_world_switcher


def clip_price(video: Dict, shot: Dict) -> float:
    return video['usd_per_second'] * shot['duration']


def money(usd: float) -> str:
    """A price for a label. The dollar sign is escaped, as two in one label would render as LaTeX."""
    return f"\\${usd:.2f}"


def render_controls(world: str, episode: str, scene: Dict, shot: Dict, video: Dict) -> bool:
    """One line: the camera move and clip length (saved as soon as either changes) and the priced
    Generate or Regenerate button. Returns whether the button was clicked."""
    camera_col, length_col, button_col = st.columns([3, 2, 4], vertical_alignment='center')
    prefix = f"video_{world}_{episode}_{scene['id']}_{shot['id']}_{st.session_state.script_revision}_"
    camera_col.selectbox(
        "Camera", video['camera_moves'], index=video['camera_moves'].index(shot['camera']),
        label_visibility='collapsed', help="Camera move", key=f"{prefix}camera", on_change=save_shot_setting,
        args=(world, episode, scene['id'], shot['id'], 'camera', f"{prefix}camera", True),
    )
    length_col.selectbox(
        "Length", video['durations'], index=video['durations'].index(shot['duration']),
        format_func=lambda seconds: f"{seconds} s", label_visibility='collapsed', help="Clip length",
        key=f"{prefix}duration", on_change=save_shot_setting,
        args=(world, episode, scene['id'], shot['id'], 'duration', f"{prefix}duration", True),
    )
    label = "Regenerate" if shot.get('video_path') else "Generate"
    return button_col.button(f"{label} · {money(clip_price(video, shot))}", key=f"video_{scene['id']}_{shot['id']}",
                             width='stretch')


def is_stale(shot: Dict) -> bool:
    """True when the shot's frame was regenerated after its video was made, so the video no longer matches it."""
    if not (shot.get('video_path') and shot.get('final_path')):
        return False
    return api.file_path(shot['final_path']).stat().st_mtime > api.file_path(shot['video_path']).stat().st_mtime


def shot_caption(shot: Dict) -> str:
    action = shot['action'].strip()
    action = action if len(action) <= 140 else action[:137].rstrip() + "..."
    parts = [f"**{shot['id']}**", shot['type'] or "", action]
    return " · ".join(part for part in parts if part)


def render_shot(world: str, episode: str, scene: Dict, shot: Dict, video: Dict) -> bool:
    """One shot as a row: its frame on the left, its video on the right, then one line beneath each,
    side by side: under the frame, a warning when the video is older than it; under the video, the camera,
    length and priced button. Returns whether the button was clicked."""
    st.markdown(shot_caption(shot))
    frame_col, video_col = st.columns(2)
    if not shot.get('final_path'):
        frame_col.info("No final frame yet. Generate it on the Storyboard first.", icon=":material/image:")
        video_col.caption("A video needs the frame first.")
        return False
    frame_col.image(str(api.file_path(shot['final_path'])), width='stretch')
    if shot.get('video_path'):
        video_col.video(str(api.file_path(shot['video_path'])))
    else:
        video_col.info("No video yet.", icon=":material/pending:")

    warning_col, controls_col = st.columns(2, vertical_alignment='center')
    if is_stale(shot):
        warning_col.warning("Frame changed after this video. Regenerate to match.", icon=":material/sync_problem:")
    with controls_col:
        return render_controls(world, episode, scene, shot, video)


def render_grid(world: str, episode: str, script: Dict, video: Dict) -> List[Tuple[str, str]]:
    """Every shot, scene by scene, as a frame | video row. Returns the shots whose button was clicked."""
    clicked = []
    for scene in script['scenes']:
        if not scene['shots']:
            continue
        st.subheader(scene['heading'] or scene['id'])
        left, right = st.columns(2)
        left.caption("Frame")
        right.caption("Video")
        for number, shot in enumerate(scene['shots']):
            if number:
                st.divider()
            if render_shot(world, episode, scene, shot, video):
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
    stale = [(scene['id'], shot['id']) for scene, shot in shots if is_stale(shot)]
    # Pending: no video yet, or one made from an older frame. Kept in story order.
    pending = [key for key in framed if key in set(missing) | set(stale)]
    generate_all = False
    with action_col:
        if pending:
            generate_all = st.button(
                f"Generate {plural(len(pending), 'pending video')} · {money(sum(prices[key] for key in pending))}",
                type="primary", width='stretch',
                help="Every shot with a frame but no video, plus every video older than its frame.",
            )
        elif len(framed) == len(shots):
            # Like the Storyboard: export only once every shot has a video that matches its frame.
            # No "regenerate all": re-rendering every clip at once is too expensive to offer. One at a time only.
            st.download_button(
                "Export all videos", data=build_zip(export_files(script, 'video_path')),
                file_name=f"{world}_{episode}_videos.zip", mime="application/zip",
                icon=":material/download:", width='stretch',
            )
    status = [f"{len(framed) - len(pending)} of {len(framed)} videos up to date"]
    if missing:
        status.append(f"{len(missing)} not generated")
    if stale:
        status.append(f"{len(stale)} older than their frame")
    if len(framed) < len(shots):
        status.append(f"{plural(len(shots) - len(framed), 'shot')} without a frame yet")
    st.caption(" · ".join(status))

    st.divider()
    clicked = render_grid(world, episode, script, video)
    to_generate = pending if generate_all else clicked
    if to_generate:
        generate_shots(world, episode, to_generate, "video", action="video")


main()
