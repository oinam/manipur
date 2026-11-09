"""Near-final styling for one crop, to judge what the procedural map can become."""

import datetime as dt
import itertools
import json
import math
import multiprocessing
import time
import zlib
from dataclasses import dataclass, replace
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyogrio
import shapely
import shapely.affinity
from affine import Affine
from PIL import Image, ImageDraw
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.affinity import affine_transform
from shapely.geometry import LineString, Point
from shapely.geometry.polygon import orient
from shapely.ops import substring

from manipur.areas import Area
from manipur.fetch import raw_dir
from manipur.osm import load_features
from manipur.palettes import PALETTE, SLOT, SLOTS
from manipur.prepare import METRIC_CRS, derived_path
from manipur.render import (
    LINED_ROADS,
    PROJECTION_B,
    ROAD_ORDER,
    ROAD_SLOTS,
    SEED,
    Layers,
    Projection,
    Viewport,
    centered_viewport,
    full_viewport,
    load_layers,
)

CROP_CENTER = (93.93759, 24.80343)
CROP_PX = 900
PROJECTION = PROJECTION_B
# The chosen projection turned in 15 degree steps, named for the turn from the default.
VIEWS = {str(turn): (45.0 + turn) % 360 for turn in range(0, 360, 15)}
DEFAULT_VIEW = "0"
SPRITE_DIR = Path("assets/sprites")
LANDMARKS_PATH = Path("assets/landmarks.json")
TRANSPARENT = 255

_EXTRA = (
    *(f"roof_shade_{index}" for index in range(6)),
    "canopy_light",
    "canopy_dark",
    "water_light",
    "water_dark",
    "shadow_built",
)
SLOTS_32 = {**SLOT, **{name: len(SLOTS) + index for index, name in enumerate(_EXTRA)}}

GROUND_CLASSES = ("tree", "shrub", "grass", "crop", "built", "bare", "wetland")
SPECKLE = {
    "tree": "canopy_dark",
    "shrub": "tree",
    "grass": "shrub",
    "crop": "grass",
    "built": "bare",
    "bare": "shadow_built",
    "wetland": "grass",
}
SHADOW = {
    "tree": "canopy_dark",
    "shrub": "tree",
    "grass": "shrub",
    "crop": "grass",
    "built": "shadow_built",
    "bare": "shadow_built",
    "wetland": "shrub",
    "water": "water_dark",
    "road_major": "background",
    "road_minor": "road_major",
    "road_track": "shadow_built",
    "road_line": "road_minor",
    "water_dark": "background",
    "water_light": "water",
    "canopy_dark": "background",
    "shadow_built": "road_minor",
}
TREE_ODDS = {
    "tree": 0.72,
    "shrub": 0.18,
    "wetland": 0.08,
    "grass": 0.04,
    "built": 0.03,
    "crop": 0.01,
}
TREE_SPACING_M = 6.5
MAJOR_ROADS = [name for name, slot in ROAD_SLOTS.items() if slot == "road_major"]
SUN_U, SUN_D = 0.94, -0.34
LOW_HOUSE_MAX_M2 = 160
LOW_HOUSE_MAX_M = 4.4
VERANDA_M = 1.5
VERANDA_INNER_M = 2.6
VERANDA_OUTER_M = 2.1
WATER_TANK_MIN_M2 = 25
SHADOW_PER_HEIGHT = 0.75
STOREY_M = 3.2
BLUR_RADIUS_PX = 16
FOOTPATH_M = 1.8
MINAR_CLEARING_M = 16.0
PIXELS_PER_METER_DETAIL = 2.0
CEMETERY_ROW_M = 5.5
CEMETERY_GRAVE_M = 4.0
FRAME_PX = 2048
# Wider than the tallest building's lift, the ground blur, and any sprite, so frames join exactly.
APRON_PX = 256
WORKERS = 5
PADDY_ANGLE = math.radians(17)
PADDY_LENGTH_M = 44.0
PADDY_WIDTH_M = 28.0
PADDY_BUND_M = 1.1


def _mix(first: str, second: str, amount: float) -> str:
    a = bytes.fromhex(first.lstrip("#"))
    b = bytes.fromhex(second.lstrip("#"))
    return "#" + bytes(round(x + (y - x) * amount) for x, y in zip(a, b, strict=True)).hex()


def detail_colors() -> dict[str, str]:
    """Extend the monsoon palette with shades derived from its own colors."""
    colors = dict(PALETTE)
    for index in range(6):
        colors[f"roof_shade_{index}"] = _mix(PALETTE[f"roof_{index}"], PALETTE["background"], 0.32)
    colors["canopy_light"] = _mix(PALETTE["grass"], PALETTE["crop"], 0.35)
    colors["canopy_dark"] = _mix(PALETTE["tree"], PALETTE["background"], 0.5)
    colors["water_light"] = _mix(PALETTE["water"], "#ffffff", 0.42)
    colors["water_dark"] = _mix(PALETTE["water"], PALETTE["background"], 0.42)
    colors["shadow_built"] = _mix(PALETTE["bare"], PALETTE["background"], 0.38)
    return colors


def detail_lookup() -> bytes:
    colors = detail_colors()
    values = bytearray(768)
    for name, index in SLOTS_32.items():
        values[index * 3 : index * 3 + 3] = bytes.fromhex(colors[name].lstrip("#"))
    return bytes(values)


def hash_field(xs: np.ndarray, ys: np.ndarray, salt: int) -> np.ndarray:
    """Return deterministic noise in [0, 1) anchored to global pixel coordinates."""
    value = (xs.astype("int64").astype("uint64") * np.uint64(2654435761)) + (
        ys.astype("int64").astype("uint64") * np.uint64(2246822519)
    )
    value += np.uint64(salt * 3266489917 + 374761393)
    value ^= value >> np.uint64(15)
    value *= np.uint64(3266489917)
    value ^= value >> np.uint64(13)
    return (value & np.uint64(65535)).astype("float32") / 65536.0


def _global_grid(view: Viewport) -> tuple[np.ndarray, np.ndarray]:
    ys, xs = np.mgrid[0 : view.height, 0 : view.width]
    return xs - int(view.x_offset), ys - int(view.y_offset)


def _matrix(view: Viewport) -> tuple[float, ...]:
    a, b, d, e = PROJECTION.matrix
    return (a, b, d, e, view.x_offset, view.y_offset)


def _burn(shapes: list, view: Viewport, fill: int = 0) -> np.ndarray:
    matrix = _matrix(view)
    placed = [
        (affine_transform(geometry, matrix), value)
        for geometry, value in shapes
        if geometry is not None and not geometry.is_empty
    ]
    if not placed:
        return np.full((view.height, view.width), fill, dtype="uint8")
    return rasterize(
        placed,
        out_shape=(view.height, view.width),
        transform=Affine.identity(),
        fill=fill,
        dtype="uint8",
    )


def _box_blur(array: np.ndarray, radius: int) -> np.ndarray:
    """Return a box blur of the array, computed from a summed-area table."""
    table = np.zeros((array.shape[0] + 1, array.shape[1] + 1), dtype="float64")
    table[1:, 1:] = array.cumsum(0).cumsum(1)
    height, width = array.shape
    rows = np.arange(height)
    cols = np.arange(width)
    top = np.clip(rows - radius, 0, height)
    bottom = np.clip(rows + radius + 1, 0, height)
    left = np.clip(cols - radius, 0, width)
    right = np.clip(cols + radius + 1, 0, width)
    total = (
        table[bottom[:, None], right[None, :]]
        - table[top[:, None], right[None, :]]
        - table[bottom[:, None], left[None, :]]
        + table[top[:, None], left[None, :]]
    )
    area = (bottom - top)[:, None] * (right - left)[None, :]
    return (total / area).astype("float32")


def _paint_ground(layers: Layers, view: Viewport) -> np.ndarray:
    """Soften WorldCover's 10 m cells into ragged, speckled ground."""
    shapes = []
    for row in layers.ground.itertuples():
        name = "wetland" if row.ground == "water" else row.ground
        if name in GROUND_CLASSES:
            shapes.append((row.geometry, GROUND_CLASSES.index(name) + 1))
    labels = _burn(shapes, view)
    xs, ys = _global_grid(view)
    noise = hash_field(xs // 3, ys // 3, 11)
    scores = np.stack(
        [
            _box_blur((labels == index + 1).astype("float32"), BLUR_RADIUS_PX)
            for index in range(len(GROUND_CLASSES))
        ]
    )
    chosen = (scores + (noise - 0.5)[None, :, :] * 0.16).argmax(axis=0)
    inside = _burn([(layers.patch, 1)], view).astype(bool)

    canvas = np.full((view.height, view.width), SLOTS_32["background"], dtype="uint8")
    base = np.array([SLOTS_32[name] for name in GROUND_CLASSES], dtype="uint8")
    canvas[inside] = base[chosen[inside]]
    speckle = np.array([SLOTS_32[SPECKLE[name]] for name in GROUND_CLASSES], dtype="uint8")
    chance = 0.05 + hash_field(xs // 9, ys // 9, 12) * 0.17
    marked = inside & (hash_field(xs, ys, 13) < chance)
    canvas[marked] = speckle[chosen[marked]]
    crop = inside & (chosen == GROUND_CLASSES.index("crop"))
    if crop.any():
        _paint_paddy(canvas, crop, xs, ys)
    return canvas


def _paint_paddy(canvas: np.ndarray, crop: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> None:
    """Draw fields on a world-anchored lattice; OSM maps no paddy boundaries here."""
    a, b, d, e = PROJECTION.matrix
    det = a * e - b * d
    x = (e * xs - b * ys) / det
    y = (-d * xs + a * ys) / det
    along = x * math.cos(PADDY_ANGLE) + y * math.sin(PADDY_ANGLE)
    across = -x * math.sin(PADDY_ANGLE) + y * math.cos(PADDY_ANGLE)
    row = np.floor(across / PADDY_WIDTH_M)
    shifted = along + hash_field(row, np.zeros_like(row), 40) * PADDY_LENGTH_M
    column = np.floor(shifted / PADDY_LENGTH_M)
    tone = hash_field(column, row, 41)
    fields = np.select(
        [tone < 0.42, tone < 0.78, tone < 0.93],
        [SLOTS_32["crop"], SLOTS_32["canopy_light"], SLOTS_32["grass"]],
        default=SLOTS_32["shrub"],
    ).astype("uint8")
    furrows = np.select(
        [tone < 0.42, tone < 0.78, tone < 0.93],
        [SLOTS_32["canopy_light"], SLOTS_32["grass"], SLOTS_32["shrub"]],
        default=SLOTS_32["tree"],
    ).astype("uint8")
    canvas[crop] = fields[crop]
    rows = crop & (np.floor(across * 1.2) % 3 == 0) & (hash_field(xs, ys, 42) < 0.7)
    canvas[rows] = furrows[rows]
    bund = crop & (
        (shifted - column * PADDY_LENGTH_M < PADDY_BUND_M)
        | (across - row * PADDY_WIDTH_M < PADDY_BUND_M)
    )
    canvas[bund] = SLOTS_32["bare"]


def _paint_cemetery(canvas: np.ndarray, part: gpd.GeoDataFrame, view: Viewport) -> None:
    """Draw mown grass, a clipped hedge, and rows of grave markers."""
    mask = _burn([(geometry, 1) for geometry in part.geometry], view).astype(bool)
    canvas[mask] = SLOTS_32["grass"]
    interior = mask.copy()
    for axis, shift in ((0, 3), (0, -3), (1, 3), (1, -3)):
        interior &= np.roll(mask, shift, axis=axis)
    canvas[mask & ~interior] = SLOTS_32["tree"]
    a, b, d, e = PROJECTION.matrix
    for geometry in part.geometry:
        polygons = geometry.geoms if geometry.geom_type == "MultiPolygon" else [geometry]
        for polygon in polygons:
            center, u, v, length, width = _ground_axes(polygon)
            usable = polygon.buffer(-3.0)
            shapely.prepare(usable)
            along = np.arange(-length / 2, length / 2, CEMETERY_GRAVE_M)
            across = np.arange(-width / 2, width / 2, CEMETERY_ROW_M)
            grid_u, grid_v = np.meshgrid(along, across)
            xs = center[0] + u[0] * grid_u.ravel() + v[0] * grid_v.ravel()
            ys = center[1] + u[1] * grid_u.ravel() + v[1] * grid_v.ravel()
            inside = shapely.contains_xy(usable, xs, ys)
            for x, y in zip(xs[inside], ys[inside], strict=True):
                col = round(a * x + b * y + view.x_offset)
                row = round(d * x + e * y + view.y_offset)
                if 2 <= col < view.width - 2 and 2 <= row < view.height - 2:
                    canvas[row - 1, col - 1 : col + 2] = SLOTS_32["wall_lit"]
                    canvas[row, col - 1 : col + 2] = SLOTS_32["wall_shade"]


def _paint_surfaces(canvas: np.ndarray, surfaces: gpd.GeoDataFrame, view: Viewport) -> None:
    cemeteries = surfaces[surfaces.kind == "cemetery"]
    if not cemeteries.empty:
        _paint_cemetery(canvas, cemeteries, view)
    for kind, slot in (("pitch", "grass"), ("paved", "road_minor")):
        part = surfaces[surfaces.kind == kind]
        mask = _burn([(geometry, 1) for geometry in part.geometry], view).astype(bool)
        canvas[mask] = SLOTS_32[slot]


def _water_geometry(layers: Layers) -> list:
    rivers = layers.waterways.geometry.buffer(layers.waterways.width_m / 2)
    return [*layers.water.geometry.values, *rivers.intersection(layers.patch).values]


def _paint_water(canvas: np.ndarray, layers: Layers, view: Viewport) -> None:
    water = _water_geometry(layers)
    banks = [(shapely.intersection(g.buffer(2.5), layers.patch), 1) for g in water]
    canvas[_burn(banks, view).astype(bool)] = SLOTS_32["bare"]
    wet = _burn([(g, 1) for g in water], view).astype(bool)
    canvas[wet] = SLOTS_32["water"]

    xs, ys = _global_grid(view)
    ripple = (ys % 6 == 0) & (xs % 11 < 6) & (hash_field(xs // 11, ys, 21) < 0.3)
    canvas[wet & ripple] = SLOTS_32["water_light"]
    above = np.roll(wet, 2, axis=0)
    above[:2, :] = False
    canvas[wet & ~above] = SLOTS_32["water_dark"]


def _dashes(line: LineString, on_m: float = 4.0, off_m: float = 6.0) -> list:
    parts = []
    position = 0.0
    while position < line.length:
        parts.append(substring(line, position, min(position + on_m, line.length)).buffer(0.45))
        position += on_m + off_m
    return parts


def _paint_roads(canvas: np.ndarray, layers: Layers, view: Viewport) -> None:
    roads = layers.roads.explode(index_parts=False)
    roads = roads[roads.geometry.geom_type == "LineString"]
    major = roads[roads.road_class.isin(MAJOR_ROADS)]
    walks = major.geometry.buffer(major.width_m / 2 + FOOTPATH_M, cap_style="flat")
    walk_mask = _burn([(g.intersection(layers.patch), 1) for g in walks], view).astype(bool)
    canvas[walk_mask] = SLOTS_32["road_track"]

    shapes = []
    for road_class in ROAD_ORDER:
        part = roads[roads.road_class == road_class]
        slot = SLOTS_32[ROAD_SLOTS.get(road_class, "road_minor")]
        bodies = part.geometry.buffer(part.width_m / 2, cap_style="flat")
        shapes.extend((g.intersection(layers.patch), slot) for g in bodies)
    burned = _burn(shapes, view)
    painted = burned > 0
    canvas[painted] = burned[painted]

    majors = burned == SLOTS_32["road_major"]
    interior = majors.copy()
    for axis, shift in ((0, 1), (0, -1), (1, 1), (1, -1)):
        interior &= np.roll(majors, shift, axis=axis)
    canvas[majors & ~interior] = SLOTS_32["road_minor"]

    lined = roads[roads.road_class.isin(LINED_ROADS)]
    marks = [(g.intersection(layers.patch), 1) for line in lined.geometry for g in _dashes(line)]
    canvas[_burn(marks, view).astype(bool)] = SLOTS_32["road_line"]


def _sun_offset(length: float) -> tuple[float, float]:
    """Return the world offset of a shadow of the given ground length."""
    angle = math.radians(PROJECTION.rotation_deg)
    cos, sin = math.cos(angle), math.sin(angle)
    return (
        (SUN_U * cos - SUN_D * sin) * length,
        (SUN_U * sin + SUN_D * cos) * length,
    )


def _depth(x: float, y: float) -> float:
    return PROJECTION.depth(x, y)


def _project(view: Viewport, x: float, y: float, z: float) -> tuple[int, int]:
    a, b, d, e = PROJECTION.matrix
    return (
        round(a * x + b * y + view.x_offset),
        round(d * x + e * y + view.y_offset - z * PROJECTION.lift),
    )


def _hash(seed: int, text: str, modulo: int) -> int:
    return zlib.crc32(f"{seed}:{text}".encode()) % modulo


def _normal(p: np.ndarray, q: np.ndarray) -> tuple[float, float]:
    """Return the outward normal of a counterclockwise edge in the view frame (u, depth)."""
    dx, dy = q - p
    angle = math.radians(PROJECTION.rotation_deg)
    cos, sin = math.cos(angle), math.sin(angle)
    return (cos * dy - sin * dx, -sin * dy - cos * dx)


def _windows(draw, view, p, q, top, lit, shutters: bool) -> None:
    length = float(np.linalg.norm(q - p))
    count = int(length / 3.0)
    if count < 1:
        return
    color = SLOTS_32["road_major"] if lit else SLOTS_32["background"]
    start = 0
    if shutters:
        shutter = SLOTS_32["road_minor"] if lit else SLOTS_32["road_major"]
        for index in range(count):
            t0 = (index + 0.15) / count
            t1 = (index + 0.85) / count
            a = p + (q - p) * t0
            b = p + (q - p) * t1
            draw.polygon(
                [
                    _project(view, *a, 0.2),
                    _project(view, *b, 0.2),
                    _project(view, *b, 2.5),
                    _project(view, *a, 2.5),
                ],
                fill=shutter,
            )
        start = 1
    storey = start
    while 1.7 + STOREY_M * storey + 1.0 < top:
        z = 1.7 + STOREY_M * storey
        for index in range(count):
            point = p + (q - p) * ((index + 0.5) / count)
            x, y = _project(view, *point, z)
            draw.rectangle([x - 1, y - 2, x, y], fill=color)
        storey += 1


def _paint_walls(
    draw,
    view,
    ring,
    top,
    gable_top,
    shutters,
    windows,
    lit_slot=None,
    shade_slot=None,
    decorate=None,
) -> None:
    """Draw camera-facing walls; ring is counterclockwise and closed."""
    edges = []
    for index in range(len(ring) - 1):
        p, q = ring[index], ring[index + 1]
        normal_u, normal_depth = _normal(p, q)
        length = float(np.linalg.norm(q - p))
        if normal_depth < 0 and length > 0:
            edges.append((-_depth(*((p + q) / 2)), index, p, q, normal_u < 0))
    outline = SLOTS_32["background"]
    edges.sort(key=lambda edge: edge[0])
    visible = {edge[1] for edge in edges}
    for _, index, p, q, lit in edges:
        wall_lit = SLOTS_32["wall_lit"] if lit_slot is None else lit_slot
        wall_shade = SLOTS_32["wall_shade"] if shade_slot is None else shade_slot
        fill = wall_lit if lit else wall_shade
        quad = [
            _project(view, *p, 0),
            _project(view, *q, 0),
            _project(view, *q, top),
            _project(view, *p, top),
        ]
        draw.polygon(quad, fill=fill)
        apex = gable_top.get(index) if gable_top else None
        if apex is not None:
            middle = (p + q) / 2
            draw.polygon(
                [
                    _project(view, *p, top),
                    _project(view, *q, top),
                    _project(view, *middle, apex),
                ],
                fill=fill,
            )
        if windows:
            _windows(draw, view, p, q, top, lit, shutters)
        if decorate:
            decorate(p, q, lit)
        draw.line([_project(view, *p, 0), _project(view, *q, 0)], fill=outline)
    count = len(ring) - 1
    for index in range(count):
        if (index in visible) != ((index - 1) % count in visible):
            draw.line(
                [_project(view, *ring[index], 0), _project(view, *ring[index], top)], fill=outline
            )


def _classify(area: float, height: float, rectangular: bool, building_id: str, seed: int) -> str:
    if area >= 600 and height < 9.5:
        return "shed" if rectangular else "flat"
    if height >= 11:
        return "block"
    if 100 <= area < 600 and rectangular and _hash(seed, building_id + "s", 100) < 45:
        return "shop"
    if rectangular and _hash(seed, building_id + "p", 100) < 72:
        return "house"
    return "flat"


def _long_side_corners(polygon) -> np.ndarray:
    """Return the footprint's rectangle corners, starting along a long side."""
    corners = np.array(shapely.minimum_rotated_rectangle(polygon).exterior.coords)[:4]
    if np.linalg.norm(corners[1] - corners[0]) < np.linalg.norm(corners[2] - corners[1]):
        corners = np.roll(corners, -1, axis=0)
    return corners


def _paint_pitched(draw, view, polygon, height, slot, shade, windows, ribbed) -> None:
    a, b, c, d = _long_side_corners(polygon)
    width = float(np.linalg.norm(c - b))
    rise = float(np.clip(width * 0.2, 0.8, 3.0))
    eave = max(2.4, height - rise)
    ridge = eave + rise
    left, right = (a + d) / 2, (b + c) / 2

    ring = [a, b, c, d, a]
    area2 = sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(4))
    if area2 < 0:
        ring = ring[::-1]
    closed = np.array(ring)
    # Short edges carry the gables; in the reversed ring they stay at odd positions.
    gables = dict.fromkeys((1, 3), ridge)
    _paint_walls(draw, view, closed, eave, gables, False, windows)

    outline = SLOTS_32["background"]
    faces = [(a, b, right, left), (d, c, right, left)]
    faces.sort(key=lambda face: -_depth(*((face[0] + face[1]) / 2)))
    for near0, near1, top1, top0 in faces:
        outward = (near0 + near1) / 2 - (left + right) / 2
        angle = math.radians(PROJECTION.rotation_deg)
        facing_left = math.cos(angle) * outward[0] + math.sin(angle) * outward[1] < 0
        fill = slot if facing_left else shade
        draw.polygon(
            [
                _project(view, *near0, eave),
                _project(view, *near1, eave),
                _project(view, *top1, ridge),
                _project(view, *top0, ridge),
            ],
            fill=fill,
            outline=outline,
        )
        if ribbed and facing_left:
            span = float(np.linalg.norm(near1 - near0))
            for step in range(1, int(span / 1.6)):
                t = step / int(span / 1.6)
                draw.line(
                    [
                        _project(view, *(near0 + (near1 - near0) * t), eave),
                        _project(view, *(top0 + (top1 - top0) * t), ridge),
                    ],
                    fill=shade,
                )


def _paint_low_house(draw, view, polygon, height, slot, shade) -> None:
    """Draw a low tin house with a veranda along its near long side."""
    _paint_pitched(draw, view, polygon, min(height, LOW_HOUSE_MAX_M), slot, shade, True, True)
    a, b, c, d = _long_side_corners(polygon)
    if _depth(*((a + b) / 2)) > _depth(*((c + d) / 2)):
        a, b, c, d = c, d, a, b
    out = (a - d) / np.linalg.norm(a - d) * VERANDA_M
    draw.polygon(
        [
            _project(view, *a, VERANDA_INNER_M),
            _project(view, *b, VERANDA_INNER_M),
            _project(view, *(b + out), VERANDA_OUTER_M),
            _project(view, *(a + out), VERANDA_OUTER_M),
        ],
        fill=shade,
        outline=SLOTS_32["background"],
    )
    for t in np.linspace(0.08, 0.92, 4):
        post = a + (b - a) * t + out
        draw.line(
            [_project(view, *post, 0), _project(view, *post, VERANDA_OUTER_M)],
            fill=SLOTS_32["wall_shade"],
        )


def _paint_flat(draw, view, polygon, height, slot, shade, kind, building_id, seed) -> None:
    ring = np.array(orient(polygon, 1.0).exterior.coords)
    _paint_walls(draw, view, ring, height, None, kind == "shop", kind in ("flat", "shop", "block"))
    outline = SLOTS_32["background"]
    points = [_project(view, x, y, height) for x, y in ring]
    draw.polygon(points, fill=SLOTS_32["wall_lit"], outline=outline)
    inner = polygon.buffer(-0.7, join_style="mitre")
    if not inner.is_empty and inner.geom_type == "Polygon":
        draw.polygon(
            [_project(view, x, y, height) for x, y in inner.exterior.coords],
            fill=slot,
            outline=shade,
        )
    for hole in polygon.interiors:
        draw.polygon(
            [_project(view, x, y, height) for x, y in hole.coords],
            fill=SLOTS_32["wall_shade"],
            outline=outline,
        )
    if polygon.area >= WATER_TANK_MIN_M2 and _hash(seed, building_id + "t", 3) < 2:
        center = polygon.representative_point()
        x, y = _project(view, center.x, center.y, height)
        draw.rectangle([x - 2, y - 6, x + 2, y - 1], fill=SLOTS_32["background"])
        draw.line([(x - 2, y - 6), (x + 2, y - 6)], fill=SLOTS_32["roof_shade_1"])


def _ground_axes(polygon):
    """Return (center, long unit vector, short unit vector, length, width) of the footprint."""
    corners = np.array(shapely.minimum_rotated_rectangle(polygon).exterior.coords)[:4]
    side_a, side_b = corners[1] - corners[0], corners[2] - corners[1]
    length_a, length_b = float(np.linalg.norm(side_a)), float(np.linalg.norm(side_b))
    if length_a < length_b:
        side_a, side_b, length_a, length_b = side_b, side_a, length_b, length_a
    return corners.mean(axis=0), side_a / length_a, side_b / length_b, length_a, length_b


def _facing_left(outward) -> bool:
    angle = math.radians(PROJECTION.rotation_deg)
    return math.cos(angle) * outward[0] + math.sin(angle) * outward[1] < 0


def _rect_ring(center, u, v, half_u, half_v) -> np.ndarray:
    """Return a closed counterclockwise ring for a rectangle on the ground."""
    ring = [
        center - u * half_u - v * half_v,
        center + u * half_u - v * half_v,
        center + u * half_u + v * half_v,
        center - u * half_u + v * half_v,
    ]
    area2 = sum(
        ring[i][0] * ring[(i + 1) % 4][1] - ring[(i + 1) % 4][0] * ring[i][1] for i in range(4)
    )
    if area2 < 0:
        ring.reverse()
    return np.array([*ring, ring[0]])


def _gable_roof(draw, view, center, u, v, half_u, half_v, base, rise, lit, shade, end) -> None:
    """Draw a roof whose ridge runs along u, with filled gable ends."""
    outline = SLOTS_32["background"]
    ridge = base + rise
    a, b = center - u * half_u, center + u * half_u
    for sign, tip in ((-1, a), (1, b)):
        outward = u * sign
        if _depth(*(tip + outward)) < _depth(*tip):
            draw.polygon(
                [
                    _project(view, *(tip - v * half_v), base),
                    _project(view, *(tip + v * half_v), base),
                    _project(view, *tip, ridge),
                ],
                fill=end,
                outline=outline,
            )
    slopes = sorted((-1, 1), key=lambda sign: -_depth(*(center + v * sign * half_v)))
    for sign in slopes:
        edge = v * sign * half_v
        draw.polygon(
            [
                _project(view, *(a + edge), base),
                _project(view, *(b + edge), base),
                _project(view, *b, ridge),
                _project(view, *a, ridge),
            ],
            fill=lit if _facing_left(v * sign) else shade,
            outline=outline,
        )


def _pyramid_roof(draw, view, center, u, v, half_u, half_v, base, rise, lit, shade) -> None:
    outline = shade
    ring = _rect_ring(center, u, v, half_u, half_v)
    faces = sorted(range(4), key=lambda i: -_depth(*((ring[i] + ring[i + 1]) / 2)))
    for index in faces:
        p, q = ring[index], ring[index + 1]
        draw.polygon(
            [
                _project(view, *p, base),
                _project(view, *q, base),
                _project(view, *center, base + rise),
            ],
            fill=lit if _normal(p, q)[0] < 0 else shade,
            outline=outline,
        )


def _wall_arch(draw, view, p, q, t0, t1, top, fill) -> None:
    """Draw a round-headed opening on a wall between fractions t0 and t1 of its length."""
    spring = top * 0.6
    points = [(t0, 0.2), (t1, 0.2), (t1, spring)]
    for step in range(1, 8):
        theta = math.pi * step / 8
        middle = (t0 + t1) / 2
        points.append(
            (middle + (t1 - t0) / 2 * math.cos(theta), spring + (top - spring) * math.sin(theta))
        )
    points.append((t0, spring))
    draw.polygon([_project(view, *(p + (q - p) * t), z) for t, z in points], fill=fill)


def _dome(draw, view, center, base, radius_m, lit, shade) -> None:
    x, y = _project(view, *center, base)
    radius = round(radius_m * PIXELS_PER_METER_DETAIL)
    rows = round(radius * 1.15)
    for row in range(rows + 1):
        half = round(radius * math.sqrt(max(0.0, 1 - (row / rows) ** 2)))
        if half:
            split = x + round(half * 0.35)
            draw.line([(x - half, y - row), (split, y - row)], fill=lit)
            draw.line([(split + 1, y - row), (x + half, y - row)], fill=shade)
            draw.point([(x - half, y - row), (x + half, y - row)], fill=SLOTS_32["background"])
    draw.line([(x - radius, y), (x + radius, y)], fill=SLOTS_32["background"])
    draw.line([(x, y - rows - 8), (x, y - rows)], fill=SLOTS_32["roof_1"])
    draw.rectangle([x - 1, y - rows - 4, x + 1, y - rows - 2], fill=SLOTS_32["roof_1"])


def _roof_cap(draw, view, polygon, height, edge, fill, inset=1.0) -> None:
    outline = SLOTS_32["background"]
    ring = polygon.exterior.coords
    draw.polygon([_project(view, x, y, height) for x, y in ring], fill=edge, outline=outline)
    inner = polygon.buffer(-inset, join_style="mitre")
    if not inner.is_empty and inner.geom_type == "Polygon":
        draw.polygon([_project(view, x, y, height) for x, y in inner.exterior.coords], fill=fill)


def _module_centers(polygon, center, u, v, length, width, step_u, step_v, inset) -> list:
    """Return roof module centers on a footprint-aligned grid, inside the footprint."""
    usable = polygon.buffer(-inset)
    points = []
    for i in range(-int(length / step_u), int(length / step_u) + 1):
        for j in range(-int(width / step_v), int(width / step_v) + 1):
            point = center + u * i * step_u + v * j * step_v
            if usable.contains(Point(point)):
                points.append(point)
    return sorted(points, key=lambda point: -_depth(*point))


def _paint_temple(draw, view, polygon, height) -> None:
    center, u, _, length, _ = _ground_axes(polygon)
    ring = np.array(orient(polygon, 1.0).exterior.coords)

    def arches(p, q, _lit):
        count = max(1, int(float(np.linalg.norm(q - p)) / 9.0))
        for index in range(count):
            t0, t1 = (index + 0.18) / count, (index + 0.82) / count
            _wall_arch(draw, view, p, q, t0, t1, height * 0.78, SLOTS_32["road_major"])
            for t in (t0, t1):
                point = p + (q - p) * t
                draw.line(
                    [_project(view, *point, 0.3), _project(view, *point, height * 0.5)],
                    fill=SLOTS_32["road_line"],
                )

    _paint_walls(draw, view, ring, height, None, False, False, decorate=arches)
    _roof_cap(draw, view, polygon, height, SLOTS_32["wall_lit"], SLOTS_32["road_line"], 1.2)
    offset = min(9.0, length * 0.18)
    domes = sorted((center - u * offset, center + u * offset), key=lambda point: -_depth(*point))
    for point in domes:
        x, y = _project(view, *point, height)
        draw.rectangle(
            [x - 13, y - 7, x + 13, y], fill=SLOTS_32["wall_lit"], outline=SLOTS_32["background"]
        )
        _dome(draw, view, point, height + 4.0, 6.5, SLOTS_32["road_line"], SLOTS_32["road_track"])


def _paint_market(draw, view, polygon, height) -> None:
    center, u, v, length, width = _ground_axes(polygon)
    ring = np.array(orient(polygon, 1.0).exterior.coords)

    def columns(p, q, lit):
        wall = float(np.linalg.norm(q - p))
        count = max(1, int(wall / 6.0))
        rail = SLOTS_32["roof_0"]
        draw.line([_project(view, *p, height * 0.48), _project(view, *q, height * 0.48)], fill=rail)
        stripe = SLOTS_32["wall_lit"] if lit else SLOTS_32["road_line"]
        for index in range(count + 1):
            t = index / count
            half = 0.45 / max(wall, 1.0)
            a, b = p + (q - p) * max(0.0, t - half), p + (q - p) * min(1.0, t + half)
            draw.polygon(
                [
                    _project(view, *a, 0.2),
                    _project(view, *b, 0.2),
                    _project(view, *b, height - 0.8),
                    _project(view, *a, height - 0.8),
                ],
                fill=stripe,
            )

    _paint_walls(
        draw,
        view,
        ring,
        height,
        None,
        False,
        False,
        SLOTS_32["roof_1"],
        SLOTS_32["roof_shade_1"],
        columns,
    )
    _roof_cap(draw, view, polygon, height, SLOTS_32["road_line"], SLOTS_32["roof_1"], 1.3)
    for point in _module_centers(polygon, center, u, v, length, width, 17.0, 15.0, 7.0):
        _gable_roof(
            draw,
            view,
            point,
            v,
            u,
            7.5,
            5.0,
            height,
            4.5,
            SLOTS_32["roof_0"],
            SLOTS_32["roof_shade_0"],
            SLOTS_32["road_line"],
        )


def _paint_stand(draw, view, polygon, height) -> None:
    center, u, v, length, width = _ground_axes(polygon)
    ring = np.array(orient(polygon, 1.0).exterior.coords)
    _paint_walls(draw, view, ring, height, None, False, False)
    _roof_cap(draw, view, polygon, height, SLOTS_32["wall_lit"], SLOTS_32["roof_0"], 0.7)
    for row in np.arange(-width / 2 + 1.8, width / 2 - 1.0, 1.6):
        a = center + v * row - u * (length / 2 - 1.0)
        b = center + v * row + u * (length / 2 - 1.0)
        draw.line(
            [_project(view, *a, height), _project(view, *b, height)], fill=SLOTS_32["roof_shade_0"]
        )


def _paint_pavilion(draw, view, polygon, height) -> None:
    center, u, v, length, width = _ground_axes(polygon)
    _paint_stand(draw, view, polygon, 3.0)
    posts = [
        center + u * along + v * side
        for along in np.linspace(-length / 2 + 1.5, length / 2 - 1.5, 7)
        for side in (-width / 2 + 1.5, width / 2 - 1.5)
    ]
    for post in sorted(posts, key=lambda point: -_depth(*point)):
        draw.line(
            [_project(view, *post, 3.0), _project(view, *post, height)], fill=SLOTS_32["wall_lit"]
        )
    _gable_roof(
        draw,
        view,
        center,
        u,
        v,
        length / 2 + 1.0,
        width / 2 + 1.0,
        height,
        1.6,
        SLOTS_32["roof_2"],
        SLOTS_32["roof_shade_2"],
        SLOTS_32["road_line"],
    )


def _paint_terminal(draw, view, polygon, height) -> None:
    center, u, v, length, width = _ground_axes(polygon)
    ring = np.array(orient(polygon, 1.0).exterior.coords)

    def glazing(p, q, lit):
        draw.line(
            [_project(view, *p, height * 0.62), _project(view, *q, height * 0.62)],
            fill=SLOTS_32["road_line"],
        )
        count = max(1, int(float(np.linalg.norm(q - p)) / 5.0))
        for index in range(count):
            t0, t1 = (index + 0.15) / count, (index + 0.85) / count
            a, b = p + (q - p) * t0, p + (q - p) * t1
            draw.polygon(
                [
                    _project(view, *a, 0.8),
                    _project(view, *b, 0.8),
                    _project(view, *b, height * 0.55),
                    _project(view, *a, height * 0.55),
                ],
                fill=SLOTS_32["road_major"] if lit else SLOTS_32["background"],
            )

    _paint_walls(
        draw,
        view,
        ring,
        height,
        None,
        False,
        False,
        SLOTS_32["water"],
        SLOTS_32["water_dark"],
        glazing,
    )
    _roof_cap(draw, view, polygon, height, SLOTS_32["wall_lit"], SLOTS_32["wetland"], 0.8)
    for point in _module_centers(polygon, center, u, v, length, width, 27.0, 24.0, 8.0):
        _pyramid_roof(
            draw, view, point, u, v, 12.5, 11.0, height, 6.5, SLOTS_32["wetland"], SLOTS_32["shrub"]
        )


def _paint_gate(draw, view, polygon, height) -> None:
    center, u, v, length, width = _ground_axes(polygon)
    half_block = max(5.0, length * 0.3)
    wing = max(3.0, (length / 2 - half_block) / 2)
    half_v = width / 2
    parts = [
        ("wing", center - u * (half_block + wing)),
        ("wing", center + u * (half_block + wing)),
        ("block", center),
    ]

    def wing_wall(p, q, _lit):
        count = max(1, int(float(np.linalg.norm(q - p)) / 3.2))
        for index in range(count + 1):
            point = p + (q - p) * (index / count)
            draw.line(
                [_project(view, *point, 0.2), _project(view, *point, height * 0.52)],
                fill=SLOTS_32["roof_0"],
            )
        draw.line(
            [_project(view, *p, height * 0.3), _project(view, *q, height * 0.3)],
            fill=SLOTS_32["wall_lit"],
        )

    def block_wall(p, q, _lit):
        if abs(float(np.dot((q - p) / np.linalg.norm(q - p), u))) > 0.7:
            _wall_arch(draw, view, p, q, 0.08, 0.92, height * 0.86, SLOTS_32["wall_lit"])
            _wall_arch(draw, view, p, q, 0.16, 0.84, height * 0.78, SLOTS_32["background"])

    for kind, point in sorted(parts, key=lambda part: -_depth(*part[1])):
        if kind == "wing":
            top = height * 0.52
            ring = _rect_ring(point, u, v, wing, half_v * 0.92)
            _paint_walls(
                draw,
                view,
                ring,
                top,
                None,
                False,
                False,
                SLOTS_32["road_major"],
                SLOTS_32["background"],
                wing_wall,
            )
            _pyramid_roof(
                draw,
                view,
                point,
                u,
                v,
                wing * 1.08,
                half_v,
                top,
                height * 0.26,
                SLOTS_32["roof_3"],
                SLOTS_32["roof_shade_3"],
            )
        else:
            ring = _rect_ring(point, u, v, half_block, half_v)
            _paint_walls(
                draw,
                view,
                ring,
                height,
                None,
                False,
                False,
                SLOTS_32["roof_5"],
                SLOTS_32["roof_shade_5"],
                block_wall,
            )
            # The gable faces the road, so the ridge runs across the footprint.
            _gable_roof(
                draw,
                view,
                point,
                v,
                u,
                half_v + 0.8,
                half_block + 0.8,
                height,
                height * 0.34,
                SLOTS_32["roof_0"],
                SLOTS_32["roof_shade_0"],
                SLOTS_32["roof_5"],
            )
            x, y = _project(view, *point, height * 1.34)
            draw.line([(x, y - 7), (x, y)], fill=SLOTS_32["roof_1"])


def _box(draw, view, center, u, v, half_u, half_v, base, top, lit, shade, cap) -> None:
    """Draw a raised block: its camera-facing sides, then its top."""
    outline = SLOTS_32["background"]
    ring = _rect_ring(center, u, v, half_u, half_v)
    for p, q in itertools.pairwise(ring):
        normal_u, normal_depth = _normal(p, q)
        if normal_depth < 0:
            draw.polygon(
                [
                    _project(view, *p, base),
                    _project(view, *q, base),
                    _project(view, *q, top),
                    _project(view, *p, top),
                ],
                fill=lit if normal_u < 0 else shade,
                outline=outline,
            )
    draw.polygon([_project(view, *point, top) for point in ring[:-1]], fill=cap, outline=outline)


def _ribbed_spire(draw, view, center, base, radius_m, tall_m, rib) -> None:
    """Draw a bullet-shaped spire banded with dark rings."""
    x, y = _project(view, *center, base)
    _, tip = _project(view, *center, base + tall_m)
    radius = max(2, round(radius_m * PIXELS_PER_METER_DETAIL))
    rows = y - tip
    for row in range(rows + 1):
        half = round(radius * math.sqrt(max(0.0, 1 - (row / rows) ** 2.4)))
        if half:
            banded = row % rib >= rib - 1
            lit = SLOTS_32["road_major"] if banded else SLOTS_32["road_line"]
            shade = SLOTS_32["background"] if banded else SLOTS_32["wall_shade"]
            split = x + round(half * 0.35)
            draw.line([(x - half, y - row), (split, y - row)], fill=lit)
            draw.line([(split + 1, y - row), (x + half, y - row)], fill=shade)
    draw.line([(x, tip - 5), (x, tip)], fill=SLOTS_32["roof_1"])


def _paint_laishang(draw, view, polygon, height) -> None:
    center, u, v, length, width = _ground_axes(polygon)
    white, shade = SLOTS_32["wall_lit"], SLOTS_32["wall_shade"]
    _box(draw, view, center, u, v, length / 2, width / 2, 0.0, 1.4, shade, shade, SLOTS_32["built"])
    stem, deck = 4.2, 7.0
    _box(draw, view, center, u, v, stem, stem, 1.4, height * 0.55, white, shade, white)
    steps = 5
    for step in range(steps):
        half = stem + (deck - stem) * (step + 1) / steps
        low = height * (0.55 + 0.45 * step / steps)
        high = height * (0.55 + 0.45 * (step + 1) / steps)
        _box(draw, view, center, u, v, half, half, low, high, white, shade, white)
    corner = deck - 1.6
    spires = [(center, 3.4, 9.5, 4)]
    for sign_u, sign_v in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        spires.append((center + u * sign_u * corner + v * sign_v * corner, 1.5, 5.5, 3))
    for point, radius, tall, rib in sorted(spires, key=lambda spire: -_depth(*spire[0])):
        _ribbed_spire(draw, view, point, height, radius, tall, rib)


def _paint_shanglen(draw, view, polygon, height) -> None:
    center, u, v, _, _ = _ground_axes(polygon)
    if abs(u[0]) < abs(v[0]):
        u, v = v, u
    ring = np.array(orient(polygon, 1.0).exterior.coords)

    def entrance(p, q, _lit):
        wall = (q - p) / np.linalg.norm(q - p)
        if float(np.linalg.norm(q - p)) > 6.5 and abs(float(np.dot(wall, v))) > 0.7:
            _wall_arch(draw, view, p, q, 0.14, 0.86, height * 0.84, SLOTS_32["road_line"])
            _wall_arch(draw, view, p, q, 0.24, 0.76, height * 0.72, SLOTS_32["background"])

    _paint_walls(
        draw,
        view,
        ring,
        height,
        None,
        False,
        False,
        SLOTS_32["roof_5"],
        SLOTS_32["roof_shade_5"],
        entrance,
    )
    tile, tile_shade, cream = SLOTS_32["roof_0"], SLOTS_32["roof_shade_0"], SLOTS_32["road_line"]
    _gable_roof(draw, view, center, v, u, 10.2, 4.6, height - 0.6, 2.2, tile, tile_shade, cream)
    _gable_roof(draw, view, center, u, v, 10.2, 5.0, height, 4.2, tile, tile_shade, cream)
    for sign in (-1, 1):
        x, y = _project(view, *(center + u * sign * 10.2), height + 4.2)
        draw.line([(x - 4, y - 5), (x, y), (x + 4, y - 5)], fill=cream)


def _paint_museum(draw, view, polygon, height) -> None:
    center, u, v, length, _ = _ground_axes(polygon)
    ring = np.array(orient(polygon, 1.0).exterior.coords)

    def arcade(p, q, _lit):
        count = max(1, int(float(np.linalg.norm(q - p)) / 4.5))
        for index in range(count):
            t0, t1 = (index + 0.22) / count, (index + 0.78) / count
            _wall_arch(draw, view, p, q, t0, t1, height * 0.78, SLOTS_32["wall_lit"])
            inner = (t1 - t0) * 0.2
            _wall_arch(
                draw, view, p, q, t0 + inner, t1 - inner, height * 0.66, SLOTS_32["roof_shade_2"]
            )

    _paint_walls(
        draw,
        view,
        ring,
        height,
        None,
        False,
        False,
        SLOTS_32["roof_0"],
        SLOTS_32["roof_shade_0"],
        arcade,
    )
    _gable_roof(
        draw,
        view,
        center,
        u,
        v,
        length / 2 + 0.6,
        7.0,
        height,
        3.0,
        SLOTS_32["roof_3"],
        SLOTS_32["roof_shade_3"],
        SLOTS_32["wall_lit"],
    )


def _paint_citadel(draw, view, polygon, height) -> None:
    ring = np.array(orient(polygon, 1.0).exterior.coords)

    def brickwork(p, q, _lit):
        wall = float(np.linalg.norm(q - p))
        panels = max(1, int(wall / 5.5))
        for index in range(panels + 1):
            point = p + (q - p) * (index / panels)
            draw.line(
                [_project(view, *point, height * 0.42), _project(view, *point, height * 0.82)],
                fill=SLOTS_32["roof_2"],
            )
        draw.line(
            [_project(view, *p, height * 0.84), _project(view, *q, height * 0.84)],
            fill=SLOTS_32["roof_2"],
        )
        for index in range(max(1, int(wall / 2.6))):
            point = p + (q - p) * ((index + 0.5) / max(1, int(wall / 2.6)))
            draw.point(_project(view, *point, height * 0.28), fill=SLOTS_32["background"])

    _paint_walls(
        draw,
        view,
        ring,
        height,
        None,
        False,
        False,
        SLOTS_32["roof_1"],
        SLOTS_32["roof_shade_1"],
        brickwork,
    )
    _roof_cap(draw, view, polygon, height, SLOTS_32["roof_1"], SLOTS_32["shrub"], 1.0)


def _dome_sites(polygon, count: int) -> list:
    """Return (center, room in meters) for the roomiest parts of a footprint, roomiest first."""
    sites = []
    remaining = polygon
    for _ in range(count):
        if remaining.is_empty:
            break
        spoke = shapely.maximum_inscribed_circle(remaining)
        point = np.array(spoke.coords[0])
        sites.append((point, spoke.length))
        remaining = remaining.difference(Point(point).buffer(spoke.length + 12.0))
    return sites


def _paint_assembly(draw, view, polygon, height) -> None:
    _, u, _, _, _ = _ground_axes(polygon)
    ring = np.array(orient(polygon, 1.0).exterior.coords)

    def facade(p, q, _lit):
        wall = float(np.linalg.norm(q - p))
        draw.line(
            [_project(view, *p, height * 0.92), _project(view, *q, height * 0.92)],
            fill=SLOTS_32["roof_shade_3"],
        )
        for index in range(max(1, int(wall / 4.0))):
            count = max(1, int(wall / 4.0))
            t0, t1 = (index + 0.25) / count, (index + 0.75) / count
            for low, high in ((0.12, 0.42), (0.52, 0.82)):
                a, b = p + (q - p) * t0, p + (q - p) * t1
                draw.polygon(
                    [
                        _project(view, *a, height * low),
                        _project(view, *b, height * low),
                        _project(view, *b, height * high),
                        _project(view, *a, height * high),
                    ],
                    fill=SLOTS_32["water_dark"],
                )

    _paint_walls(
        draw,
        view,
        ring,
        height,
        None,
        False,
        False,
        SLOTS_32["road_line"],
        SLOTS_32["roof_shade_4"],
        facade,
    )
    _roof_cap(draw, view, polygon, height, SLOTS_32["road_line"], SLOTS_32["roof_4"], 1.2)
    sites = _dome_sites(polygon, 3)
    main, room = sites[0]
    domes = [(main, min(13.0, room * 0.8), 5.0)]
    for sign in (-1, 1):
        turret = main + u * sign * (domes[0][1] + 3.5)
        if polygon.contains(Point(turret)):
            domes.append((turret, 3.5, 7.0))
    domes += [(point, min(7.0, spare * 0.7), 2.5) for point, spare in sites[1:]]
    for point, radius, drum in sorted(domes, key=lambda dome: -_depth(*dome[0])):
        x, y = _project(view, *point, height)
        _, top = _project(view, *point, height + drum)
        half = round(radius * PIXELS_PER_METER_DETAIL * 0.9)
        draw.rectangle(
            [x - half, top, x + half, y],
            fill=SLOTS_32["road_line"],
            outline=SLOTS_32["background"],
        )
        band = (top + y) // 2
        draw.rectangle([x - half + 2, band - 1, x + half - 2, band + 1], fill=SLOTS_32["water"])
        _dome(
            draw, view, point, height + drum, radius, SLOTS_32["road_line"], SLOTS_32["road_track"]
        )


def _paint_cathedral(draw, view, polygon, height) -> None:
    center, u, v, length, width = _ground_axes(polygon)
    ring = np.array(orient(polygon, 1.0).exterior.coords)
    tin, tin_shade = SLOTS_32["roof_5"], SLOTS_32["roof_shade_5"]
    white, shade = SLOTS_32["wall_lit"], SLOTS_32["wall_shade"]

    def windows(p, q, _lit):
        count = max(1, int(float(np.linalg.norm(q - p)) / 6.0))
        for index in range(count):
            t0, t1 = (index + 0.4) / count, (index + 0.6) / count
            _wall_arch(draw, view, p, q, t0, t1, height * 0.55, SLOTS_32["roof_2"])

    _paint_walls(draw, view, ring, height, None, False, False, decorate=windows)
    arm = min(length, width) * 0.24
    _gable_roof(draw, view, center, v, u, width / 2 + 0.5, arm, height, 4.5, tin, tin_shade, white)
    _gable_roof(draw, view, center, u, v, length / 2 + 0.5, arm, height, 4.5, tin, tin_shade, white)
    towers = [(center, 3.6, 5.5)]
    for sign_u, sign_v in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        towers.append((center + u * sign_u * arm * 1.15 + v * sign_v * arm * 1.15, 2.3, 3.5))
    for point, half, lift in sorted(towers, key=lambda tower: -_depth(*tower[0])):
        top = height + lift
        _box(draw, view, point, u, v, half, half, height, top, white, shade, white)
        _pyramid_roof(draw, view, point, u, v, half + 0.7, half + 0.7, top, 5.0, tin, tin_shade)
        x, y = _project(view, *point, top + 5.0)
        draw.line([(x, y - 7), (x, y)], fill=white)
        draw.line([(x - 2, y - 5), (x + 2, y - 5)], fill=white)


STYLE_PAINTERS = {
    "assembly": _paint_assembly,
    "cathedral": _paint_cathedral,
    "citadel": _paint_citadel,
    "gate": _paint_gate,
    "laishang": _paint_laishang,
    "market": _paint_market,
    "museum": _paint_museum,
    "pavilion": _paint_pavilion,
    "shanglen": _paint_shanglen,
    "stand": _paint_stand,
    "temple": _paint_temple,
    "terminal": _paint_terminal,
}


def _paint_building(draw, view, polygon, height, building_id, seed, style=None) -> None:
    if style:
        STYLE_PAINTERS[style["style"]](draw, view, polygon, height)
        return
    area = polygon.area
    envelope = shapely.minimum_rotated_rectangle(polygon).area
    rectangular = envelope > 0 and area / envelope >= 0.85 and not polygon.interiors
    kind = _classify(area, height, rectangular, building_id, seed)
    index = _hash(seed, building_id, 6)
    if kind in ("house", "shed"):
        tin = (0, 1, 2, 3, 5)
        index = tin[index % len(tin)]
    elif kind in ("block", "flat", "shop") and _hash(seed, building_id + "c", 10) < 6:
        index = 4
    slot = SLOTS_32[f"roof_{index}"]
    shade = SLOTS_32[f"roof_shade_{index}"]
    if kind == "house" and area < LOW_HOUSE_MAX_M2:
        _paint_low_house(draw, view, polygon, height, slot, shade)
    elif kind in ("house", "shed"):
        _paint_pitched(draw, view, polygon, height, slot, shade, kind == "house", True)
    else:
        _paint_flat(draw, view, polygon, height, slot, shade, kind, building_id, seed)


def _tree_sprite(radius: int, seed: int) -> tuple[Image.Image, Image.Image, int]:
    """Return (sprite, mask, crown_center_y) for a shaded canopy with a short trunk."""
    width = 2 * radius + 3
    crown_h = int(radius * 1.7)
    height = crown_h + 6
    rng = np.random.default_rng(seed)
    cx, cy = (width - 1) / 2, radius * 0.85 + 1
    lumps = [
        (
            cx + rng.uniform(-0.55, 0.55) * radius,
            cy + rng.uniform(-0.45, 0.45) * radius,
            radius * rng.uniform(0.45, 0.72),
        )
        for _ in range(9)
    ]
    lumps.append((cx, cy, radius * 0.72))
    ys, xs = np.mgrid[0:height, 0:width]
    field = np.zeros(xs.shape, dtype="float32")
    for lump_x, lump_y, lump_r in lumps:
        distance = ((xs - lump_x) ** 2 + ((ys - lump_y) / 0.88) ** 2) / lump_r**2
        field = np.maximum(field, 1.0 - distance)
    crown = field > 0
    sprite = np.full(xs.shape, SLOTS_32["canopy_dark"], dtype="uint8")
    light = (-(xs - cx) * 0.55 - (ys - cy) * 0.83) / radius + field * 0.35
    jitter = hash_field(xs + seed, ys, 31) * 0.26
    sprite[light + jitter > 0.05] = SLOTS_32["tree"]
    sprite[light + jitter > 0.42] = SLOTS_32["shrub"]
    sprite[light + jitter > 0.78] = SLOTS_32["canopy_light"]
    trunk = (np.abs(xs - cx) <= 1) & (ys > crown_h - 2)
    mask = crown | trunk
    sprite[trunk & ~crown] = SLOTS_32["background"]
    return (
        Image.fromarray(sprite),
        Image.fromarray(mask.astype("uint8") * 255),
        height,
    )


def _tree_points(
    layers: Layers, surfaces: gpd.GeoDataFrame, tree_rows: list[LineString], seed: int
) -> np.ndarray:
    """Return (x, y, variant) for trees, placed the same way whatever the crop."""
    left, bottom, right, top = layers.patch.bounds
    columns = np.arange(left, right, TREE_SPACING_M)
    rows = np.arange(bottom, top, TREE_SPACING_M)
    grid_x, grid_y = np.meshgrid(columns, rows)
    rng = np.random.default_rng(seed + 7)
    x = grid_x.ravel() + rng.uniform(-2.6, 2.6, grid_x.size)
    y = grid_y.ravel() + rng.uniform(-2.6, 2.6, grid_x.size)
    roll = rng.uniform(0, 1, grid_x.size)
    variant = rng.integers(0, 12, grid_x.size)

    keep = np.zeros(x.size, dtype=bool)
    for row in layers.ground.itertuples():
        odds = TREE_ODDS.get(row.ground, 0.0)
        if odds:
            shapely.prepare(row.geometry)
            inside = shapely.contains_xy(row.geometry, x, y)
            keep |= inside & (roll < odds)

    extra = []
    for line in tree_rows:
        for distance in np.arange(0.0, line.length, 8.0):
            point = line.interpolate(float(distance))
            if layers.patch.contains(point):
                extra.append((point.x, point.y, int(distance) % 12))
    array = np.column_stack([x[keep], y[keep], variant[keep]]).astype("float64")
    if extra:
        array = np.vstack([array, np.array(extra, dtype="float64")])
    if not len(array):
        return np.empty((0, 3))

    blocked = np.concatenate(
        [
            np.asarray(_water_geometry(layers), dtype=object),
            layers.roads.geometry.buffer(layers.roads.width_m / 2 + 1.5).values.to_numpy(),
            layers.buildings.geometry.buffer(1.8).values.to_numpy(),
            surfaces.geometry.values.to_numpy(),
        ]
    )
    blocked = blocked[~shapely.is_missing(blocked) & ~shapely.is_empty(blocked)]
    hits, _ = shapely.STRtree(blocked).query(
        shapely.points(array[:, 0], array[:, 1]), predicate="intersects"
    )
    free = np.ones(len(array), dtype=bool)
    free[hits] = False
    return array[free]


@dataclass
class Scene:
    """Everything that is computed once per area and shared by its frames."""

    layers: Layers
    surfaces: gpd.GeoDataFrame
    trees: np.ndarray
    sprites: list
    landmarks: list[dict]
    seed: int
    indexes: dict[str, shapely.STRtree]
    styles: dict[str, dict]


RADIUS_PX = (6, 7, 8, 9, 10, 12)


def empty_surfaces() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"kind": []}, geometry=[], crs=METRIC_CRS)


def load_landmarks() -> list[dict]:
    to_metric = Transformer.from_crs(4326, METRIC_CRS, always_xy=True)
    landmarks = []
    for path in sorted(SPRITE_DIR.glob("*.json")):
        sidecar = json.loads(path.read_text())
        x, y = to_metric.transform(sidecar["placed_at"]["lon"], sidecar["placed_at"]["lat"])
        sprite = np.asarray(Image.open(SPRITE_DIR / sidecar.get("sprite", f"{path.stem}.png")))
        landmarks.append(
            {
                "x": x,
                "y": y,
                "sprite": sprite,
                "anchor": sidecar["anchor_px"],
                "clearing": sidecar.get("clearing_m", MINAR_CLEARING_M),
            }
        )
    return landmarks


def load_styles() -> dict[str, dict]:
    """Return footprint landmark styles, keyed by the building they replace."""
    styles = {}
    for entry in json.loads(LANDMARKS_PATH.read_text()):
        for building_id in entry["replaces"]:
            styles[building_id] = entry
    return styles


def compute_trees(
    layers: Layers,
    surfaces: gpd.GeoDataFrame,
    tree_rows: list[LineString],
    landmarks: list[dict],
    seed: int,
) -> np.ndarray:
    trees = _tree_points(layers, surfaces, tree_rows, seed)
    for landmark in landmarks:
        distance = np.hypot(trees[:, 0] - landmark["x"], trees[:, 1] - landmark["y"])
        trees = trees[distance > landmark["clearing"]]
    return trees


def build_scene(
    layers: Layers,
    tree_rows: list[LineString] | None = None,
    landmarks: list[dict] | None = None,
    surfaces: gpd.GeoDataFrame | None = None,
    seed: int = SEED,
    trees: np.ndarray | None = None,
    styles: dict[str, dict] | None = None,
) -> Scene:
    tree_rows = tree_rows or []
    landmarks = landmarks or []
    surfaces = empty_surfaces() if surfaces is None else surfaces
    styles = styles or {}
    if trees is None:
        trees = compute_trees(layers, surfaces, tree_rows, landmarks, seed)
        cleared = layers.buildings[layers.buildings.building_id.isin(list(styles))]
        for row in cleared.itertuples():
            clearing = styles[row.building_id].get("clearing_m")
            if clearing and len(trees):
                inside = shapely.contains_xy(
                    row.geometry.buffer(clearing), trees[:, 0], trees[:, 1]
                )
                trees = trees[~inside]
    # Exploded so a frame only touches the ground fragments it can see.
    ground = layers.ground.explode(index_parts=False).reset_index(drop=True)
    local = Layers(
        layers.patch, ground, layers.water, layers.waterways, layers.roads, layers.buildings
    )
    frames = {
        "ground": ground,
        "water": layers.water,
        "waterways": layers.waterways,
        "roads": layers.roads,
        "buildings": layers.buildings,
        "surfaces": surfaces,
    }
    indexes = {name: shapely.STRtree(frame.geometry.values) for name, frame in frames.items()}
    sprites = [_tree_sprite(RADIUS_PX[index % 6], seed + index) for index in range(12)]
    return Scene(local, surfaces, trees, sprites, landmarks, seed, indexes, styles)


def _view_quad(view: Viewport) -> shapely.Polygon:
    """Return the ground area that the view's rectangle covers."""
    a, b, d, e = PROJECTION.matrix
    det = a * e - b * d
    corners = []
    for sx, sy in ((0, 0), (view.width, 0), (view.width, view.height), (0, view.height)):
        px, py = sx - view.x_offset, sy - view.y_offset
        corners.append(((e * px - b * py) / det, (-d * px + a * py) / det))
    return shapely.Polygon(corners)


def _select(frame: gpd.GeoDataFrame, index: shapely.STRtree, quad) -> gpd.GeoDataFrame:
    return frame.iloc[np.unique(index.query(quad, predicate="intersects"))]


def _local_layers(scene: Scene, quad: shapely.Polygon) -> Layers:
    """Return only the features a view can see."""
    layers = scene.layers
    return Layers(
        layers.patch,
        _select(layers.ground, scene.indexes["ground"], quad),
        _select(layers.water, scene.indexes["water"], quad),
        _select(layers.waterways, scene.indexes["waterways"], quad),
        _select(layers.roads, scene.indexes["roads"], quad),
        _select(layers.buildings, scene.indexes["buildings"], quad),
    )


def _screen(view: Viewport, x, y):
    a, b, d, e = PROJECTION.matrix
    return a * x + b * y + view.x_offset, d * x + e * y + view.y_offset


def _visible_landmarks(scene: Scene, view: Viewport) -> list[dict]:
    landmarks = []
    for landmark in scene.landmarks:
        sx, sy = _screen(view, landmark["x"], landmark["y"])
        if -200 < sx < view.width + 200 and -200 < sy < view.height + 200:
            landmarks.append(landmark)
    return landmarks


def _add_buildings(items: list, shadows: list, scene: Scene, local: Layers) -> None:
    for row in local.buildings.itertuples():
        parts = row.geometry.geoms if row.geometry.geom_type == "MultiPolygon" else [row.geometry]
        style = scene.styles.get(row.building_id)
        height = style.get("height_m", row.height_m) if style else row.height_m
        for part in parts:
            polygon = part
            if style and "scale" in style:
                factor = style["scale"]
                polygon = shapely.affinity.scale(part, factor, factor, origin="centroid")
            dx, dy = _sun_offset(height * SHADOW_PER_HEIGHT)
            moved = shapely.affinity.translate(polygon, dx, dy)
            shadows.append((shapely.convex_hull(shapely.union(polygon, moved)), 1))
            center = polygon.centroid
            items.append((-_depth(center.x, center.y), row.building_id, 0, polygon, height))


def _add_trees(items: list, shadows: list, scene: Scene, view: Viewport) -> None:
    trees = scene.trees
    screen_x, screen_y = _screen(view, trees[:, 0], trees[:, 1])
    nearby = (
        (screen_x > -40)
        & (screen_x < view.width + 40)
        & (screen_y > -40)
        & (screen_y < view.height + 60)
    )
    for x, y, variant in trees[nearby]:
        index = int(variant)
        radius_m = RADIUS_PX[index % 6] / PROJECTION.lift * 0.95
        dx, dy = _sun_offset(radius_m * 0.9)
        shadows.append((Point(x + dx, y + dy).buffer(radius_m * 0.9, quad_segs=4), 1))
        items.append((-_depth(x, y), f"tree/{x:.2f}/{y:.2f}", 1, (x, y), index))


def _add_landmarks(items: list, shadows: list, landmarks: list[dict]) -> None:
    for landmark in landmarks:
        dx, dy = _sun_offset(12.0)
        foot = Point(landmark["x"], landmark["y"]).buffer(4.5)
        shadow = shapely.convex_hull(shapely.union(foot, shapely.affinity.translate(foot, dx, dy)))
        shadows.append((shadow, 1))
        items.append((-_depth(landmark["x"], landmark["y"]), "landmark", 2, landmark, 0))


def _darken_shadows(canvas: np.ndarray, shadows: list, view: Viewport) -> None:
    mask = _burn(shadows, view).astype(bool)
    remap = np.arange(256, dtype="uint8")
    for name, darker in SHADOW.items():
        remap[SLOTS_32[name]] = SLOTS_32[darker]
    inside = mask & (canvas != SLOTS_32["background"])
    canvas[inside] = remap[canvas[inside]]


def _paint_items(image: Image.Image, items: list, scene: Scene, view: Viewport) -> None:
    """Draw buildings, trees, and sprites from the back of the scene to the front."""
    draw = ImageDraw.Draw(image)
    items.sort(key=lambda item: (item[0], item[1]))
    for _, label, kind, payload, extra in items:
        if kind == 0:
            _paint_building(draw, view, payload, extra, label, scene.seed, scene.styles.get(label))
        elif kind == 1:
            sprite, sprite_mask, height = scene.sprites[extra]
            x, y = _project(view, payload[0], payload[1], 0)
            image.paste(sprite, (x - sprite.width // 2, y - height + 1), sprite_mask)
        else:
            art = payload["sprite"]
            x, y = _project(view, payload["x"], payload["y"], 0)
            left = x - payload["anchor"][0]
            top = y - payload["anchor"][1]
            paste_mask = Image.fromarray(((art != TRANSPARENT).astype("uint8")) * 255)
            image.paste(Image.fromarray(art), (left, top), paste_mask)


def render_detail(scene: Scene, view: Viewport) -> np.ndarray:
    """Return a uint8 array of 32 palette slots."""
    quad = _view_quad(view)
    if not quad.intersects(scene.layers.patch):
        return np.full((view.height, view.width), SLOTS_32["background"], dtype="uint8")
    local = _local_layers(scene, quad)
    surfaces = _select(scene.surfaces, scene.indexes["surfaces"], quad)
    landmarks = _visible_landmarks(scene, view)

    canvas = _paint_ground(local, view)
    _paint_surfaces(canvas, surfaces, view)
    for landmark in landmarks:
        clearing = Point(landmark["x"], landmark["y"]).buffer(landmark["clearing"] * 0.6)
        canvas[_burn([(clearing, 1)], view).astype(bool)] = SLOTS_32["bare"]
    _paint_water(canvas, local, view)
    _paint_roads(canvas, local, view)

    items: list = []
    shadows: list = []
    _add_buildings(items, shadows, scene, local)
    _add_trees(items, shadows, scene, view)
    _add_landmarks(items, shadows, landmarks)
    _darken_shadows(canvas, shadows, view)

    image = Image.fromarray(canvas)
    _paint_items(image, items, scene, view)
    return np.asarray(image, dtype="uint8").copy()


def _load_tree_rows(area: Area) -> list[LineString]:
    rows = [
        f.geometry
        for f in load_features(raw_dir(area) / "osm.json")
        if f.tags.get("natural") == "tree_row" and f.geometry.geom_type == "LineString"
    ]
    if not rows:
        return []
    return list(gpd.GeoSeries(rows, crs=4326).to_crs(METRIC_CRS).values)


def _load_surfaces(area: Area) -> gpd.GeoDataFrame:
    path = derived_path(area)
    if "surfaces" not in pyogrio.list_layers(path)[:, 0]:
        return empty_surfaces()
    return gpd.read_file(path, layer="surfaces")


def trees_path(area: Area) -> Path:
    return Path("data/derived") / f"{area.name}_trees.npy"


def load_scene(area: Area, use_cached_trees: bool = False) -> Scene:
    layers = load_layers(area)
    surfaces = _load_surfaces(area)
    landmarks = load_landmarks()
    trees = np.load(trees_path(area)) if use_cached_trees else None
    return build_scene(
        layers, _load_tree_rows(area), landmarks, surfaces, trees=trees, styles=load_styles()
    )


def save_slots(slots: np.ndarray, path: Path) -> None:
    image = Image.fromarray(slots, mode="P")
    image.putpalette(detail_lookup())
    image.save(path, optimize=True)


def detail(area: Area) -> None:
    scene = load_scene(area)
    to_metric = Transformer.from_crs(4326, METRIC_CRS, always_xy=True)
    x, y = to_metric.transform(*CROP_CENTER)
    view = centered_viewport(PROJECTION, x, y, CROP_PX, CROP_PX)
    target = Path("out") / area.name
    target.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    output = target / f"{stamp}_detail-crop.png"
    save_slots(render_detail(scene, view), output)
    print(output)


def view_projection(view: str) -> Projection:
    return replace(PROJECTION_B, rotation_deg=VIEWS[view])


def use_view(view: str) -> None:
    """Point every painter in this process at one view."""
    global PROJECTION  # noqa: PLW0603
    PROJECTION = view_projection(view)


def frames_dir(area: Area, view: str = DEFAULT_VIEW) -> Path:
    name = "frames" if view == DEFAULT_VIEW else f"frames-{view}"
    return Path("out") / area.name / name


def manifest_path(area: Area, view: str = DEFAULT_VIEW) -> Path:
    name = "manifest.json" if view == DEFAULT_VIEW else f"manifest-{view}.json"
    return Path("out") / area.name / name


def frame_view(canvas: Viewport, column: int, row: int) -> Viewport:
    """Return a frame's view, including its apron, cut from the global canvas."""
    return Viewport(
        FRAME_PX + 2 * APRON_PX,
        FRAME_PX + 2 * APRON_PX,
        canvas.x_offset - column * FRAME_PX + APRON_PX,
        canvas.y_offset - row * FRAME_PX + APRON_PX,
    )


def render_frame(scene: Scene, canvas: Viewport, column: int, row: int) -> np.ndarray:
    slots = render_detail(scene, frame_view(canvas, column, row))
    return slots[APRON_PX:-APRON_PX, APRON_PX:-APRON_PX]


_worker: dict = {}


def _init_worker(area: Area, canvas: Viewport, view: str) -> None:
    use_view(view)
    _worker["scene"] = load_scene(area, use_cached_trees=True)
    _worker["canvas"] = canvas
    _worker["area"] = area
    _worker["view"] = view


def _render_and_save(cell: tuple[int, int]) -> tuple[int, int]:
    column, row = cell
    slots = render_frame(_worker["scene"], _worker["canvas"], column, row)
    save_slots(slots, frames_dir(_worker["area"], _worker["view"]) / f"{row:03d}_{column:03d}.png")
    return cell


def frame_grid(canvas: Viewport) -> tuple[int, int]:
    return math.ceil(canvas.width / FRAME_PX), math.ceil(canvas.height / FRAME_PX)


def frames(area: Area, only: list[tuple[int, int]] | None = None) -> None:
    """Render every view of the area as a grid of frames and write its manifests."""
    started = time.perf_counter()
    scene = load_scene(area)
    np.save(trees_path(area), scene.trees)
    print(f"{area.name}: {len(scene.trees)} trees")
    for view in VIEWS:
        _render_view(area, scene, view, only)
    print(f"done in {time.perf_counter() - started:.0f}s")


def _render_view(
    area: Area, scene: Scene, view: str, only: list[tuple[int, int]] | None = None
) -> None:
    started = time.perf_counter()
    projection = view_projection(view)
    canvas = full_viewport(projection, scene.layers)
    columns, rows = frame_grid(canvas)
    print(f"{view}: {columns} x {rows} frames")
    directory = frames_dir(area, view)
    directory.mkdir(parents=True, exist_ok=True)
    cells = only or [(column, row) for row in range(rows) for column in range(columns)]
    context = multiprocessing.get_context("spawn")
    with context.Pool(WORKERS, _init_worker, (area, canvas, view)) as pool:
        for count, _ in enumerate(pool.imap_unordered(_render_and_save, cells), 1):
            if count % 10 == 0 or count == len(cells):
                print(
                    f"{count}/{len(cells)} frames, {time.perf_counter() - started:.0f}s", flush=True
                )
    manifest_path(area, view).write_text(
        json.dumps(
            {
                "area": area.name,
                "projection": projection.name,
                "pixels_per_meter": 2.0,
                "rotation_deg": projection.rotation_deg,
                "ground_scale": projection.ground_scale,
                "matrix": list(projection.matrix),
                "x_offset": canvas.x_offset,
                "y_offset": canvas.y_offset,
                "canvas_width": columns * FRAME_PX,
                "canvas_height": rows * FRAME_PX,
                "frame_px": FRAME_PX,
                "columns": columns,
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )
