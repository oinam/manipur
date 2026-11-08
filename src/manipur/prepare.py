"""Stage 2: clip, reproject, merge footprints, attach heights, classify ground."""

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio.features import geometry_mask, shapes
from rasterio.windows import Window, from_bounds
from rasterio.windows import transform as window_transform

from manipur.areas import Area
from manipur.fetch import raw_dir
from manipur.osm import Feature, load_features
from manipur.plan import load_open_buildings

METRIC_CRS = 32646
MIN_CONFIDENCE = 0.70
DEDUPE_IOU = 0.30
DEDUPE_COVERED = 0.50
WATER_COVERED = 0.50
MIN_HEIGHT_M = 2.5
MAX_HEIGHT_M = 80.0
HEIGHT_PERCENTILE = 75
METERS_PER_LEVEL = 3.2

ROAD_WIDTHS_M = {
    "trunk": 14.0,
    "primary": 12.0,
    "secondary": 10.0,
    "tertiary": 8.0,
    "unclassified": 6.0,
    "residential": 5.0,
    "living_street": 5.0,
    "service": 3.5,
    "track": 3.0,
    "pedestrian": 3.0,
    "path": 1.5,
    "footway": 1.5,
    "cycleway": 1.5,
    "steps": 1.5,
}
WATERWAY_WIDTHS_M = {"river": 30.0, "canal": 8.0, "stream": 4.0, "drain": 2.0, "ditch": 2.0}
WORLDCOVER_CLASSES = {
    10: "tree",
    20: "shrub",
    30: "grass",
    40: "crop",
    50: "built",
    60: "bare",
    70: "bare",
    80: "water",
    90: "wetland",
    95: "wetland",
    100: "grass",
}


def derived_path(area: Area) -> Path:
    return Path("data/derived") / f"{area.name}.gpkg"


def stats_path(area: Area) -> Path:
    return Path("data/derived") / f"{area.name}_stats.json"


def _to_metric(rows: list[dict], geometries: list) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(rows, geometry=geometries, crs=4326).to_crs(METRIC_CRS)


def _is_polygon(geometry) -> bool:
    return geometry.geom_type in ("Polygon", "MultiPolygon")


def _is_line(geometry) -> bool:
    return geometry.geom_type in ("LineString", "MultiLineString")


def _parse_meters(value: str | None) -> float | None:
    """Read an OSM height or width tag, ignoring anything that is not plain meters."""
    if not value:
        return None
    try:
        return float(value.replace("m", "").strip())
    except ValueError:
        return None


def _osm_height(tags: dict[str, str]) -> float | None:
    height = _parse_meters(tags.get("height"))
    if height is not None:
        return height
    levels = _parse_meters(tags.get("building:levels"))
    return levels * METERS_PER_LEVEL if levels is not None else None


def osm_buildings(features: list[Feature]) -> gpd.GeoDataFrame:
    chosen = [f for f in features if "building" in f.tags and _is_polygon(f.geometry)]
    rows = [
        {
            "building_id": f"osm/{f.osm_type}/{f.osm_id}",
            "source": "osm",
            "confidence": 1.0,
            "name": f.tags.get("name"),
            "tagged_height": _osm_height(f.tags),
        }
        for f in chosen
    ]
    return _to_metric(rows, [f.geometry for f in chosen])


def roads(features: list[Feature]) -> gpd.GeoDataFrame:
    rows, geometries = [], []
    for feature in features:
        highway = feature.tags.get("highway", "").removesuffix("_link")
        if highway in ROAD_WIDTHS_M and _is_line(feature.geometry):
            rows.append(
                {
                    "road_class": highway,
                    "width_m": ROAD_WIDTHS_M[highway],
                    "name": feature.tags.get("name"),
                }
            )
            geometries.append(feature.geometry)
    return _to_metric(rows, geometries)


def waterways(features: list[Feature]) -> gpd.GeoDataFrame:
    rows, geometries = [], []
    for feature in features:
        kind = feature.tags.get("waterway")
        if kind in WATERWAY_WIDTHS_M and _is_line(feature.geometry):
            width = _parse_meters(feature.tags.get("width")) or WATERWAY_WIDTHS_M[kind]
            rows.append({"waterway": kind, "width_m": width, "name": feature.tags.get("name")})
            geometries.append(feature.geometry)
    return _to_metric(rows, geometries)


def water_polygons(features: list[Feature]) -> gpd.GeoDataFrame:
    chosen = [
        f
        for f in features
        if _is_polygon(f.geometry)
        and (
            f.tags.get("natural") == "water"
            or "water" in f.tags
            or f.tags.get("waterway") == "riverbank"
            or f.tags.get("landuse") in ("reservoir", "basin")
        )
    ]
    rows = [{"name": f.tags.get("name")} for f in chosen]
    return _to_metric(rows, [f.geometry for f in chosen])


def points_of_interest(features: list[Feature]) -> gpd.GeoDataFrame:
    chosen = [f for f in features if "name" in f.tags]
    rows = [
        {
            "name": f.tags["name"],
            "kind": f.tags.get("amenity") or f.tags.get("place") or f.tags.get("building") or "",
        }
        for f in chosen
    ]
    return _to_metric(rows, [f.geometry.representative_point() for f in chosen])


def duplicate_mask(
    open_buildings: gpd.GeoDataFrame, osm: gpd.GeoDataFrame
) -> tuple[np.ndarray, np.ndarray]:
    """Return (intersects any OSM building, duplicates an OSM building) for each polygon."""
    count = len(open_buildings)
    intersects = np.zeros(count, dtype=bool)
    duplicate = np.zeros(count, dtype=bool)
    if count == 0 or len(osm) == 0:
        return intersects, duplicate
    ob_geometries = open_buildings.geometry.values
    osm_geometries = osm.geometry.values
    ob_index, osm_index = shapely.STRtree(osm_geometries).query(
        ob_geometries, predicate="intersects"
    )
    intersects[ob_index] = True
    ob_part = ob_geometries[ob_index]
    osm_part = osm_geometries[osm_index]
    shared = shapely.area(shapely.intersection(ob_part, osm_part))
    ob_area = shapely.area(ob_part)
    iou = shared / (ob_area + shapely.area(osm_part) - shared)
    hits = (iou >= DEDUPE_IOU) | (shared / ob_area >= DEDUPE_COVERED)
    duplicate[ob_index[hits]] = True
    return intersects, duplicate


def on_water_mask(open_buildings: gpd.GeoDataFrame, water: shapely.Geometry) -> np.ndarray:
    """Flag polygons mostly on mapped water; anything drawn on water is a bug."""
    geometries = open_buildings.geometry.values
    covered = shapely.area(shapely.intersection(geometries, water)) / shapely.area(geometries)
    return covered >= WATER_COVERED


def sample_heights(buildings: gpd.GeoDataFrame, raster_path: Path) -> np.ndarray:
    """Return each footprint's upper-quartile raster height, or NaN if it has none."""
    with rasterio.open(raster_path) as dataset:
        data = dataset.read(1, masked=True).filled(np.nan).astype("float64")
        data[data <= 0] = np.nan
        transform = dataset.transform
        full = Window(0, 0, dataset.width, dataset.height)
    heights = np.full(len(buildings), np.nan)
    for index, geometry in enumerate(buildings.geometry.values):
        window = (
            from_bounds(*geometry.bounds, transform=transform)
            .round_offsets(op="floor")
            .round_lengths(op="ceil")
        )
        try:
            window = window.intersection(full)
        except rasterio.errors.WindowError:
            continue
        if window.width < 1 or window.height < 1:
            continue
        row, col = int(window.row_off), int(window.col_off)
        cells = data[row : row + int(window.height), col : col + int(window.width)]
        inside = ~geometry_mask(
            [geometry],
            out_shape=cells.shape,
            transform=window_transform(window, transform),
            all_touched=True,
        )
        values = cells[inside & np.isfinite(cells)]
        if values.size:
            heights[index] = float(np.percentile(values, HEIGHT_PERCENTILE))
    return heights


def assign_heights(buildings: gpd.GeoDataFrame, raster: np.ndarray) -> gpd.GeoDataFrame:
    """Prefer OSM tags, then the 2.5D raster, then a default from the footprint area."""
    result = buildings.copy()
    tagged = pd.to_numeric(result["tagged_height"], errors="coerce").to_numpy(dtype="float64")
    fallback = np.where(result.geometry.area < 120, 3.5, 6.5)
    heights = np.where(np.isfinite(tagged), tagged, np.where(np.isfinite(raster), raster, fallback))
    sources = np.where(
        np.isfinite(tagged), "osm_tag", np.where(np.isfinite(raster), "temporal_2023", "default")
    )
    result["height_m"] = np.clip(heights, MIN_HEIGHT_M, MAX_HEIGHT_M)
    result["height_source"] = sources
    return result.drop(columns="tagged_height")


def ground_polygons(area: Area, patch: shapely.Geometry) -> gpd.GeoDataFrame:
    with rasterio.open(raw_dir(area) / "worldcover_2021.tif") as dataset:
        data = dataset.read(1)
        cells = [
            (WORLDCOVER_CLASSES.get(int(value), "bare"), shapely.geometry.shape(shape))
            for shape, value in shapes(data, transform=dataset.transform)
        ]
        crs = dataset.crs
    frame = gpd.GeoDataFrame(
        {"ground": [c[0] for c in cells]}, geometry=[c[1] for c in cells], crs=crs
    ).to_crs(METRIC_CRS)
    dissolved = frame.dissolve(by="ground", as_index=False)
    dissolved["geometry"] = dissolved.geometry.buffer(0).intersection(patch)
    return dissolved[~dissolved.geometry.is_empty]


def prepare(area: Area) -> None:
    raw = raw_dir(area)
    features = load_features(raw / "osm.json")
    patch = gpd.GeoSeries([shapely.box(*area.bounds)], crs=4326).to_crs(METRIC_CRS).iloc[0]

    water = water_polygons(features)
    rivers = waterways(features)
    wet = shapely.union_all(
        [*water.geometry.values, *rivers.geometry.buffer(rivers.width_m / 2).values]
    )

    osm = osm_buildings(features)
    candidates = load_open_buildings(area).to_crs(METRIC_CRS).reset_index(drop=True)
    confident = candidates["confidence"].to_numpy() >= MIN_CONFIDENCE
    intersects_all, _ = duplicate_mask(candidates, osm)

    kept = candidates[confident].reset_index(drop=True)
    _, duplicate = duplicate_mask(kept, osm)
    on_water = on_water_mask(kept, wet)
    survivors = kept[~duplicate & ~on_water].copy()
    survivors["building_id"] = "ob/" + survivors["full_plus_code"].astype(str)
    survivors["source"] = "open_buildings"
    survivors["name"] = None
    survivors["tagged_height"] = np.nan

    columns = ["building_id", "source", "confidence", "name", "tagged_height", "geometry"]
    merged = gpd.GeoDataFrame(
        pd.concat([osm[columns], survivors[columns]], ignore_index=True), crs=METRIC_CRS
    )
    merged = merged[merged.geometry.centroid.within(patch)].sort_values("building_id")
    merged = merged.reset_index(drop=True)
    buildings = assign_heights(merged, sample_heights(merged, raw / "temporal_height_2023.tif"))
    buildings["area_m2"] = buildings.geometry.area

    layers = {
        "patch": gpd.GeoDataFrame({"area": [area.name]}, geometry=[patch], crs=METRIC_CRS),
        "ground": ground_polygons(area, patch),
        "water": water.assign(geometry=water.geometry.intersection(patch)),
        "waterways": rivers.assign(geometry=rivers.geometry.intersection(patch)),
        "roads": roads(features).pipe(lambda r: r.assign(geometry=r.geometry.intersection(patch))),
        "pois": points_of_interest(features).pipe(lambda p: p[p.geometry.within(patch)]),
        "buildings": buildings,
    }

    target = derived_path(area)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    for name, frame in layers.items():
        frame[~frame.geometry.is_empty].to_file(target, layer=name, driver="GPKG")

    areas = candidates.geometry.area.to_numpy()
    largest = np.sort(areas)[::-1][:5]
    height_counts = buildings["height_source"].value_counts().to_dict()
    stats = {
        "osm_buildings": len(osm),
        "open_buildings_total": len(candidates),
        "open_buildings_overlapping_osm": int(intersects_all.sum()),
        "open_buildings_overlapping_osm_fraction": float(intersects_all.mean()),
        "open_buildings_below_confidence": int((~confident).sum()),
        "open_buildings_duplicates_dropped": int(duplicate.sum()),
        "open_buildings_on_water_dropped": int((on_water & ~duplicate).sum()),
        "open_buildings_kept": len(survivors),
        "open_buildings_under_10m2": int((areas < 10).sum()),
        "open_buildings_largest_m2": [round(float(value), 1) for value in largest],
        "buildings_final": len(buildings),
        "height_sources": {str(key): int(value) for key, value in height_counts.items()},
        "height_percentiles_m": {
            str(p): round(float(np.percentile(buildings["height_m"], p)), 1)
            for p in (5, 25, 50, 75, 95, 100)
        },
    }
    stats_path(area).write_text(json.dumps(stats, indent=2) + "\n")
    print(f"prepare: {target}")
    print(json.dumps(stats, indent=2))
