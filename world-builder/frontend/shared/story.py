"""Helpers shared by the Script, Storyboard and Video pages: pickers, shot settings and shot rendering."""

from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import streamlit as st

import api
from shared.state import notify

#: Script field -> the asset type its names refer to.
REFERENCE_FIELDS = {'characters': 'character', 'locations': 'location', 'objects': 'object'}

#: How many shots render at once. Provider rate limits are the ceiling.
PARALLEL_RENDERS = 4


def episode_url(world: str, episode: str) -> str:
    return f"/worlds/{world}/episodes/{episode}"


def shots_in_order(script: Dict) -> List[Tuple[Dict, Dict]]:
    """Every shot that has an id (a shot added outside the app has none until the script is saved or reprocessed)."""
    return [(scene, shot) for scene in script['scenes'] for shot in scene['shots'] if shot['id']]


def shot_label(scene: Dict, shot: Dict) -> str:
    """``2.3``: the third shot of the second scene, as the script reads now."""
    return f"{scene['number']}.{shot['number']}"


def excerpt(text: str, limit: int = 140) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


@st.cache_data(show_spinner=False, max_entries=4)
def build_zip(files: Tuple[Tuple[str, str], ...]) -> bytes:
    """A zip of ``(name in the zip, data-relative path)`` pairs. Cached on the paths, which change with every render."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_STORED) as archive:  # images and videos are already compressed
        for name, path in files:
            archive.write(api.file_path(path), name)
    return buffer.getvalue()


def export_files(script: Dict, key: str) -> Tuple[Tuple[str, str], ...]:
    """Every shot's file under ``key`` (``final_path`` or ``video_path``), named in story order
    (``01_03_a3f9c2.png``: scene, shot, shot id) so the files sort as the episode runs."""
    files = []
    for scene in script['scenes']:
        for shot in scene['shots']:
            if shot.get(key):
                suffix = Path(shot[key]).suffix
                files.append((f"{scene['number']:02}_{shot['number']:02}_{shot['id']}{suffix}", shot[key]))
    return tuple(files)


def generate_shots(world: str, episode: str, shots: List[Tuple[str, str]], what: str,
                   body: Optional[Dict] = None, action: str = "generate") -> None:
    """Render each ``(label, shot id)`` with the shot's ``action`` endpoint (``generate`` for the
    frame, ``video`` for the clip), ``PARALLEL_RENDERS`` at a time, then leave a notice for the rerun.

    Only the requests run in worker threads: Streamlit calls must stay on the
    script's own thread, so progress is written here as each render lands.
    """
    warnings = []
    with st.status(f"Generating {len(shots)} {what}(s), {PARALLEL_RENDERS} at a time... each can take a few minutes.") as status:
        with ThreadPoolExecutor(max_workers=PARALLEL_RENDERS) as pool:
            futures = {
                pool.submit(api.post, f"{episode_url(world, episode)}/shots/{shot_id}/{action}", json=body):
                    f"shot {label}"
                for label, shot_id in shots
            }
            for done, future in enumerate(as_completed(futures), start=1):
                try:
                    future.result()
                    status.write(f"`{futures[future]}` done ({done}/{len(shots)}).")
                except api.ApiError as exc:
                    warnings.append(f"{futures[future]}: {exc}")
                    status.write(f"`{futures[future]}` failed ({done}/{len(shots)}).")
    if warnings:
        notify('warning', f"Generated {len(shots) - len(warnings)} of {len(shots)} {what}(s). Failed: " + "; ".join(warnings))
    else:
        notify('success', f"Generated {len(shots)} {what}(s).")


def save_shot_setting(world: str, episode: str, shot_id: str, field: str, key: str) -> None:
    """Save one shot setting (``duration``, ``end_on_next``, ``characters`` or ``objects``) as picked in widget
    ``key``. Runs as the widget's on_change."""
    try:
        api.patch(f"{episode_url(world, episode)}/shots/{shot_id}", json={field: st.session_state[key]})
    except api.ApiError as exc:
        st.session_state.notice = ('error', f"Could not save the shot: {exc}")


def pick_episode(world: str, container=st) -> Optional[str]:
    """The episode select box, drawn in ``container`` (the page, or ``st.sidebar``). Remembers the choice in ``current_episode``."""
    episodes = api.get(f"/worlds/{world}/episodes")['episodes']
    if not episodes:
        st.info(f"No episodes in **{world}** yet. Create one from the Episodes tab of the World page.")
        if st.button("Go to the World page"):
            st.switch_page("pages/world.py")
        return None
    names = [episode['name'] for episode in episodes]
    titles = {episode['name']: episode['title'] for episode in episodes}
    current = st.session_state.current_episode if st.session_state.current_episode in names else names[0]
    st.session_state.current_episode = container.selectbox(
        "Episode", names, index=names.index(current), format_func=lambda n: f"{n} · {titles[n]}"
    )
    return st.session_state.current_episode


def asset_names(world: str) -> Dict[str, List[str]]:
    """Script field -> every reference of that type in the world (``name``, then each ``name:variation``), for the
    tag pickers. An asset with no image yet is listed too: the text model can tag it, and its description is used."""
    names = {}
    for field, asset_type in REFERENCE_FIELDS.items():
        assets = api.get("/assets", world=world, asset_type=asset_type)['assets']
        names[field] = [
            ref
            for asset in assets
            for ref in [asset['name'], *(variation['ref'] for variation in asset['variations'])]
        ]
    return names


def reference_label(reference: str) -> str:
    """``fox:older`` reads as ``fox · older``; a bare name is the asset's preferred image."""
    return reference.replace(":", " · ", 1) if ":" in reference else f"{reference} (preferred)"
