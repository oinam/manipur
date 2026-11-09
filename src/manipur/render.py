"""Stage 3: paint ground, water, roads, and extruded buildings into palette slots."""

import datetime as dt
import itertools
import math
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from affine import Affine
from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.affinity import affine_transform
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from manipur.areas import Area
from manipur.palettes import CANDIDATES, PALETTE, ROOF_SLOTS, SLOT, SLOTS, lookup
from manipur.prepare import METRIC_CRS, derived_path

SEED = 1891
PIXELS_PER_METER = 2.0
FRAME_SIZE = 2048
MARGIN_PX = 40
LINE_WIDTH_M = 1.0
LINED_ROADS = ("trunk", "primary")
ROAD_ORDER = (
    "path",
    "footway",
    "cycleway",
    "steps",
    "track",
    "pedestrian",
    "service",
    "living_street",
    "residential",
    "unclassified",
    "tertiary",
    "secondary",
    "primary",
    "trunk",
)
ROAD_SLOTS = {
    "path": "road_track",
    "footway": "road_track",
    "cycleway": "road_track",
    "steps": "road_track",
    "track": "road_track",
    "tertiary": "road_major",
    "secondary": "road_major",
    "primary": "road_major",
    "trunk": "road_major",
}
# Swatch panels center on the southwest corner of the moat: water, roads, dense wards.
SWATCH_CENTER = (93.9385, 24.8026)
SWATCH_PANEL_PX = 900


@dataclass(frozen=True)
class Projection:
    """Orthographic view: rotate the ground, squash its depth, lift by height."""

    name: str
    rotation_deg: float
    ground_scale: float
    height_scale: float

    @property
    def matrix(self) -> tuple[float, float, float, float]:
        """Return (a, b, d, e) mapping metric ground (x, y) to unshifted screen pixels."""
        angle = math.radians(self.rotation_deg)
        cos, sin = math.cos(angle), math.sin(angle)
        scale = PIXELS_PER_METER
        return (
            cos * scale,
            sin * scale,
            sin * self.ground_scale * scale,
            -cos * self.ground_scale * scale,
        )

    def depth(self, x: float, y: float) -> float:
        """Return distance from the viewer along the ground; larger is farther."""
        angle = math.radians(self.rotation_deg)
        return -x * math.sin(angle) + y * math.cos(angle)

    @property
    def lift(self) -> float:
        """Return screen pixels moved upward per meter of height."""
        return self.height_scale * PIXELS_PER_METER


PROJECTION_A = Projection(
    "a-tilt45-rot15", 15.0, math.sin(math.radians(45)), math.cos(math.radians(45))
)
PROJECTION_B = Projection("b-dimetric-2to1", 45.0, 0.5, math.cos(math.radians(30)))
PROJECTIONS = (PROJECTION_B,)


@dataclass(frozen=True)
class Viewport:
    """Pixel canvas; offsets move unshifted screen coordinates onto it."""

    width: int
    height: int
    x_offset: float
    y_offset: float


@dataclass(frozen=True)
class Layers:
    patch: shapely.Geometry
    ground: gpd.GeoDataFrame
    water: gpd.GeoDataFrame
    waterways: gpd.GeoDataFrame
    roads: gpd.GeoDataFrame
    buildings: gpd.GeoDataFrame


def load_layers(area: Area) -> Layers:
    path = derived_path(area)
    frames = {
        name: gpd.read_file(path, layer=name)
        for name in ("patch", "ground", "water", "waterways", "roads", "buildings")
    }
    patch = frames.pop("patch").geometry.iloc[0]
    return Layers(patch=patch, **frames)


def full_viewport(projection: Projection, layers: Layers) -> Viewport:
    """Fit the whole patch, leaving headroom for the tallest building."""
    a, b, d, e = projection.matrix
    xs, ys = np.array(layers.patch.exterior.coords).T
    screen_x = a * xs + b * ys
    screen_y = d * xs + e * ys
    headroom = float(layers.buildings["height_m"].max()) * projection.lift
    left = math.floor(screen_x.min()) - MARGIN_PX
    top = math.floor(screen_y.min() - headroom) - MARGIN_PX
    width = math.ceil(screen_x.max()) + MARGIN_PX - left
    height = math.ceil(screen_y.max()) + MARGIN_PX - top
    return Viewport(width, height, -left, -top)


def centered_viewport(projection: Projection, x: float, y: float, width: int, height: int):
    a, b, d, e = projection.matrix
    return Viewport(
        width,
        height,
        round(width / 2 - (a * x + b * y)),
        round(height / 2 - (d * x + e * y)),
    )


def _paint_flat(canvas: np.ndarray, projection: Projection, view: Viewport, layers: Layers) -> None:
    a, b, d, e = projection.matrix
    matrix = (a, b, d, e, view.x_offset, view.y_offset)

    def shapes_of(geometries, slot: int):
        for geometry in geometries:
            if geometry is not None and not geometry.is_empty:
                yield affine_transform(geometry, matrix), slot

    ordered = []
    for row in layers.ground.itertuples():
        ordered.extend(shapes_of([row.geometry], SLOT[row.ground]))
    ordered.extend(shapes_of(layers.water.geometry, SLOT["water"]))
    rivers = layers.waterways.geometry.buffer(layers.waterways.width_m / 2)
    ordered.extend(shapes_of(rivers.intersection(layers.patch), SLOT["water"]))
    for road_class in ROAD_ORDER:
        part = layers.roads[layers.roads.road_class == road_class]
        if part.empty:
            continue
        slot = SLOT[ROAD_SLOTS.get(road_class, "road_minor")]
        body = part.geometry.buffer(part.width_m / 2, cap_style="flat")
        ordered.extend(shapes_of(body.intersection(layers.patch), slot))
    lined = layers.roads[layers.roads.road_class.isin(LINED_ROADS)]
    ordered.extend(shapes_of(lined.geometry.buffer(LINE_WIDTH_M / 2), SLOT["road_line"]))
    if ordered:
        burned = rasterize(
            ordered,
            out_shape=(view.height, view.width),
            transform=Affine.identity(),
            fill=SLOT["background"],
            dtype="uint8",
        )
        canvas[:] = burned


def _roof_slot(building_id: str, seed: int) -> int:
    return ROOF_SLOTS[zlib.crc32(f"{seed}:{building_id}".encode()) % len(ROOF_SLOTS)]


def _project(points: np.ndarray, projection: Projection, view: Viewport, z: float) -> list:
    a, b, d, e = projection.matrix
    screen_x = np.rint(a * points[:, 0] + b * points[:, 1] + view.x_offset)
    screen_y = np.rint(d * points[:, 0] + e * points[:, 1] + view.y_offset - z * projection.lift)
    return [(int(x), int(y)) for x, y in zip(screen_x, screen_y, strict=True)]


def _paint_building(
    draw: ImageDraw.ImageDraw,
    polygon: Polygon,
    height: float,
    roof: int,
    projection: Projection,
    view: Viewport,
) -> None:
    angle = math.radians(projection.rotation_deg)
    cos, sin = math.cos(angle), math.sin(angle)
    ring = np.array(orient(polygon, 1.0).exterior.coords)
    walls = []
    for start, end in itertools.pairwise(ring):
        dx, dy = end - start
        # Outward normal of a counterclockwise ring, in the rotated ground frame.
        normal_x = cos * dy - sin * dx
        normal_depth = -sin * dy - cos * dx
        if normal_depth < 0:
            depth = projection.depth(*((start + end) / 2))
            walls.append((-depth, start, end, normal_x))
    for _, start, end, normal_x in sorted(walls, key=lambda wall: wall[0]):
        base = np.array([start, end])
        quad = _project(base, projection, view, 0.0) + _project(
            base[::-1], projection, view, height
        )
        draw.polygon(quad, fill=SLOT["wall_lit"] if normal_x < 0 else SLOT["wall_shade"])
    draw.polygon(_project(ring, projection, view, height), fill=roof)
    for interior in polygon.interiors:
        draw.polygon(
            _project(np.array(interior.coords), projection, view, height),
            fill=SLOT["wall_shade"],
        )


def render_slots(
    layers: Layers, projection: Projection, view: Viewport, seed: int = SEED
) -> np.ndarray:
    """Return a uint8 array of palette slot indices."""
    canvas = np.full((view.height, view.width), SLOT["background"], dtype="uint8")
    _paint_flat(canvas, projection, view, layers)
    image = Image.fromarray(canvas, mode="L")
    draw = ImageDraw.Draw(image)

    parts = []
    for row in layers.buildings.itertuples():
        polygons = (
            row.geometry.geoms if row.geometry.geom_type == "MultiPolygon" else [row.geometry]
        )
        for polygon in polygons:
            center = polygon.centroid
            parts.append(
                (projection.depth(center.x, center.y), row.building_id, polygon, row.height_m)
            )
    parts.sort(key=lambda part: (-part[0], part[1]))

    for _, building_id, polygon, height in parts:
        _paint_building(draw, polygon, height, _roof_slot(building_id, seed), projection, view)
    return np.asarray(image, dtype="uint8").copy()


def to_image(slots: np.ndarray, palette: dict[str, str]) -> Image.Image:
    image = Image.fromarray(slots, mode="P")
    image.putpalette(lookup(palette))
    return image


def _stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def render(area: Area) -> None:
    layers = load_layers(area)
    target = Path("out") / area.name
    target.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    center = layers.patch.centroid
    for projection in PROJECTIONS:
        views = {
            "frame": centered_viewport(projection, center.x, center.y, FRAME_SIZE, FRAME_SIZE),
            "full": full_viewport(projection, layers),
        }
        for label, view in views.items():
            started = time.perf_counter()
            slots = render_slots(layers, projection, view)
            output = target / f"{stamp}_{projection.name}_{label}.png"
            to_image(slots, PALETTE).save(output, optimize=True)
            elapsed = time.perf_counter() - started
            print(f"{output}: {view.width} x {view.height}, {elapsed:.1f}s")


def _swatch_font() -> ImageFont.ImageFont:
    return ImageFont.load_default(size=22)


def swatches(area: Area) -> None:
    """Apply every candidate palette to one crop, per projection, side by side."""
    layers = load_layers(area)
    to_metric = Transformer.from_crs(4326, METRIC_CRS, always_xy=True)
    x, y = to_metric.transform(*SWATCH_CENTER)
    panel = SWATCH_PANEL_PX
    gap = 24
    title = 44
    strip = 110
    names = list(CANDIDATES)
    width = gap + (panel + gap) * len(names)
    row_height = title + panel + strip + gap
    sheet = Image.new("RGB", (width, gap + row_height * len(PROJECTIONS)), "#ffffff")
    draw = ImageDraw.Draw(sheet)
    font = _swatch_font()

    for row, projection in enumerate(PROJECTIONS):
        view = centered_viewport(projection, x, y, panel, panel)
        slots = render_slots(layers, projection, view)
        top = gap + row * row_height
        for column, name in enumerate(names):
            left = gap + column * (panel + gap)
            palette = CANDIDATES[name]
            draw.text(
                (left, top + 8),
                f"{name}  ({len(set(palette.values()))} colors)  {projection.name}",
                fill="#111111",
                font=font,
            )
            sheet.paste(to_image(slots, palette).convert("RGB"), (left, top + title))
            chip = panel / len(SLOTS)
            for index, slot in enumerate(SLOTS):
                x0 = left + index * chip
                draw.rectangle(
                    (x0, top + title + panel + 8, x0 + chip - 1, top + title + panel + strip - 8),
                    fill=palette[slot],
                )

    target = Path("out") / area.name
    target.mkdir(parents=True, exist_ok=True)
    output = target / f"{_stamp()}_palette-swatches.png"
    sheet.save(output, optimize=True)
    print(f"{output}: {sheet.width} x {sheet.height}")
