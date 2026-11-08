"""Draw landmark sprites from shapes. Palette slots are written as pixel values."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from manipur.detail import SLOTS_32, TRANSPARENT

WIDTH, HEIGHT = 64, 104
LIT = SLOTS_32["wall_lit"]
SHADE = SLOTS_32["wall_shade"]
DARK = SLOTS_32["background"]
STONE = SLOTS_32["road_major"]
STEP = SLOTS_32["road_minor"]
TOP = SLOTS_32["road_line"]


def diamond(draw: ImageDraw.ImageDraw, x: int, y: int, half: int, fill: int) -> None:
    draw.polygon([(x - half, y), (x, y - half // 2), (x + half, y), (x, y + half // 2)], fill=fill)


def draw_shaheed_minar() -> None:
    image = Image.new("L", (WIDTH, HEIGHT), TRANSPARENT)
    draw = ImageDraw.Draw(image)
    x, y = 32, 94

    # Stepped plinth, widest at the ground.
    for lift, half, fill in ((0, 30, STONE), (3, 25, STEP), (6, 20, STONE), (9, 15, STEP)):
        diamond(draw, x, y - lift, half, fill)
        draw.line([(x - half, y - lift), (x, y - lift + half // 2)], fill=DARK)
        draw.line([(x, y - lift + half // 2), (x + half, y - lift)], fill=DARK)
    foot = y - 11

    # Rear blade first, then the two tapering front blades.
    top = 25
    # The gaps between them stay transparent; they are what make the pillar recognizable.
    draw.polygon([(x - 2, foot - 3), (x + 2, foot - 3), (x + 1, top), (x - 1, top)], fill=SHADE)
    draw.polygon([(x - 17, foot), (x - 8, foot + 3), (x - 4, top), (x - 8, top)], fill=LIT)
    draw.polygon([(x + 8, foot + 3), (x + 17, foot), (x + 8, top), (x + 4, top)], fill=SHADE)
    for start, end in (
        ((x - 17, foot), (x - 8, top)),
        ((x - 8, foot + 3), (x - 4, top)),
        ((x + 8, foot + 3), (x + 4, top)),
        ((x + 17, foot), (x + 8, top)),
        ((x - 2, foot - 3), (x - 1, top)),
        ((x + 2, foot - 3), (x + 1, top)),
    ):
        draw.line([start, end], fill=DARK)

    # Lintel joining the blades, then the round cap.
    draw.rectangle([x - 8, top - 5, x + 8, top], fill=LIT)
    draw.rectangle([x, top - 5, x + 8, top], fill=SHADE)
    draw.rectangle([x - 8, top - 5, x + 8, top], outline=DARK)
    draw.ellipse([x - 7, top - 10, x + 7, top - 4], fill=TOP, outline=DARK)

    # The dark sculpture: three creatures back to back around a taller center.
    draw.ellipse([x - 8, top - 20, x - 1, top - 9], fill=DARK)
    draw.ellipse([x + 1, top - 20, x + 8, top - 9], fill=DARK)
    draw.polygon(
        [(x - 3, top - 9), (x + 3, top - 9), (x + 2, top - 22), (x, top - 25), (x - 2, top - 22)],
        fill=STONE,
    )
    draw.point([(x - 5, top - 17), (x + 5, top - 17), (x - 1, top - 21)], fill=STEP)
    target = Path("assets/sprites/shaheed_minar.png")
    image.save(target)
    print(target)


def outlined(image: Image.Image) -> Image.Image:
    """Return the image with a one-pixel dark edge around its opaque shape."""
    art = np.asarray(image).copy()
    solid = art != TRANSPARENT
    grown = solid.copy()
    for axis, shift in ((0, 1), (0, -1), (1, 1), (1, -1)):
        grown |= np.roll(solid, shift, axis=axis)
    art[grown & ~solid] = DARK
    return Image.fromarray(art)


def draw_kangla_sha() -> None:
    """Draw one of the pair of white dragon-lions, facing right."""
    image = Image.new("L", (36, 34), TRANSPARENT)
    draw = ImageDraw.Draw(image)
    # Legs, body, chest and neck, then the head and its two horns.
    for x in (6, 12, 22, 27):
        draw.rectangle([x, 21, x + 4, 30], fill=LIT)
    draw.ellipse([3, 12, 29, 25], fill=LIT)
    draw.polygon([(19, 13), (29, 18), (30, 6), (22, 6)], fill=LIT)
    draw.ellipse([21, 3, 32, 12], fill=LIT)
    draw.polygon([(29, 7), (34, 6), (33, 10), (29, 11)], fill=LIT)
    draw.line([(23, 4), (21, 0)], fill=TOP)
    draw.line([(27, 3), (28, 0)], fill=TOP)
    # Shade the belly and the rear legs, and mark the mouth and neck band.
    draw.polygon([(5, 22), (28, 22), (27, 25), (7, 25)], fill=SHADE)
    draw.rectangle([12, 22, 16, 30], fill=SHADE)
    draw.rectangle([27, 22, 31, 30], fill=SHADE)
    draw.line([(30, 10), (33, 9)], fill=SHADE)
    draw.line([(21, 13), (29, 14)], fill=TOP)
    outlined(image).save(Path("assets/sprites/kangla_sha.png"))


def main() -> None:
    draw_shaheed_minar()
    draw_kangla_sha()


if __name__ == "__main__":
    main()
