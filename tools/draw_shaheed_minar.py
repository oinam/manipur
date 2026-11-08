"""Draw the Shaheed Minar sprite from shapes. Palette slots are written as pixel values."""

from pathlib import Path

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


def main() -> None:
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


if __name__ == "__main__":
    main()
