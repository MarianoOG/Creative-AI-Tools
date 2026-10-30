"""Create: generate a character, location or object in the current world's style."""

from __future__ import annotations

from typing import Dict, List

import streamlit as st

import api
from shared.worlds import render_world_switcher

UPLOAD_TYPES = ["png", "jpg", "jpeg", "webp"]
PLACEHOLDERS = {
    'character': "a lanky fox in a patched wool coat, tall ears, tired eyes",
    'location': "a night market street with paper lanterns and wet cobbles",
    'object': "a dented brass lantern with a candle inside",
}


def render_form(options: Dict) -> Dict:
    types = options['asset_types']
    asset_type = st.radio(
        "Asset type",
        types,
        index=types.index(st.session_state.create_type),
        format_func=str.capitalize,
        horizontal=True,
    )
    st.session_state.create_type = asset_type
    name = st.text_input(
        "Name",
        placeholder="fox_hero",
        help="Used for the filename and in scripts. Spaces and punctuation become underscores.",
        key='asset_name',
    )
    description = st.text_area(
        "Description", placeholder=PLACEHOLDERS[asset_type], height=120, key='asset_description'
    )
    ratio_col, quality_col = st.columns(2)
    return {
        'asset_type': asset_type,
        'name': name,
        'description': description,
        'aspect_ratio': ratio_col.selectbox("Aspect ratio", options['aspect_ratios'], key='aspect_ratio'),
        'quality': quality_col.selectbox("Quality", options['qualities'], key='quality'),
    }


def generate(fields: Dict, world: str, uploads: List) -> None:
    """Send the form to the backend, wait for the images and show them."""
    files = [('uploads', (upload.name, upload.getvalue(), upload.type)) for upload in uploads]
    with st.spinner("Generating... this can take a few minutes."):
        try:
            result = api.post("/assets/generate", data={**fields, 'world': world}, files=files or None)
        except api.ApiError as exc:
            st.error(str(exc))
            return

    if result['warning']:
        st.warning(f"One provider failed: {result['warning']}")
    st.success("Saved to the world.")
    for column, asset in zip(st.columns(6), result['assets']):
        column.image(str(api.file_path(asset['path'])), caption=asset['label'], width='stretch')


def main() -> None:
    options = api.options()
    world, _ = render_world_switcher()

    st.title("✨ Create an asset")
    st.caption(f"Generating into **{world}**, in the style from the sidebar.")
    if st.button("← Back to the world"):
        st.switch_page("pages/world.py")

    st.divider()
    fields = render_form(options)
    uploads = st.file_uploader(
        "Reference images (optional)",
        type=UPLOAD_TYPES,
        accept_multiple_files=True,
        key='uploads',
        help="Inspiration for palette and mood, never for the art style. Not saved.",
    ) or []

    st.divider()
    has_text = bool(fields['name'].strip() and fields['description'].strip())
    if st.button("Generate", type="primary", disabled=not has_text):
        generate(fields, world, uploads)
    if not has_text:
        st.caption("A name and a description are required.")


main()
