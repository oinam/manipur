"""Near-final styling for one crop, to judge what the procedural map can become."""

import datetime as dt
import json
import math
import zlib
from pathlib import Path

import numpy as np
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
from manipur.prepare import METRIC_CRS
from manipur.render import (
    LINED_ROADS,
    PROJECTION_B,
    ROAD_ORDER,
    ROAD_SLOTS,
    SEED,
    Layers,
    Viewport,
    centered_viewport,
    load_layers,
)

CROP_CENTER = (93.93759, 24.80343)
CROP_PX = 900
PROJECTION = PROJECTION_B
SPRITE_DIR = Path("assets/sprites")
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
SHADOW_PER_HEIGHT = 0.75
STOREY_M = 3.2
BLUR_RADIUS_PX = 16
FOOTPATH_M = 1.8
MINAR_CLEARING_M = 16.0


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
    return canvas


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


def _in_view(view: Viewport, geometry, pad: float = 120.0) -> bool:
    a, b, d, e = PROJECTION.matrix
    minx, miny, maxx, maxy = geometry.bounds
    corners = [(minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy)]
    screen = [(a * x + b * y + view.x_offset, d * x + e * y + view.y_offset) for x, y in corners]
    xs = [point[0] for point in screen]
    ys = [point[1] for point in screen]
    return (
        max(xs) >= -pad
        and min(xs) <= view.width + pad
        and max(ys) >= -pad
        and min(ys) <= view.height + pad
    )


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


def _paint_walls(draw, view, ring, top, gable_top, shutters, windows) -> None:
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
        fill = SLOTS_32["wall_lit"] if lit else SLOTS_32["wall_shade"]
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


def _paint_pitched(draw, view, polygon, height, slot, shade, windows, ribbed) -> None:
    corners = np.array(shapely.minimum_rotated_rectangle(polygon).exterior.coords)[:4]
    if np.linalg.norm(corners[1] - corners[0]) < np.linalg.norm(corners[2] - corners[1]):
        corners = np.roll(corners, -1, axis=0)
    a, b, c, d = corners
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
    gables = {index: ridge for index in (1, 3)}
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
    if polygon.area >= 40 and _hash(seed, building_id + "t", 3) == 0:
        center = polygon.representative_point()
        x, y = _project(view, center.x, center.y, height)
        draw.rectangle([x - 2, y - 6, x + 2, y], fill=SLOTS_32["background"])
        draw.line([(x - 2, y - 6), (x + 2, y - 6)], fill=SLOTS_32["road_major"])


def _paint_building(draw, view, polygon, height, building_id, seed) -> None:
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
    if kind in ("house", "shed"):
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


def _tree_points(layers: Layers, tree_rows: list[LineString], seed: int) -> np.ndarray:
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
            inside = shapely.contains_xy(row.geometry, x, y)
            keep |= inside & (roll < odds)

    points = list(zip(x[keep], y[keep], variant[keep], strict=True))
    for line in tree_rows:
        for distance in np.arange(0.0, line.length, 8.0):
            point = line.interpolate(float(distance))
            if layers.patch.contains(point):
                points.append((point.x, point.y, int(distance) % 12))
    if not points:
        return np.empty((0, 3))
    array = np.array(points, dtype="float64")

    blocked = shapely.union_all(
        [
            *_water_geometry(layers),
            *layers.roads.geometry.buffer(layers.roads.width_m / 2 + 1.5).values,
            *layers.buildings.geometry.buffer(1.8).values,
        ]
    )
    shapely.prepare(blocked)
    free = ~shapely.contains_xy(blocked, array[:, 0], array[:, 1])
    return array[free]


def _load_landmark() -> dict:
    sidecar = json.loads((SPRITE_DIR / "shaheed_minar.json").read_text())
    to_metric = Transformer.from_crs(4326, METRIC_CRS, always_xy=True)
    x, y = to_metric.transform(sidecar["placed_at"]["lon"], sidecar["placed_at"]["lat"])
    sprite = np.asarray(Image.open(SPRITE_DIR / "shaheed_minar.png"))
    return {"x": x, "y": y, "sprite": sprite, "anchor": sidecar["anchor_px"]}


def render_detail(
    layers: Layers,
    view: Viewport,
    tree_rows: list[LineString] | None = None,
    landmarks: list[dict] | None = None,
    seed: int = SEED,
) -> np.ndarray:
    """Return a uint8 array of 32 palette slots."""
    tree_rows = tree_rows or []
    landmarks = landmarks or []
    canvas = _paint_ground(layers, view)
    for landmark in landmarks:
        clearing = Point(landmark["x"], landmark["y"]).buffer(MINAR_CLEARING_M * 0.6)
        canvas[_burn([(clearing, 1)], view).astype(bool)] = SLOTS_32["bare"]
    _paint_water(canvas, layers, view)
    _paint_roads(canvas, layers, view)

    trees = _tree_points(layers, tree_rows, seed)
    for landmark in landmarks:
        far = np.hypot(trees[:, 0] - landmark["x"], trees[:, 1] - landmark["y"]) > MINAR_CLEARING_M
        trees = trees[far]
    radius_px = (6, 7, 8, 9, 10, 12)
    sprites = [_tree_sprite(radius_px[index % 6], seed + index) for index in range(12)]

    items = []
    shadows = []
    for row in layers.buildings.itertuples():
        parts = row.geometry.geoms if row.geometry.geom_type == "MultiPolygon" else [row.geometry]
        for polygon in parts:
            if not _in_view(view, polygon):
                continue
            dx, dy = _sun_offset(row.height_m * SHADOW_PER_HEIGHT)
            moved = shapely.affinity.translate(polygon, dx, dy)
            shadows.append((shapely.convex_hull(shapely.union(polygon, moved)), 1))
            center = polygon.centroid
            items.append((-_depth(center.x, center.y), row.building_id, 0, polygon, row.height_m))

    a, b, d, e = PROJECTION.matrix
    screen_x = a * trees[:, 0] + b * trees[:, 1] + view.x_offset
    screen_y = d * trees[:, 0] + e * trees[:, 1] + view.y_offset
    nearby = (
        (screen_x > -40)
        & (screen_x < view.width + 40)
        & (screen_y > -40)
        & (screen_y < view.height + 60)
    )
    for x, y, variant in trees[nearby]:
        index = int(variant)
        radius_m = radius_px[index % 6] / PROJECTION.lift * 0.95
        dx, dy = _sun_offset(radius_m * 0.9)
        shadows.append((Point(x + dx, y + dy).buffer(radius_m * 0.9, quad_segs=4), 1))
        items.append((-_depth(x, y), f"tree/{x:.2f}/{y:.2f}", 1, (x, y), index))
    for landmark in landmarks:
        dx, dy = _sun_offset(12.0)
        foot = Point(landmark["x"], landmark["y"]).buffer(4.5)
        shadow = shapely.convex_hull(shapely.union(foot, shapely.affinity.translate(foot, dx, dy)))
        shadows.append((shadow, 1))
        items.append((-_depth(landmark["x"], landmark["y"]), "landmark", 2, landmark, 0))

    mask = _burn(shadows, view).astype(bool)
    remap = np.arange(256, dtype="uint8")
    for name, darker in SHADOW.items():
        remap[SLOTS_32[name]] = SLOTS_32[darker]
    inside = mask & (canvas != SLOTS_32["background"])
    canvas[inside] = remap[canvas[inside]]

    image = Image.fromarray(canvas)
    draw = ImageDraw.Draw(image)
    items.sort(key=lambda item: (item[0], item[1]))
    for _, label, kind, payload, extra in items:
        if kind == 0:
            _paint_building(draw, view, payload, extra, label, seed)
        elif kind == 1:
            sprite, sprite_mask, height = sprites[extra]
            x, y = _project(view, payload[0], payload[1], 0)
            image.paste(sprite, (x - sprite.width // 2, y - height + 1), sprite_mask)
        else:
            art = payload["sprite"]
            x, y = _project(view, payload["x"], payload["y"], 0)
            left = x - payload["anchor"][0]
            top = y - payload["anchor"][1]
            paste_mask = Image.fromarray(((art != TRANSPARENT).astype("uint8")) * 255)
            image.paste(Image.fromarray(art), (left, top), paste_mask)
    return np.asarray(image, dtype="uint8").copy()


def _load_tree_rows(area: Area) -> list[LineString]:
    import geopandas as gpd

    rows = [
        f.geometry
        for f in load_features(raw_dir(area) / "osm.json")
        if f.tags.get("natural") == "tree_row" and f.geometry.geom_type == "LineString"
    ]
    if not rows:
        return []
    return list(gpd.GeoSeries(rows, crs=4326).to_crs(METRIC_CRS).values)


def detail(area: Area) -> None:
    layers = load_layers(area)
    to_metric = Transformer.from_crs(4326, METRIC_CRS, always_xy=True)
    x, y = to_metric.transform(*CROP_CENTER)
    view = centered_viewport(PROJECTION, x, y, CROP_PX, CROP_PX)
    slots = render_detail(layers, view, _load_tree_rows(area), [_load_landmark()])
    image = Image.fromarray(slots, mode="P")
    image.putpalette(detail_lookup())
    target = Path("out") / area.name
    target.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    output = target / f"{stamp}_detail-crop.png"
    image.save(output, optimize=True)
    print(output)
