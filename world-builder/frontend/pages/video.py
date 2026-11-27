"""Video: each shot's final frame animated into a clip, and a zip of them all.

Like the Script and Storyboard pages, the episode, the model (Runware MiniMax H3
Fast at 768p or Gemini Omni Flash 1.2 at 720p, kept per episode) and Export all
videos are in the sidebar, and a bar at the top (which stays on screen as the
page scrolls) says how many videos are up to date and has Generate for the
pending ones. Omni Flash renders up to 10 seconds from a frame, so longer
shots need H3 Fast (or a shorter length).

Each shot is a row: its frame on the left, its video on the right, so a
video that is missing, or out of date (made from another frame, or before the
shot or its length changed: flagged), stands out. A clip starts from the
shot's final frame and is prompted with the world's style and the shot's text
(the scene's heading and summary, the shot's action and tagged cast), with no
dialogue or voices. The camera moves only as the action says. Each shot's clip
length is saved in the script (it is also on the Script page's Shots tab). A shot needs its final frame first (the Storyboard page). Every
clip is a paid render, so its price is shown before each button; the billed
figure lands in the world's cost log.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import streamlit as st

import api
from shared.state import show_notice
from shared.story import (
    build_zip, episode_url, excerpt, export_files, generate_shots, pick_episode, save_shot_setting, shot_label,
    shots_in_order,
)
from shared.ui import plural, top_bar
from shared.worlds import render_world_switcher


def clip_price(model: Dict, shot: Dict) -> float:
    return model['usd_per_second'] * shot['duration']


def renders(model: Dict, shot: Dict) -> bool:
    """Whether ``model`` renders a clip as long as the shot's."""
    return shot['duration'] in model['durations']


def money(usd: float) -> str:
    """A price for a label. The dollar sign is escaped, as two in one label would render as LaTeX."""
    return f"\\${usd:.2f}"


def render_controls(world: str, episode: str, shot: Dict, video: Dict, model: Dict, has_next_frame: bool) -> bool:
    """One line: the clip length and "end on the next shot" toggle (saved as soon as either changes) and the priced
    Generate or Regenerate button. The toggle needs a next shot with a final frame. Returns whether it was clicked."""
    length_col, next_col, button_col = st.columns([2, 2, 4], vertical_alignment='center')
    prefix = f"video_{world}_{episode}_{shot['id']}_"
    length_col.selectbox(
        "Length", video['durations'], index=video['durations'].index(shot['duration']),
        format_func=lambda seconds: f"{seconds} s", label_visibility='collapsed', help="Clip length",
        key=f"{prefix}duration_{shot['duration']}", on_change=save_shot_setting,
        args=(world, episode, shot['id'], 'duration', f"{prefix}duration_{shot['duration']}"),
    )
    next_col.toggle(
        "Next", value=shot['end_on_next'] and has_next_frame, disabled=not has_next_frame,
        help="End the clip on the next shot's final frame" if has_next_frame
        else "Needs a next shot with a final frame", key=f"{prefix}end_on_next", on_change=save_shot_setting,
        args=(world, episode, shot['id'], 'end_on_next', f"{prefix}end_on_next"),
    )
    label = "Regenerate" if shot.get('video_path') else "Generate"
    too_long = not renders(model, shot)
    return button_col.button(
        f"{label} · {money(clip_price(model, shot))}", key=f"video_{shot['id']}", width='stretch', disabled=too_long,
        help=f"{model['name']} renders up to {max(model['durations'])} s: shorten the clip or pick another model."
        if too_long else None,
    )


def is_stale(shot: Dict) -> bool:
    """True when the video was made from another frame, or before the shot or its length changed."""
    return bool(shot.get('video_path')) and shot['video_stale']


def shot_caption(scene: Dict, shot: Dict) -> str:
    return f"**{shot_label(scene, shot)}** · {excerpt(shot['action'])}"


def render_shot(world: str, episode: str, scene: Dict, shot: Dict, video: Dict, model: Dict,
                has_next_frame: bool) -> bool:
    """One shot as a row: its frame on the left, its video on the right, then one line beneath each,
    side by side: under the frame, a warning when the video is out of date; under the video, the clip length,
    "end on the next frame" toggle and priced button. Returns whether the button was clicked."""
    st.markdown(shot_caption(scene, shot))
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
        warning_col.warning("The frame, the shot or its length changed after this video. Regenerate to match.",
                            icon=":material/sync_problem:")
    with controls_col:
        return render_controls(world, episode, shot, video, model, has_next_frame)


def render_grid(world: str, episode: str, script: Dict, video: Dict, model: Dict) -> List[Tuple[str, str]]:
    """Every shot, scene by scene, as a frame | video row. Returns the shots whose button was clicked."""
    clicked = []
    for scene in script['scenes']:
        if not any(shot['id'] for shot in scene['shots']):
            continue
        st.subheader(f"{scene['number']}. {scene['heading']}")
        left, right = st.columns(2)
        left.caption("Frame")
        right.caption("Video")
        for number, shot in enumerate(scene['shots']):
            if not shot['id']:
                continue
            if number:
                st.divider()
            following = scene['shots'][number + 1:number + 2]
            has_next_frame = bool(following and following[0].get('final_path'))
            if render_shot(world, episode, scene, shot, video, model, has_next_frame):
                clicked.append((shot_label(scene, shot), shot['id']))
    return clicked


def render_sidebar(world: str, episode: str, script: Dict, video: Dict) -> Dict:
    """The model (saved on the episode as soon as it changes), its price, and Export all videos.
    Returns the model's details."""
    models = video['models']
    key = f"video_model_{world}_{episode}"
    with st.sidebar:
        name = st.selectbox(
            "Model", list(models), index=list(models).index(script['video_model']),
            format_func=lambda m: f"{models[m]['name']} · {models[m]['resolution']}", key=key,
            on_change=lambda: api.patch(episode_url(world, episode), json={'video_model': st.session_state[key]}),
        )
        model = models[name]
        st.caption(f"**{money(model['usd_per_second'])} per second** of clip (list price; the billed figure is "
                   f"logged). Up to {max(model['durations'])} s, no voices. The camera moves only as each "
                   "shot's action says.")
        files = export_files(script, 'video_path')
        # No "regenerate all": re-rendering every clip at once is too expensive to offer. One at a time only.
        st.download_button(
            "Export all videos", data=build_zip(files) if files else b"", file_name=f"{world}_{episode}_videos.zip",
            mime="application/zip", icon=":material/download:", width='stretch', disabled=not files,
            help="A zip of every video, named in story order." if files else "No videos yet.",
        )
    return {'key': name, **model}


def main() -> None:
    world, _ = render_world_switcher()
    episode = pick_episode(world, st.sidebar)
    if not episode:
        return
    script = api.get(episode_url(world, episode))
    video = api.options()['video']
    model = render_sidebar(world, episode, script, video)
    shots = shots_in_order(script)

    framed = [(shot_label(scene, shot), shot['id']) for scene, shot in shots if shot.get('final_path')]
    by_key = {(shot_label(scene, shot), shot['id']): shot for scene, shot in shots}
    with_video = {key for key, shot in by_key.items() if shot.get('video_path')}
    missing = [key for key in framed if key not in with_video]
    stale = [key for key, shot in by_key.items() if is_stale(shot)]
    # Pending: no video yet, or one made from an older frame. Kept in story order.
    pending = [key for key in framed if key in set(missing) | set(stale)]
    too_long = [key for key in pending if not renders(model, by_key[key])]
    pending = [key for key in pending if key not in too_long]

    generate_all = False
    with top_bar():
        status_col, action_col = st.columns([3, 1.4], vertical_alignment='center')
        status = [f"{len(framed) - len(pending) - len(too_long)} of {plural(len(framed), 'video')} up to date"]
        if missing:
            status.append(f"{len(missing)} not generated")
        if stale:
            status.append(f"{len(stale)} out of date")
        if too_long:
            status.append(f"{len(too_long)} too long for {model['name']}")
        if len(framed) < len(shots):
            status.append(f"{plural(len(shots) - len(framed), 'shot')} without a frame yet")
        status_col.caption(" · ".join(status) if shots else "No shots yet.")
        total = money(sum(clip_price(model, by_key[key]) for key in pending))
        generate_all = action_col.button(
            f"Generate {plural(len(pending), 'video')} · {total}" if pending else "Nothing pending",
            type="primary", width='stretch', disabled=not pending, icon=":material/auto_awesome:",
            help="Every shot with a frame but no video, plus every video that is out of date.",
        )
    show_notice()
    if not shots:
        st.info("This episode has no shots yet. Write them on the Script page.")
        return
    if not framed:
        st.info("No shot has a final frame yet. Generate them on the Storyboard, then animate them here.")
        if st.button("Go to the Storyboard"):
            st.switch_page("pages/storyboard.py")
        return

    clicked = render_grid(world, episode, script, video, model)
    to_generate = pending if generate_all else clicked
    if to_generate:
        generate_shots(world, episode, to_generate, "video", {'model': model['key']}, action="video")


main()
