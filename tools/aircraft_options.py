"""Render candidate airliner styles over the real runway, for Brajeshwar to choose from.

The plane is an A320-sized model in meters, projected like the buildings, so the
viewer can draw it at any heading in any of the 24 views. Writes
out/imphal/aircraft-options.png.
"""

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw
from pyproj import Transformer

from manipur.detail import detail_colors

MANIFEST = Path("out/imphal/tiles/manifest.json")
FRAMES = Path("out/imphal/frames")
OUT = Path("out/imphal/aircraft-options.png")
FRAME_PX = 2048
LIFT = math.sqrt(3)  # screen pixels per meter of height in projection B
RUNWAY = ((93.8895255, 24.7494582), (93.9049069, 24.7697927))  # OSM way 44884414, 04/22
PANEL_W, PANEL_H, LABEL_H = 440, 400, 22
COLORS = {name: tuple(bytes.fromhex(value[1:])) for name, value in detail_colors().items()}

# Plan-view outlines in meters: (forward, right). The fuselage is 4 m tall.
FUSELAGE = [(18.8, 0), (16.5, 2), (-13, 2), (-18.6, 0.5), (-18.6, -0.5), (-13, -2), (16.5, -2)]
WINGS = [
    (3, 2),
    (-6.5, 17.9),
    (-8.6, 17.9),
    (-4.5, 2),
    (-4.5, -2),
    (-8.6, -17.9),
    (-6.5, -17.9),
    (3, -2),
]
TAILPLANE = [(-13.5, 1.5), (-17, 6.2), (-18.4, 6.2), (-17.4, 1.5)]
FIN = [(-12, 4), (-18.6, 4), (-18.9, 11.8), (-16, 11.8)]  # (forward, up) at right = 0
ENGINE = (3.2, -1.2, 5.7)  # nacelle front and back, and its distance out on each wing


class Placer:
    def __init__(self, x: float, y: float, z: float, heading: float, scale: float) -> None:
        manifest = json.loads(MANIFEST.read_text())
        self.matrix = manifest["matrix"]
        self.offset = (manifest["x_offset"], manifest["y_offset"])
        self.x, self.y, self.z = x, y, z
        self.sin, self.cos = math.sin(math.radians(heading)), math.cos(math.radians(heading))
        self.scale = scale

    def ground(self, forward: float, right: float) -> tuple[float, float]:
        f, r = forward * self.scale, right * self.scale
        return self.x + f * self.sin + r * self.cos, self.y + f * self.cos - r * self.sin

    def screen(self, forward: float, right: float, up: float, shadow: bool = False) -> tuple:
        x, y = self.ground(forward, right)
        a, b, d, e = self.matrix
        z = 0 if shadow else self.z + up * self.scale
        return (a * x + b * y + self.offset[0], d * x + e * y + self.offset[1] - z * LIFT)


def outline(draw: ImageDraw.ImageDraw, points: list, fill: tuple, edge: tuple | None) -> None:
    draw.polygon(points, fill=fill, outline=edge)


def draw_plane(image: Image.Image, origin: tuple, place: Placer, style: str) -> None:
    def to_image(point: tuple) -> tuple:
        return (point[0] - origin[0], point[1] - origin[1])

    def flat(points: list, up: float, shadow: bool = False) -> list:
        return [to_image(place.screen(f, r, up, shadow)) for f, r in points]

    # The shadow is the whole plan view on the ground, darkened over whatever is below.
    shade = Image.new("L", image.size, 0)
    shade_draw = ImageDraw.Draw(shade)
    for part in (WINGS, TAILPLANE, FUSELAGE):
        shade_draw.polygon(flat(part, 0, shadow=True), fill=110)
    image.paste(COLORS["background"], mask=shade)

    draw = ImageDraw.Draw(image)
    edge = COLORS["background"]
    if style == "flat":
        for part in (WINGS, TAILPLANE, FUSELAGE):
            outline(draw, flat(part, 2), COLORS["wall_lit"], edge)
        return

    # The fuselage side that faces the viewer, then the wings, top, fin, and engines.
    _, _, d, e = place.matrix  # (d, e) is the ground direction that points down the screen
    side = 1 if place.cos * d - place.sin * e > 0 else -1
    body = [(f, r * side) for f, r in FUSELAGE if r * side >= 0]
    body.sort(key=lambda p: -p[0])
    wall = [to_image(place.screen(f, r, 0)) for f, r in body]
    wall += [to_image(place.screen(f, r, 4)) for f, r in reversed(body)]
    for part, up in ((WINGS, 1.2), (TAILPLANE, 3.4)):
        outline(draw, flat(part, up), COLORS["wall_shade"], edge)
    front, back, out = ENGINE
    for r in (out, -out):
        nacelle = [(front, r - 1), (front, r + 1), (back, r + 1), (back, r - 1)]
        outline(draw, flat(nacelle, 0.2), COLORS["road_major"], edge)
    outline(draw, wall, COLORS["wall_shade"], edge)
    outline(draw, flat(FUSELAGE, 4), COLORS["wall_lit"], edge)
    fin = [to_image(place.screen(f, 0, up)) for f, up in FIN]
    outline(draw, fin, COLORS["roof_0"], edge)


def read_canvas(x0: int, y0: int, width: int, height: int) -> Image.Image:
    canvas = Image.new("RGB", (width, height))
    for row in range(y0 // FRAME_PX, (y0 + height) // FRAME_PX + 1):
        for column in range(x0 // FRAME_PX, (x0 + width) // FRAME_PX + 1):
            frame = Image.open(FRAMES / f"{row:03d}_{column:03d}.png").convert("RGB")
            canvas.paste(frame, (column * FRAME_PX - x0, row * FRAME_PX - y0))
    return canvas


def main() -> None:
    to_metric = Transformer.from_crs(4326, 32646, always_xy=True)
    # Landing on runway 22, from the northeast: the approach to 04 starts off the map.
    (x2, y2), (x1, y1) = (to_metric.transform(*end) for end in RUNWAY)
    heading = math.degrees(math.atan2(x2 - x1, y2 - y1))
    glide = math.tan(math.radians(3))
    styles = [
        ("flat", 1, "A  Flat: plan view only"),
        ("volume", 1, "B  Volume: body, fin, engines"),
    ]
    styles.append(("volume", 2, "C  Bold: B at twice real size"))
    moments = [
        (0, 0.12, "on the runway"),
        (40, None, "short final, 40 m up"),
        (110, None, "110 m up"),
    ]

    sheet = Image.new("RGB", (PANEL_W * 3, (PANEL_H + LABEL_H) * 3), COLORS["background"])
    label = ImageDraw.Draw(sheet)
    for row, (style, scale, title) in enumerate(styles):
        for column, (altitude, along, moment) in enumerate(moments):
            back = along * 2746 if along is not None else -altitude / glide
            x = x1 + back * math.sin(math.radians(heading))
            y = y1 + back * math.cos(math.radians(heading))
            place = Placer(x, y, altitude, heading, scale)
            center = place.screen(0, 0, -altitude / 2 / scale)
            x0, y0 = int(center[0] - PANEL_W / 2), int(center[1] - PANEL_H / 2)
            panel = read_canvas(x0, y0, PANEL_W, PANEL_H)
            draw_plane(panel, (x0, y0), place, style)
            top = row * (PANEL_H + LABEL_H)
            sheet.paste(panel, (column * PANEL_W, top + LABEL_H))
            label.text(
                (column * PANEL_W + 6, top + 5), f"{title} - {moment}", fill=COLORS["road_line"]
            )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT)
    print(OUT, f"runway heading {heading:.1f}")


if __name__ == "__main__":
    main()
