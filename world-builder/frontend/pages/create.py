"""Create: generate an asset from a description, a style and optional references.

Characters, objects and locations take uploaded references (never saved).
Scenes pick existing assets from the current world.
"""

from __future__ import annotations

from typing import Dict, List

import streamlit as st

import api
from shared.worlds import render_world_switcher

UPLOAD_TYPES = ["png", "jpg", "jpeg", "webp"]

#: What the ``None`` style is called on screen.
FOLLOW_LABEL = "Follow references"


def render_form(options: Dict) -> Dict:
    asset_type = st.radio(
        "Asset type", options['asset_types'], format_func=str.capitalize, horizontal=True, key='asset_type'
    )
    scene = asset_type == "scene"
    name = st.text_input(
        "Name",
        placeholder="asset_name",
        help="Used for the filename. Spaces and punctuation become underscores.",
        key='asset_name',
    )
    description = st.text_area(
        "Description",
        placeholder=("asset_description"),
        help="The situation to depict." if scene else "The subject to design.",
        height=120,
        key='asset_description',
    )
    style_col, ratio_col, quality_col = st.columns(3)
    return {
        'asset_type': asset_type,
        'name': name,
        'description': description,
        'style': style_col.selectbox(
            "Style", options['styles'], format_func=lambda s: FOLLOW_LABEL if s is None else s, key='style'
        ),
        'aspect_ratio': ratio_col.selectbox("Aspect ratio", options['aspect_ratios'], key='aspect_ratio'),
        'quality': quality_col.selectbox("Quality", options['qualities'], key='quality'),
    }


def render_upload_references(follow: bool) -> List:
    st.subheader("Reference images")
    st.caption(
        "Required here: the art style is copied from these images. These files are not saved."
        if follow
        else "Optional. Used as inspiration for the world, palette and mood - "
        "never for the art style. These files are not saved."
    )
    return st.file_uploader("Upload references", type=UPLOAD_TYPES, accept_multiple_files=True, key='uploads') or []


def render_library_references(follow: bool, world: str, reference_types: List[str]) -> List[str]:
    """Pick the existing assets of ``world`` a scene should reproduce."""
    st.subheader("Reference assets")
    st.caption(
        "Scenes treat these as authority: the designs are reproduced faithfully. "
        f"Pick any number of characters, objects and locations from **{world}**."
        + (
            " With no style picked each one also keeps its own art style, so "
            "the frame is not unified into one look."
            if follow
            else ""
        )
    )

    labels: Dict[str, str] = {}
    selected: List[str] = []
    for column, asset_type in zip(st.columns(len(reference_types)), reference_types):
        assets = api.get("/assets", world=world, asset_type=asset_type)['assets']
        labels.update({asset['path']: asset['label'] for asset in assets})
        with column:
            if not assets:
                st.caption(f"No {asset_type}s in this world yet.")
                continue
            selected += st.multiselect(
                f"{asset_type.capitalize()}s",
                [asset['path'] for asset in assets],
                format_func=lambda path: labels.get(path, path),
                key=f"scene_refs_{asset_type}",
            )

    if selected:
        for column, path in zip(st.columns(min(len(selected), 6)), selected):
            column.image(str(api.file_path(path)), caption=labels.get(path), width='stretch')
    return selected


def generate(fields: Dict, world: str, references: List) -> None:
    """Send the form to the backend, wait for the images and show them."""
    data = {**fields, 'world': world}
    if data['style'] is None:
        del data['style']  # "Follow references": a form field cannot be None
    files = None
    if fields['asset_type'] == "scene":
        data['references'] = references
    else:
        files = [('uploads', (upload.name, upload.getvalue(), upload.type)) for upload in references]

    with st.spinner("Generating... this can take a few minutes."):
        try:
            result = api.post("/assets/generate", data=data, files=files)
        except api.ApiError as exc:
            st.error(str(exc))
            return

    if result['warning']:
        st.warning(f"One provider failed: {result['warning']}")
    st.success("Saved to the library.")
    for column, asset in zip(st.columns(6), result['assets']):
        column.image(str(api.file_path(asset['path'])), caption=asset['label'], width='stretch')


def main() -> None:
    options = api.options()
    world, _ = render_world_switcher()

    st.title("✨ Create an asset")
    st.caption(
        f"Generating into **{world}**. Characters, objects and locations are "
        "reference sheets; scenes are finished frames."
    )
    if st.button("← Back to library"):
        st.switch_page("pages/library.py")

    st.divider()
    fields = render_form(options)

    st.divider()
    follow = fields['style'] is None
    if fields['asset_type'] == "scene":
        references = render_library_references(follow, world, options['reference_types'])
    else:
        references = render_upload_references(follow)

    st.divider()
    has_text = bool(fields['name'].strip() and fields['description'].strip())
    # With no style there is nothing to render from, so references are required.
    missing_references = follow and not references
    if st.button("Generate", type="primary", disabled=not has_text or missing_references):
        generate(fields, world, references)
    if not has_text:
        st.caption("A name and a description are required.")
    if missing_references:
        st.caption(f"**{FOLLOW_LABEL}** takes the look from the references, so at least one is required.")


main()
