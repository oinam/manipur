"""Render candidate Sangai sprites over Keibul Lamjao, for Brajeshwar to choose from.

The Sangai is the brow-antlered deer of Loktak's floating phumdis, about 1.5 m long. At the
map's 0.5 m/px a real-size deer is a speck, so the options are drawn at one, two, and three
times real size, like the airliner. Each is a hand-made pixel sprite facing right, with a
second walking frame; the viewer would mirror it to face left. The coat colors are mixed
from the palette. Writes out/loktak/sangai-options.png.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

from manipur.detail import _mix, detail_colors

OUT = Path("out/loktak/sangai-options.png")
ZOOM = 6  # the close-up panels
COLORS = detail_colors()
PAINT = {
    "b": _mix(COLORS["roof_2"], COLORS["roof_1"], 0.35),  # reddish-brown coat
    "d": _mix(COLORS["roof_2"], COLORS["background"], 0.45),  # coat in shade, legs
    "w": _mix(COLORS["wall_lit"], "#ffffff", 0.3),  # pale rump and belly
    "a": COLORS["road_line"],  # antler
    "o": COLORS["background"],  # outline
}

# Facing right: rump at the left, head at the right. "." is clear.
SPRITES = {
    "1x": {
        "stag": [["..a", "bbb", "d.d"], ["..a", "bbb", ".d."]],
        "hind": [["..b", "bbb", "d.d"], ["..b", "bbb", ".d."]],
    },
    "2x": {
        "stag": [
            [".....a.a", "......a.", "......bb", "wbbbbbd.", "wbbbbb..", ".d.d.d.."],
            [".....a.a", "......a.", "......bb", "wbbbbbd.", "wbbbbb..", "..d..d.."],
        ],
        "hind": [
            [".......", "......b", ".....bb", "wbbbbd.", "wbbbb..", ".d.d.d."],
            [".......", "......b", ".....bb", "wbbbbd.", "wbbbb..", "..d..d."],
        ],
    },
    "3x": {
        "stag": [
            [
                "........a..a",
                ".......a..a.",
                "........aa..",
                ".........bb.",
                "........bbbb",
                "........bd..",
                "wbbbbbbbbd..",
                "wbbbbbbbb...",
                ".wddddddd...",
                ".d.d...d.d..",
                ".d.d...d.d..",
            ],
            [
                "........a..a",
                ".......a..a.",
                "........aa..",
                ".........bb.",
                "........bbbb",
                "........bd..",
                "wbbbbbbbbd..",
                "wbbbbbbbb...",
                ".wddddddd...",
                "..dd....dd..",
                ".d..d..d..d.",
            ],
        ],
        "hind": [
            [
                "..........",
                "..........",
                "........b.",
                ".......bbb",
                ".......bd.",
                "wbbbbbbbd.",
                "wbbbbbbb..",
                ".wdddddd..",
                ".d.d..d.d.",
                ".d.d..d.d.",
            ],
            [
                "..........",
                "..........",
                "........b.",
                ".......bbb",
                ".......bd.",
                "wbbbbbbbd.",
                "wbbbbbbb..",
                ".wdddddd..",
                "..dd...dd.",
                ".d..d.d..d",
            ],
        ],
    },
}


def outlined(rows: list[str]) -> list[str]:
    """Add a one-pixel dark edge around the sprite, so it reads on bright paddy and phumdi."""
    height, width = len(rows) + 2, len(rows[0]) + 2
    grid = [["."] * width for _ in range(height)]
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            if cell != ".":
                grid[y + 1][x + 1] = cell
    edged = [row[:] for row in grid]
    for y in range(height):
        for x in range(width):
            if grid[y][x] == "." and any(
                0 <= y + dy < height and 0 <= x + dx < width and grid[y + dy][x + dx] != "."
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))
            ):
                edged[y][x] = "o"
    return ["".join(row) for row in edged]


def sprite(rows: list[str]) -> Image.Image:
    image = Image.new("RGBA", (len(rows[0]), len(rows)))
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            if cell != ".":
                image.putpixel((x, y), (*bytes.fromhex(PAINT[cell][1:]), 255))
    return image


def main() -> None:
    background = Image.open(sys.argv[1]).convert("RGBA") if len(sys.argv) > 1 else None
    panel = 260
    sheet = Image.new("RGBA", (panel * 3, panel * 2 + 60), COLORS["background"])
    draw = ImageDraw.Draw(sheet)
    for column, (size, kinds) in enumerate(SPRITES.items()):
        for row, edge in enumerate((False, True)):
            left, top = column * panel, 30 + row * panel
            if background:
                crop_left = (background.width - panel // ZOOM) // 2
                crop_top = (background.height - panel // ZOOM) // 2
                patch = background.crop(
                    (crop_left, crop_top, crop_left + panel // ZOOM, crop_top + panel // ZOOM)
                )
            else:
                patch = Image.new("RGBA", (panel // ZOOM, panel // ZOOM), COLORS["grass"])
            for index, frames in enumerate(kinds.values()):
                for step, rows in enumerate(frames):
                    art = sprite(outlined(rows) if edge else rows)
                    flipped = art.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if step else art
                    patch.alpha_composite(flipped, (4 + step * 20, 6 + index * 18))
            sheet.paste(patch.resize((panel, panel), Image.Resampling.NEAREST), (left, top))
            label = f"{size} real size, {'dark edge' if edge else 'no edge'}"
            draw.text((left + 6, top + panel - 18), label, fill=COLORS["road_line"])
    draw.text(
        (6, 8),
        f"Sangai options, shown {ZOOM}x: stag (top), hind (below); right-facing and walking left",
        fill=COLORS["road_line"],
    )
    draw.text(
        (6, panel * 2 + 36),
        "At map zoom 1 each would be 1/6 of this size. Coat colors mixed from the palette.",
        fill=COLORS["road_line"],
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
