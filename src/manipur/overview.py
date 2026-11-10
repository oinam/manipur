"""Top-down check of a whole region from land cover and terrain, before any isometry."""

import datetime as dt
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import osmium
import rasterio
import shapely
from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.merge import merge
from rasterio.transform import from_origin
from rasterio.warp import reproject

from manipur.areas import AREAS, Area
from manipur.fetch import GEOFABRIK_URL, WORLDCOVER_URL, raw_dir
from manipur.palettes import PALETTE
from manipur.prepare import WORLDCOVER_CLASSES

METRIC_CRS = 32646
METERS_PER_PIXEL = 100.0
# Sources are read at about 60 m, then resampled onto the 100 m output grid.
READ_RES_DEG = 1 / 1800
DEM_URL = (
    "https://copernicus-dem-30m.s3.amazonaws.com/"
    "Copernicus_DSM_COG_10_{tile}_DEM/Copernicus_DSM_COG_10_{tile}_DEM.tif"
)
# Hill shading: light from the northwest, posterized so it reads as flat bands.
SUN_AZIMUTH_DEG = 315.0
SUN_ALTITUDE_DEG = 40.0
Z_FACTOR = 2.0
SHADE_LEVELS = np.array([0.62, 0.74, 0.86, 0.96, 1.06, 1.14])
OUTSIDE_FADE = 0.6
PAPER = (233, 228, 216)
INK = (31, 42, 46)
IMPHAL_BOX = (178, 64, 46)
STATE_NAME = "Manipur"


def _tiles(area: Area, step: int) -> list[tuple[int, int]]:
    """Return the southwest corners of the step-degree tiles covering the area."""
    lats = range(math.floor(area.south / step) * step, math.ceil(area.north / step) * step, step)
    lons = range(math.floor(area.west / step) * step, math.ceil(area.east / step) * step, step)
    return [(lat, lon) for lat in lats for lon in lons]


def _write(path: Path, data: np.ndarray, transform, dtype: str) -> None:
    profile = {
        "driver": "GTiff",
        "height": data.shape[0],
        "width": data.shape[1],
        "count": 1,
        "dtype": dtype,
        "crs": "EPSG:4326",
        "transform": transform,
        "compress": "deflate",
    }
    with rasterio.open(path, "w", **profile) as sink:
        sink.write(data.astype(dtype), 1)


def fetch_rasters(area: Area) -> list[tuple[str, str, str]]:
    """Read land cover and elevation for the area at the overview's read resolution."""
    records = []
    cover_path = raw_dir(area) / "worldcover_2021_overview.tif"
    cover_urls = [
        WORLDCOVER_URL.format(tile=f"N{lat:02d}E{lon:03d}") for lat, lon in _tiles(area, 3)
    ]
    if not cover_path.exists():
        data, transform = merge(
            cover_urls, bounds=area.bounds, res=READ_RES_DEG, resampling=Resampling.mode, nodata=0
        )
        _write(cover_path, data[0], transform, "uint8")
        print(f"worldcover: {data.shape[2]} x {data.shape[1]} cells")
    records += [("ESA WorldCover 2021 v200", url, cover_path.name) for url in cover_urls]

    dem_path = raw_dir(area) / "dem_glo30.tif"
    dem_urls = [DEM_URL.format(tile=f"N{lat:02d}_00_E{lon:03d}_00") for lat, lon in _tiles(area, 1)]
    if not dem_path.exists():
        data, transform = merge(
            dem_urls, bounds=area.bounds, res=READ_RES_DEG, resampling=Resampling.bilinear
        )
        _write(dem_path, data[0], transform, "float32")
        print(f"dem: {data.shape[2]} x {data.shape[1]} cells")
    records += [("Copernicus GLO-30 DEM", url, dem_path.name) for url in dem_urls]
    return records


def fetch_outlines(area: Area) -> tuple[Path, str]:
    """Pull the state and district boundaries, rivers, and towns from the Geofabrik extract."""
    target = raw_dir(area) / "outlines.json"
    url = GEOFABRIK_URL.format(extract=area.osm_extract)
    if target.exists():
        return target, url
    cache = Path("data/raw/_geofabrik") / url.rsplit("/", 1)[1]
    if not cache.exists():
        raise SystemExit(f"overview: {cache} is missing; run `manipur fetch --area imphal` first")
    west, south, east, north = area.bounds
    bbox = shapely.box(west, south, east, north)
    geojson = osmium.geom.GeoJSONFactory()
    boundaries, rivers, towns = [], [], []
    processor = (
        osmium.FileProcessor(str(cache))
        .with_locations()
        .with_areas(osmium.filter.TagFilter(("boundary", "administrative")))
    )
    for item in processor:
        tags = item.tags
        if item.is_area():
            level = tags.get("admin_level")
            if tags.get("boundary") == "administrative" and level in ("4", "5"):
                shape = shapely.geometry.shape(json.loads(geojson.create_multipolygon(item)))
                if shape.intersects(bbox):
                    boundaries.append(
                        {"level": int(level), "name": tags.get("name", ""), "wkt": shape.wkt}
                    )
        elif item.is_way() and tags.get("waterway") == "river":
            line = shapely.geometry.shape(json.loads(geojson.create_linestring(item)))
            if line.intersects(bbox):
                rivers.append({"name": tags.get("name", ""), "wkt": line.wkt})
        elif item.is_node() and tags.get("place") in ("city", "town"):
            lon, lat = item.location.lon, item.location.lat
            if west <= lon <= east and south <= lat <= north:
                towns.append({"name": tags.get("name", ""), "lon": lon, "lat": lat})
    target.write_text(json.dumps({"boundaries": boundaries, "rivers": rivers, "towns": towns}))
    print(f"outlines: {len(boundaries)} boundaries, {len(rivers)} rivers, {len(towns)} towns")
    return target, url


def _hillshade(dem: np.ndarray) -> np.ndarray:
    dy, dx = np.gradient(dem * Z_FACTOR, METERS_PER_PIXEL)
    slope = np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(-dx, dy)
    azimuth = math.radians(360.0 - SUN_AZIMUTH_DEG + 90.0)
    altitude = math.radians(SUN_ALTITUDE_DEG)
    shade = math.sin(altitude) * np.cos(slope) + math.cos(altitude) * np.sin(slope) * np.cos(
        azimuth - aspect
    )
    flat = math.sin(altitude)
    # Flat ground lands on the band just under 1.0, so the valley keeps its true color.
    bands = np.clip(np.round((shade - flat) * 8) + 3, 0, len(SHADE_LEVELS) - 1).astype(int)
    return SHADE_LEVELS[bands]


def _rgb(name: str) -> tuple[int, int, int]:
    color = PALETTE[name].lstrip("#")
    return tuple(int(color[index : index + 2], 16) for index in (0, 2, 4))


@dataclass(frozen=True)
class Grid:
    """The output raster: a north-up metric grid covering the area's bounding box."""

    to_metric: Transformer
    left: float
    top: float
    width: int
    height: int

    @classmethod
    def covering(cls, area: Area) -> "Grid":
        to_metric = Transformer.from_crs(4326, METRIC_CRS, always_xy=True)
        corners = [
            to_metric.transform(lon, lat) for lon in area.bounds[::2] for lat in area.bounds[1::2]
        ]
        left = min(x for x, _ in corners)
        top = max(y for _, y in corners)
        width = math.ceil((max(x for x, _ in corners) - left) / METERS_PER_PIXEL)
        height = math.ceil((top - min(y for _, y in corners)) / METERS_PER_PIXEL)
        return cls(to_metric, left, top, width, height)

    @property
    def transform(self):
        return from_origin(self.left, self.top, METERS_PER_PIXEL, METERS_PER_PIXEL)

    def metric(self, geometry):
        return shapely.ops.transform(self.to_metric.transform, geometry)

    def pixels(self, line) -> list[tuple[float, float]]:
        return [
            ((x - self.left) / METERS_PER_PIXEL, (self.top - y) / METERS_PER_PIXEL)
            for x, y in line.coords
        ]

    def resample(self, path: Path, resampling: Resampling, dtype: str) -> np.ndarray:
        grid = np.zeros((self.height, self.width), dtype=dtype)
        with rasterio.open(path) as source:
            reproject(
                rasterio.band(source, 1),
                grid,
                dst_transform=self.transform,
                dst_crs=f"EPSG:{METRIC_CRS}",
                resampling=resampling,
            )
        return grid


def _rings(geometry):
    for polygon in getattr(geometry, "geoms", [geometry]):
        yield polygon.exterior
        yield from polygon.interiors


def _draw_outlines(draw: ImageDraw.ImageDraw, grid: Grid, outlines: dict, state) -> None:
    """Draw rivers, district lines, the state line, and the box today's map covers."""
    water = _rgb("water")
    for river in outlines["rivers"]:
        for part in shapely.get_parts(grid.metric(shapely.from_wkt(river["wkt"]))):
            draw.line(grid.pixels(part), fill=water, width=2)
    for boundary in outlines["boundaries"]:
        shape = grid.metric(shapely.from_wkt(boundary["wkt"]))
        if boundary["level"] == 5 and state.contains(shape.representative_point()):
            for ring in _rings(shape):
                draw.line(grid.pixels(ring), fill=INK, width=1)
    for ring in _rings(state):
        draw.line(grid.pixels(ring), fill=INK, width=3)
    box = grid.metric(shapely.box(*AREAS["imphal"].bounds)).exterior
    draw.line(grid.pixels(box), fill=IMPHAL_BOX, width=3)


def _draw_labels(draw: ImageDraw.ImageDraw, grid: Grid, outlines: dict, state) -> None:
    font = ImageFont.load_default(size=22)
    small = ImageFont.load_default(size=16)
    halo = {"stroke_width": 2, "stroke_fill": PAPER}
    for town in outlines["towns"]:
        point = shapely.Point(grid.to_metric.transform(town["lon"], town["lat"]))
        if not state.contains(point):
            continue
        px, py = grid.pixels(point)[0]
        draw.rectangle((px - 3, py - 3, px + 3, py + 3), fill=INK, outline=PAPER)
        draw.text((px + 7, py - 9), town["name"], font=small, fill=INK, **halo)
    box = grid.metric(shapely.box(*AREAS["imphal"].bounds)).exterior
    bx, by = grid.pixels(box)[0]
    draw.text((bx, by + 6), "today's map", font=small, fill=IMPHAL_BOX, **halo)
    title = f"{STATE_NAME}, top-down check, {METERS_PER_PIXEL:.0f} m/px"
    draw.text((16, 12), title, font=font, fill=INK, **halo)
    credit = "ESA WorldCover 2021 land cover, Copernicus GLO-30 DEM shading, OSM outlines"
    draw.text((16, 40), credit, font=small, fill=INK, **halo)


def _report(cover: np.ndarray, dem: np.ndarray, inside: np.ndarray) -> None:
    # Cells past the edge of the source rasters are 0, as is the DEM's last row and
    # column after merging; nowhere in Manipur is at sea level, so leave them out.
    covered = inside & (cover > 0) & (dem > 0)
    print(f"elevation inside the state: {dem[covered].min():.0f} to {dem[covered].max():.0f} m")
    codes, counts = np.unique(cover[covered], return_counts=True)
    shares: dict[str, float] = {}
    for code, count in zip(codes, counts, strict=True):
        name = WORLDCOVER_CLASSES.get(int(code), "none")
        shares[name] = shares.get(name, 0) + count / covered.sum()
    ranked = sorted(shares.items(), key=lambda item: -item[1])
    print("land cover: " + ", ".join(f"{name} {share:.1%}" for name, share in ranked))


def overview(area: Area) -> None:
    directory = raw_dir(area)
    directory.mkdir(parents=True, exist_ok=True)
    records = fetch_rasters(area)
    outlines_path, outlines_url = fetch_outlines(area)
    sources = directory / "SOURCES.txt"
    if not sources.exists():
        today = dt.date.today().isoformat()
        with sources.open("w") as output:
            output.write(f"{today}\tOpenStreetMap\t{outlines_url}\t{outlines_path.name}\n")
            for name, url, filename in records:
                output.write(f"{today}\t{name}\t{url}\t{filename}\n")

    grid = Grid.covering(area)
    cover = grid.resample(directory / "worldcover_2021_overview.tif", Resampling.mode, "uint8")
    dem = grid.resample(directory / "dem_glo30.tif", Resampling.bilinear, "float32")
    colors = np.zeros((256, 3), dtype=float)
    colors[:] = PAPER
    for code, name in WORLDCOVER_CLASSES.items():
        colors[code] = _rgb(name)
    image = colors[cover] * _hillshade(dem)[..., None]

    outlines = json.loads(outlines_path.read_text())
    state_wkt = next(
        b["wkt"] for b in outlines["boundaries"] if b["level"] == 4 and b["name"] == STATE_NAME
    )
    state = grid.metric(shapely.from_wkt(state_wkt))
    inside = geometry_mask([state], (grid.height, grid.width), grid.transform, invert=True)
    image[~inside] = image[~inside] * (1 - OUTSIDE_FADE) + np.array(PAPER) * OUTSIDE_FADE
    picture = Image.fromarray(np.clip(image, 0, 255).astype("uint8"))
    draw = ImageDraw.Draw(picture)
    _draw_outlines(draw, grid, outlines, state)
    _draw_labels(draw, grid, outlines, state)

    target = Path("out") / area.name
    target.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    output = target / f"{stamp}_overview.png"
    picture.save(output)
    print(f"overview: {output} ({grid.width} x {grid.height} px)")
    _report(cover, dem, inside)
