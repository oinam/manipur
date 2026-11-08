"""Semantic color slots, the Phase 0 placeholder palette, and candidate palettes."""

SLOTS = (
    "background",
    "tree",
    "shrub",
    "grass",
    "crop",
    "built",
    "bare",
    "wetland",
    "water",
    "road_major",
    "road_minor",
    "road_track",
    "road_line",
    "wall_lit",
    "wall_shade",
    "roof_0",
    "roof_1",
    "roof_2",
    "roof_3",
    "roof_4",
    "roof_5",
)
SLOT = {name: index for index, name in enumerate(SLOTS)}
ROOF_SLOTS = tuple(SLOT[f"roof_{index}"] for index in range(6))

_TREE = "#3f6b3a"
_GRASS = "#7da04f"
_CROP = "#b4c066"
_BUILT = "#bcae90"
_WATER = "#3f7fb0"
_SHADOW = "#55586a"
_LIGHT = "#ddd3c2"
_ROOF = "#b5533c"

# Eight colors, for judging the geometry without being distracted by the look.
PLACEHOLDER = dict(
    zip(
        SLOTS,
        (
            _SHADOW,  # background
            _TREE,  # tree
            _GRASS,  # shrub
            _GRASS,  # grass
            _CROP,  # crop
            _BUILT,  # built
            _BUILT,  # bare
            _GRASS,  # wetland
            _WATER,  # water
            _SHADOW,  # road_major
            _SHADOW,  # road_minor
            _BUILT,  # road_track
            _LIGHT,  # road_line
            _LIGHT,  # wall_lit
            _SHADOW,  # wall_shade
            _ROOF,  # roof_0
            _ROOF,  # roof_1
            _ROOF,  # roof_2
            _LIGHT,  # roof_3
            _LIGHT,  # roof_4
            _LIGHT,  # roof_5
        ),
        strict=True,
    )
)


def _palette(*colors: str) -> dict[str, str]:
    return dict(zip(SLOTS, colors, strict=True))


# Candidates for Brajeshwar to choose from. None of these is a decision.
CANDIDATES = {
    "monsoon": _palette(
        "#1f2a2e",
        "#2f5d3a",
        "#4f7d43",
        "#79a650",
        "#b9c96a",
        "#c3b596",
        "#a8926d",
        "#6f9c7a",
        "#3a86a8",
        "#4b4d57",
        "#6c6e78",
        "#a78f68",
        "#e8dfb8",
        "#e6dccb",
        "#8f8a94",
        "#b5533c",
        "#c9744a",
        "#8a4a3a",
        "#9fb0b8",
        "#d8d2c4",
        "#6f8796",
    ),
    "retro": _palette(
        "#2b2440",
        "#3c8d4f",
        "#62b25a",
        "#8fd16a",
        "#d6e07c",
        "#d9c79e",
        "#c2a878",
        "#7dbf9b",
        "#4aa3df",
        "#5c5a66",
        "#7f7d8a",
        "#b89a6a",
        "#fff2a8",
        "#f5ead6",
        "#a59bb5",
        "#d9503f",
        "#ee8a3c",
        "#a8452f",
        "#7fb6d6",
        "#f0e6d2",
        "#5f8fb0",
    ),
    "dusk": _palette(
        "#141629",
        "#27474e",
        "#3b5f5c",
        "#5a7d6a",
        "#8f9a6f",
        "#8a7f8f",
        "#756a7a",
        "#4f7480",
        "#2f5f8a",
        "#34344e",
        "#4c4c6a",
        "#7a6a70",
        "#f0c674",
        "#c8b8c8",
        "#5a5478",
        "#a0465a",
        "#c2695a",
        "#7a3a55",
        "#6f85a5",
        "#b0a8b8",
        "#4f6585",
    ),
    "earthen": _palette(
        "#2a1f1a",
        "#55682f",
        "#7a8a3f",
        "#a2a653",
        "#d2c374",
        "#cdb48c",
        "#b0905f",
        "#8a9a6a",
        "#5a8f96",
        "#57483f",
        "#786656",
        "#a5845a",
        "#efe0b0",
        "#ead9bd",
        "#94806c",
        "#8e2f2a",
        "#b5562f",
        "#6a2c2a",
        "#a39a86",
        "#ddcfb4",
        "#7f7a68",
    ),
}


def lookup(palette: dict[str, str]) -> bytes:
    """Return a 768-byte PIL palette with colors in slot order."""
    values = bytearray(768)
    for index, name in enumerate(SLOTS):
        color = palette[name].lstrip("#")
        values[index * 3 : index * 3 + 3] = bytes.fromhex(color)
    return bytes(values)
