"""Episode: the whole script, scene by scene, as text. Each scene links to its storyboard."""

from __future__ import annotations

from html import escape
from typing import Dict, List

import streamlit as st

import api
from shared.state import notify, show_notice
from shared.story import asset_names, episode_url, open_storyboard, pick_episode, references_markdown, scene_fields
from shared.worlds import model_select, render_world_switcher


def save(world: str, episode: str, script: Dict, message: str) -> None:
    try:
        api.put(episode_url(world, episode), json=script)
    except api.ApiError as exc:
        st.error(str(exc))
        return
    notify('success', message)


def render_header(world: str, episode: str, script: Dict) -> None:
    options = api.options()
    with st.expander("Edit title, synopsis and storyboard settings"):
        title = st.text_input("Title", value=script['title'], key=f"title_{episode}")
        synopsis = st.text_area("Synopsis", value=script['synopsis'], key=f"synopsis_{episode}")
        model_col, ratio_col = st.columns(2)
        with model_col:
            provider = model_select(options, key=f"provider_{episode}", default=script['provider'])
        ratios = options['aspect_ratios']
        aspect_ratio = ratio_col.selectbox(
            "Aspect ratio", ratios, index=ratios.index(script['aspect_ratio']), key=f"ratio_{episode}"
        )
        st.caption("Every storyboard frame of the episode uses this model and aspect ratio, at low quality.")
        if st.button("Save", key=f"save_header_{episode}"):
            fields = {'title': title, 'synopsis': synopsis, 'provider': provider, 'aspect_ratio': aspect_ratio}
            save(world, episode, {**script, **fields}, "Saved.")
    st.title(script['title'])
    if script['synopsis']:
        st.write(f"*{script['synopsis']}*")
    st.caption(f"Storyboard: {options['providers'][script['provider']]} · {script['aspect_ratio']}")


def render_shots(shots: List[Dict]) -> None:
    for shot in shots:
        st.markdown(f"`{shot['id']}` {shot['action']}")
        for line in shot['dialogue']:
            speaker = escape(line['character'].upper() or "—")
            st.markdown(
                f"<div style='margin-left:3em'><b>{speaker}</b><br>{escape(line['line'])}</div>",
                unsafe_allow_html=True,
            )


def render_scene(world: str, episode: str, script: Dict, index: int, names: Dict) -> None:
    scene = script['scenes'][index]
    heading_col, open_col = st.columns([4, 1])
    heading_col.subheader(f"{index + 1}. {scene['heading'] or scene['id']}")
    if open_col.button("Storyboard", icon=":material/movie:", key=f"open_{scene['id']}", width='stretch'):
        open_storyboard(scene['id'])
    if scene['summary']:
        st.write(scene['summary'])
    if references_markdown(scene):
        st.caption(references_markdown(scene))
    render_shots(scene['shots'])

    edit_col, delete_col = st.columns([4, 1])
    with edit_col.expander("Edit scene"):
        edited = scene_fields(scene, names, prefix=f"ep_{episode}_{scene['id']}_")
        if st.button("Save scene", key=f"save_{scene['id']}"):
            scenes = [*script['scenes']]
            scenes[index] = edited
            save(world, episode, {**script, 'scenes': scenes}, f"Saved **{scene['id']}**.")
    with delete_col.popover("Delete", width='stretch'):
        st.warning(f"All {len(scene['shots'])} shots of **{scene['id']}** will be removed from the script (the folder is kept, hidden).")
        if st.button("Delete scene", icon=":material/delete:", key=f"delete_{scene['id']}"):
            api.delete(f"{episode_url(world, episode)}/scenes/{scene['id']}")
            notify('success', f"Deleted **{scene['id']}**.")


def render_new_scene(world: str, episode: str, count: int) -> None:
    name_col, button_col = st.columns([3, 1])
    name = name_col.text_input("New scene", placeholder=f"scene{count + 1}", label_visibility='collapsed')
    if button_col.button("Add scene", icon=":material/add:", type="primary", width='stretch'):
        try:
            created = api.post(f"{episode_url(world, episode)}/scenes", json={'name': name or f"scene{count + 1}"})
        except api.ApiError as exc:
            st.error(str(exc))
            return
        notify('success', f"Added **{created['name']}**.")


def main() -> None:
    world, _ = render_world_switcher()
    episode = pick_episode(world)
    if not episode:
        return
    script = api.get(episode_url(world, episode))
    render_header(world, episode, script)
    show_notice()

    names = asset_names(world)
    for index in range(len(script['scenes'])):
        st.divider()
        render_scene(world, episode, script, index, names)
    st.divider()
    render_new_scene(world, episode, len(script['scenes']))


main()
