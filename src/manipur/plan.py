"""Throwaway top-down view, to confirm the raw data is right before projection."""

import datetime as dt
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from PIL import Image, ImageDraw

from manipur.areas import Area
from manipur.fetch import raw_dir
from manipur.osm import load_features

METRIC_CRS = 32646
MARGIN_PX = 20


def overlap_stats(osm: gpd.GeoDataFrame, open_buildings: gpd.GeoDataFrame) -> dict[str, float]:
    """Report how many Open Buildings polygons overlap an OSM building."""
    tree = shapely.STRtree(osm.geometry.values)
    ob_index, _ = tree.query(open_buildings.geometry.values, predicate="intersects")
    overlapping = len(set(ob_index.tolist()))
    return {
        "osm": len(osm),
        "open_buildings": len(open_buildings),
        "overlapping": overlapping,
        "fraction": overlapping / len(open_buildings) if len(open_buildings) else 0.0,
    }


def load_open_buildings(area: Area) -> gpd.GeoDataFrame:
    table = pd.read_csv(raw_dir(area) / "open_buildings_v3.csv")
    geometry = gpd.GeoSeries.from_wkt(table.pop("geometry"), crs=4326)
    return gpd.GeoDataFrame(table, geometry=geometry)


def plan(area: Area) -> None:
    features = load_features(raw_dir(area) / "osm.json")
    open_buildings = load_open_buildings(area).to_crs(METRIC_CRS)
    frame = gpd.GeoDataFrame(
        {
            "building": [f.tags.get("building") for f in features],
            "highway": [f.tags.get("highway") for f in features],
            "waterway": [f.tags.get("waterway") for f in features],
            "natural": [f.tags.get("natural") for f in features],
        },
        geometry=[f.geometry for f in features],
        crs=4326,
    ).to_crs(METRIC_CRS)
    is_polygon = frame.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    osm_buildings = frame[frame.building.notna() & is_polygon]

    patch = gpd.GeoSeries([shapely.box(*area.bounds)], crs=4326).to_crs(METRIC_CRS)
    left, bottom, right, top = patch.total_bounds
    width = int(right - left) + 2 * MARGIN_PX
    height = int(top - bottom) + 2 * MARGIN_PX
    image = Image.new("RGB", (width, height), "#f4f1ea")
    draw = ImageDraw.Draw(image)

    def pixels(geometry) -> list[tuple[float, float]]:
        return [(x - left + MARGIN_PX, top - y + MARGIN_PX) for x, y in geometry.coords]

    def rings(frame_part: gpd.GeoDataFrame):
        for geometry in frame_part.geometry.explode(index_parts=False):
            yield geometry.exterior

    water = frame[(frame.natural == "water") & is_polygon]
    for ring in rings(water):
        draw.polygon(pixels(ring), fill="#8ec5e8")
    for line in frame[frame.waterway.notna() & ~is_polygon].geometry:
        draw.line(pixels(line), fill="#3f8fc4", width=4)
    for line in frame[frame.highway.notna() & ~is_polygon].geometry:
        draw.line(pixels(line), fill="#333333", width=3)
    for ring in rings(open_buildings):
        draw.polygon(pixels(ring), fill="#f2a65a")
    for ring in rings(osm_buildings):
        draw.polygon(pixels(ring), fill="#c0392b")

    target = Path("out") / area.name
    target.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    output = target / f"{stamp}_plan.png"
    image.save(output)

    stats = overlap_stats(osm_buildings, open_buildings)
    print(f"plan: {output}")
    print(
        f"OSM buildings: {stats['osm']}; Open Buildings: {stats['open_buildings']}; "
        f"overlapping an OSM building: {stats['overlapping']} ({stats['fraction']:.1%})"
    )
