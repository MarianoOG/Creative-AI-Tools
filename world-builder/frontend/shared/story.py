"""Helpers shared by the Script and Storyboard pages: pickers and the scene editor."""

from __future__ import annotations

from typing import Dict, List, Optional

import streamlit as st

import api

#: Script field -> the asset type its names refer to.
REFERENCE_FIELDS = {'characters': 'character', 'locations': 'location', 'objects': 'object'}


def episode_url(world: str, episode: str) -> str:
    return f"/worlds/{world}/episodes/{episode}"


def pick_episode(world: str) -> Optional[str]:
    """The episode select box. Remembers the choice in ``current_episode``."""
    episodes = api.get(f"/worlds/{world}/episodes")['episodes']
    if not episodes:
        st.info(f"No episodes in **{world}** yet. Create one from the Episodes tab of the World page.")
        if st.button("Go to the World page"):
            st.switch_page("pages/world.py")
        return None
    names = [episode['name'] for episode in episodes]
    titles = {episode['name']: episode['title'] for episode in episodes}
    current = st.session_state.current_episode if st.session_state.current_episode in names else names[0]
    chosen = st.selectbox(
        "Episode", names, index=names.index(current), format_func=lambda n: f"{n} · {titles[n]}"
    )
    if chosen != st.session_state.current_episode:
        st.session_state.current_episode = chosen
    return chosen


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
    for column, field in zip(st.columns(len(REFERENCE_FIELDS)), REFERENCE_FIELDS):
        # Keep names whose asset is gone, so opening the editor never drops them.
        options = names[field] + [name for name in scene[field] if name not in names[field]]
        picks[field] = column.multiselect(
            field.capitalize(), options, default=scene[field], format_func=reference_label, key=f"{prefix}{field}"
        )
    return {**scene, 'heading': heading, 'summary': summary, **picks}


def references_markdown(scene: Dict) -> str:
    parts = [
        f"**{field.capitalize()}:** " + ", ".join(f"`{reference_label(name)}`" for name in scene[field])
        for field in REFERENCE_FIELDS
        if scene[field]
    ]
    return "  \n".join(parts)
