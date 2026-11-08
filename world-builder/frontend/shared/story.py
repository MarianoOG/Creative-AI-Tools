"""Helpers shared by the Script and Storyboard pages: pickers, the scene editor and shot rendering."""

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
    return [(scene, shot) for scene in script['scenes'] for shot in scene['shots']]


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
    (``01_scene1_01_shot1.png``) so the files sort as the episode runs."""
    files = []
    for scene_number, scene in enumerate(script['scenes'], start=1):
        for shot_number, shot in enumerate(scene['shots'], start=1):
            if shot.get(key):
                suffix = Path(shot[key]).suffix
                files.append((f"{scene_number:02}_{scene['id']}_{shot_number:02}_{shot['id']}{suffix}", shot[key]))
    return tuple(files)


def generate_shots(world: str, episode: str, shots: List[Tuple[str, str]], what: str,
                   body: Optional[Dict] = None, action: str = "generate") -> None:
    """Render each ``(scene, shot)`` with the shot's ``action`` endpoint (``generate`` for the
    frame, ``video`` for the clip), ``PARALLEL_RENDERS`` at a time, then leave a notice for the rerun.

    Only the requests run in worker threads: Streamlit calls must stay on the
    script's own thread, so progress is written here as each render lands.
    """
    warnings = []
    with st.status(f"Generating {len(shots)} {what}(s), {PARALLEL_RENDERS} at a time... each can take a few minutes.") as status:
        with ThreadPoolExecutor(max_workers=PARALLEL_RENDERS) as pool:
            futures = {
                pool.submit(api.post, f"{episode_url(world, episode)}/scenes/{scene_id}/shots/{shot_id}/{action}", json=body):
                    f"{scene_id}/{shot_id}"
                for scene_id, shot_id in shots
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
    """Script field -> every reference of that type in the world (``name``, then each ``name:variation``), for the pickers."""
    names = {}
    for field, asset_type in REFERENCE_FIELDS.items():
        assets = api.get("/assets", world=world, asset_type=asset_type)['assets']
        names[field] = [
            ref
            for asset in assets if asset['variations']
            for ref in [asset['name'], *(variation['ref'] for variation in asset['variations'])]
        ]
    return names


def reference_label(reference: str) -> str:
    """``fox:older`` reads as ``fox · older``; a bare name is the asset's preferred image."""
    return reference.replace(":", " · ", 1) if ":" in reference else f"{reference} (preferred)"


def scene_fields(scene: Dict, names: Dict[str, List[str]], prefix: str) -> Dict:
    """Edit a scene's heading, summary and references. Returns the scene with the edits applied."""
    heading = st.text_input("Heading", value=scene['heading'], placeholder="INT. KITCHEN - DAY", key=f"{prefix}heading")
    summary = st.text_area("What happens", value=scene['summary'], height=90, key=f"{prefix}summary")
    picks = {}
    for field in REFERENCE_FIELDS:
        # Keep names whose asset is gone, so saving never drops them.
        options = names[field] + [name for name in scene[field] if name not in names[field]]
        picks[field] = st.multiselect(
            field.capitalize(), options, default=scene[field], format_func=reference_label, key=f"{prefix}{field}"
        )
    return {**scene, 'heading': heading, 'summary': summary, **picks}

