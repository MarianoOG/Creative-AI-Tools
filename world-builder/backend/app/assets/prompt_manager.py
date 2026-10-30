"""Prompt composition for characters, objects, locations and storyboard shots. Pure data plus :func:`build_prompt`, no I/O.

A prompt is ``description -> style clause -> framing -> reference clause``.
Framing comes after the style, so it has the last word on layout and lighting.
The style clause is the world's style (in ``world.json``); :data:`STYLES` are the presets
new worlds start from.
"""

from __future__ import annotations

#: Asset type -> the folder its files live in, inside a world.
ASSET_DIRS: dict[str, str] = {
    "character": "characters",
    "location": "locations",
    "object": "objects",
}

#: Written long on purpose: a one-word label ("anime") gives the model too little to go on.
STYLES: dict[str, str] = {
    "flat_2d": (
        "Modern flat 2D vector animation style: clean uniform-weight outlines, "
        "large areas of flat unshaded colour, simple geometric shape language, a "
        "limited bright palette of six to eight hues, no gradients and no texture."
    ),
    "anime_cel": (
        "Japanese cel-animation style: crisp dark ink outlines of varying weight, "
        "two-tone cel shading with hard-edged shadow shapes, saturated but "
        "naturalistic colour, expressive large eyes, subtle rim light on the "
        "silhouette."
    ),
    "pixar_3d": (
        "Polished 3D CG animated-feature style: soft rounded appealing forms, "
        "subsurface-scattering skin, physically based materials, warm cinematic "
        "three-point lighting with soft shadows, shallow depth of field, high "
        "render fidelity."
    ),
    "stop_motion_clay": (
        "Handmade stop-motion claymation style: visible fingerprints and tool "
        "marks in the plasticine, slightly lumpy hand-sculpted forms, matte clay "
        "surface, practical soft studio lighting with real contact shadows, "
        "tangible miniature-set feel."
    ),
    "watercolor_storybook": (
        "Hand-painted watercolour storybook style: soft wet-on-wet colour washes "
        "with visible pigment blooms and paper grain, loose graphite underdrawing "
        "showing through, muted earthy palette, gentle diffuse light, edges that "
        "fade rather than stop."
    ),
    "comic_ink": (
        "Bold inked comic-book style: heavy brush-inked contours, dense "
        "cross-hatching and spotted blacks for shadow, halftone dot texture in the "
        "midtones, punchy high-contrast primary colours, dramatic directional "
        "lighting."
    ),
    "retro_cartoon_1930s": (
        "1930s rubber-hose cartoon style: bendy limbs without visible joints, "
        "pie-cut eyes and white gloves, thick tapering ink lines, sepia and "
        "cream limited palette with soft film grain and subtle vignetting, "
        "vintage animation-cel look."
    ),
    "pixel_art": (
        "Hand-crafted pixel art style: low resolution grid with large crisp square "
        "pixels and no anti-aliasing, deliberate dithering for gradients, a tight "
        "indexed palette of about sixteen colours, strong readable silhouettes, "
        "16-bit era game-sprite look."
    ),
    "low_poly_3d": (
        "Stylised low-poly 3D style: faceted geometry with visible flat triangular "
        "planes, hard flat-shaded facets and no smoothing, untextured solid colour "
        "materials, clean studio lighting, crisp geometric silhouette."
    ),
    "paper_cutout": (
        "Layered paper cutout animation style: shapes cut from textured coloured "
        "card with visible fibrous torn and scissor-cut edges, distinct stacked "
        "depth layers casting small soft drop shadows onto the layer beneath, matte "
        "paper surface."
    ),
    "ligne_claire_color": (
        "Ligne claire children's book illustration style in the Tintin and Hergé "
        "tradition: bold uniform-weight black outlines around every object and "
        "shape, flat solid fills with no gradients, no soft shading, no painterly "
        "texture and no photorealistic lighting. Real locations and objects stay "
        "clearly recognisable in their proportions and layout but are rendered as "
        "clean illustration, with simplified textures — wood grain as a few clean "
        "lines, foliage as solid rounded masses, ground as one flat tone with "
        "minimal detail. Warm inviting palette, high contrast, evenly lit with no "
        "dramatic shadow work. Print-ready flat illustration, not a render."
    ),
    "ligne_claire_lineart": (
        "Pure ligne claire line art: black outlines only on a white background, "
        "with nothing filled in, no shading, no crosshatching and no gradients. "
        "Uniform line weight throughout. Every shape is defined entirely by clean "
        "confident black contour lines, so objects and locations stay clearly "
        "recognisable by silhouette and structure alone. Ready for print or "
        "colouring-book use."
    ),
}

#: Style slots older filenames carry (``{name}_{style}_{uuid8}_{provider}``). New files have none.
LEGACY_STYLE_SLUGS = (*STYLES, "follow_references")

# Characters and objects are reference sheets for later animation steps, so
# their layout is fixed here. Locations are empty background plates.
CHARACTER_FRAMING = (
    "Render this as a character turnaround reference sheet. Pure solid white "
    "seamless background. Full body, head to feet, standing upright in a neutral "
    "relaxed A-pose with the arms held slightly away from the torso and the legs "
    "straight. Show exactly three views of the same character in a single image, "
    "arranged in one horizontal row, left to right: front view, three-quarter "
    "view (turned about 45 degrees), back view. No side profile view. All three "
    "views share the same character design, the same scale, the same height, and "
    "the same eye line. Even flat lighting with no cast shadow on the backdrop. "
    "No props, no accessories beyond the described costume, no scenery, no text, "
    "no labels, no borders or panel frames."
)

OBJECT_FRAMING = (
    "Render this as an object turnaround reference sheet. Pure solid white "
    "seamless background. Show exactly two views of the same object in a single "
    "image, arranged in one horizontal row, left to right: a front isometric view "
    "(seen from the front, slightly above and to one side, so the front, one side "
    "and the top read at once, with parallel edges and no vanishing point), and a "
    "flat side view along the X axis. Exactly two views and no others — no "
    "separate top view, no back view. Both views share the same object design, "
    "scale and lighting. The object is isolated and centred in each view. Even "
    "flat lighting, no cast shadow on the backdrop, no ground plane. No "
    "characters, no people, no hands holding the object, no text, no labels, no "
    "dimension lines, no borders."
)

# Location and shot framings are split around their one lighting sentence,
# which line-only styles swap out (see MONOCHROME_FRAMING).
_LOCATION_COMPOSITION = (
    "Render this as an empty background plate for animation. The environment is "
    "completely unoccupied: no characters, no people, no figures, no crowds, no "
    "animals, and no foreground subject of any kind anywhere in the frame. "
)

#: The fixed views every location is rendered in, in order. The first is the
#: establishing view; the others are rendered from it as the same place.
LOCATION_VIEWS: dict[str, str] = {
    "establishing": (
        "Wide establishing view of the space itself with a consistent single-point "
        "perspective and a clear horizon. "
    ),
    "reverse": (
        "Reverse angle: the camera stands on the far side of the space and looks "
        "back towards where the establishing view was taken, so the opposite side "
        "of the same place fills the frame, with a consistent single-point "
        "perspective and a clear horizon. "
    ),
    "detail": (
        "Closer medium view at eye level of one characteristic corner of the space, "
        "framed as a backdrop a character could stand in, with the ground visible. "
    ),
}
_LOCATION_TAIL = "No text, no signage lettering, no watermarks, no borders."

_SHOT_COMPOSITION = (
    "Render this as a single finished composed frame depicting the situation "
    "described above. Compose it cinematically with a clear focal subject, a "
    "readable staging of every element mentioned, and depth between foreground, "
    "midground and background. Keep the characters, objects and environment "
    "exactly consistent with their reference designs. "
)
_SHOT_TAIL = "No text, no captions, no borders."

#: For line-only styles, where a lighting or colour-grade sentence would contradict the style.
_MONOCHROME_RENDERING = (
    "Describe the whole frame with black contour lines alone: depth and "
    "separation come from overlap, scale and line, never from tone, fill or "
    "shadow. "
)

_LOCATION_LIGHTING = (
    "Light the environment as a usable backdrop, readable across the whole "
    "frame with nothing blown out and nothing crushed to black. "
)

FRAMING: dict[str, str] = {
    "character": CHARACTER_FRAMING,
    "object": OBJECT_FRAMING,
    "location": _LOCATION_COMPOSITION + "{view}" + _LOCATION_LIGHTING + _LOCATION_TAIL,
    "shot": _SHOT_COMPOSITION + "Unified lighting and colour grade across the whole frame. " + _SHOT_TAIL,
}

#: Framings for line-only styles. Matched on the exact preset text, so an edited style gets the default framing.
MONOCHROME_FRAMING: dict[str, str] = {
    "location": _LOCATION_COMPOSITION + "{view}" + _MONOCHROME_RENDERING + _LOCATION_TAIL,
    "shot": _SHOT_COMPOSITION + _MONOCHROME_RENDERING + _SHOT_TAIL,
}
_MONOCHROME_STYLES = {STYLES["ligne_claire_lineart"]}

#: How references are used. New characters, objects and locations take them as
#: inspiration (never for the style); variations, location views and shots take
#: them as designs to reproduce.
REFERENCE_CLAUSES: dict[str, str] = {
    "character": (
        "Reference images are provided as inspiration, not as something to copy. "
        "Do not adopt the art style, rendering, linework or medium of the "
        "reference images — the style is defined by the style description above "
        "and overrides anything seen in the references. If a reference shows "
        "another character, do not reproduce or clone that character: take only "
        "cues such as the world it belongs to, its palette, its costume language "
        "and its level of stylisation, so the new character plausibly lives "
        "alongside it. If a reference shows an object or a place instead, read the "
        "colours, materials, era and mood from it and design a character who "
        "would inhabit that world and use those objects. The described character "
        "above is always the subject; the references only inform it."
    ),
    "object": (
        "Reference images are provided as inspiration, not as something to copy. "
        "Do not adopt the art style, rendering, linework or medium of the "
        "reference images — the style is defined by the style description above "
        "and overrides anything seen in the references. If a reference shows "
        "another object, take only cues such as its materials, wear, construction "
        "language and palette so the new object reads as belonging to the same "
        "world and the same maker, without duplicating it. If a reference shows a "
        "character or a place instead, extract the palette, mood, era and material "
        "vocabulary and design an object that would belong in that world or be "
        "carried and used by that character, scaled and shaped to suit them. The "
        "described object above is always the subject; the references only inform it."
    ),
    "location": (
        "Use the reference images as the source of the world: carry across their "
        "palette, mood, era, architecture, materials and recurring design "
        "elements. Build the described location as a spin-off of that world — a "
        "neighbouring, adjacent or related place, not a reproduction of any place "
        "shown. If a reference shows characters or objects, do not include them in "
        "the frame; instead treat them as the inhabitants this plate must suit, and "
        "build a background they could plausibly stand in or that those objects "
        "would be found in, matched to their scale and their world. The style is "
        "defined by the style description above and overrides the rendering of the "
        "references."
    ),
    "shot": (
        "Use the attached reference images as the authority for this frame. They "
        "are fact, not inspiration: reproduce the identity, design, proportions, "
        "costume, materials and colour palette of every subject they depict "
        "faithfully and consistently. Do not redesign, restyle, simplify or "
        "substitute them — a viewer must recognise each one as the same character, "
        "object and place. Where a reference shows an environment, keep its layout, "
        "architecture and palette as the setting of this frame. Ignore only the "
        "sheet layout of the references themselves (the multiple views and the "
        "blank backdrop); their designs are what carry over."
    ),
    "variation": (
        "The first reference image is the established design of this subject, and "
        "it is fact, not inspiration: keep its identity, face, proportions, "
        "silhouette, materials and colour palette exactly, and change only what the "
        "variation above describes. A viewer must recognise it as the same subject. "
        "Any further reference images are inspiration for that change only; do not "
        "adopt their art style. The style is defined by the style description above."
    ),
    "view": (
        "The reference image is the establishing view of this exact location, and "
        "it is fact, not inspiration. Show the same place — the same layout, "
        "architecture, materials, palette, weather and time of day — only from the "
        "camera position described here. Do not invent a different or neighbouring "
        "place, and keep it empty of figures."
    ),
}


def variation_description(description: str, variation: str, change: str) -> str:
    """What a variation of a character or object shows: the subject, then what is different."""
    return f"{description.strip()}\n\nVariation \"{variation}\": {change.strip()}"


def build_prompt(
    asset_type: str,
    description: str,
    style: str,
    clause: str | None = None,
    view: str = "establishing",
) -> str:
    """Compose the full prompt for one image. For a shot, ``description`` is the situation to depict.

    ``clause`` names the :data:`REFERENCE_CLAUSES` entry for the attached
    references (``None`` when there are none). ``view`` is the camera of a location.
    """
    if asset_type not in FRAMING:
        raise ValueError(f"asset_type must be one of {sorted(FRAMING)}, got {asset_type!r}")
    if not style.strip():
        raise ValueError("this world has no style yet - write one in the sidebar")
    if not description.strip():
        raise ValueError("description must not be empty")

    framing = FRAMING[asset_type]
    if style.strip() in _MONOCHROME_STYLES:
        framing = MONOCHROME_FRAMING.get(asset_type, framing)
    framing = framing.replace("{view}", LOCATION_VIEWS[view])
    parts = [description.strip(), style.strip(), framing]
    if clause:
        parts.append(REFERENCE_CLAUSES[clause])
    return "\n\n".join(parts)
