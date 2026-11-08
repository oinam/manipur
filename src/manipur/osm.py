"""Turn the raw Overpass response into shapely geometries with tags."""

import json
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union

AREA_KEYS = ("building", "landuse", "leisure", "amenity", "natural", "water", "aeroway")
LINEAR_NATURAL = {"tree_row", "cliff", "ridge", "coastline"}


@dataclass(frozen=True)
class Feature:
    osm_type: str
    osm_id: int
    tags: dict[str, str]
    geometry: BaseGeometry


def _coords(geometry: list[dict | None]) -> list[tuple[float, float]]:
    return [(point["lon"], point["lat"]) for point in geometry if point]


def _is_area(tags: dict[str, str]) -> bool:
    if tags.get("area") == "no" or tags.get("natural") in LINEAR_NATURAL:
        return False
    if tags.get("area") == "yes" or tags.get("waterway") == "riverbank":
        return True
    return any(key in tags for key in AREA_KEYS) and "highway" not in tags


def _way_geometry(element: dict) -> BaseGeometry | None:
    coords = _coords(element.get("geometry", []))
    if len(coords) < 2:
        return None
    if len(coords) >= 4 and coords[0] == coords[-1] and _is_area(element.get("tags", {})):
        polygon = Polygon(coords)
        return polygon if polygon.is_valid else polygon.buffer(0)
    return LineString(coords)


def _multipolygon_geometry(element: dict) -> BaseGeometry | None:
    rings: dict[str, list[LineString]] = {"outer": [], "inner": []}
    for member in element.get("members", []):
        coords = _coords(member.get("geometry", []))
        if member.get("type") == "way" and len(coords) >= 2:
            rings["inner" if member.get("role") == "inner" else "outer"].append(LineString(coords))
    outer = unary_union(list(polygonize(rings["outer"])))
    if outer.is_empty:
        return None
    inner = list(polygonize(rings["inner"]))
    return outer.difference(unary_union(inner)) if inner else outer


def load_features(path: Path) -> list[Feature]:
    """Parse osm.json, keeping nodes, ways, and multipolygon relations."""
    features = []
    for element in json.loads(path.read_text())["elements"]:
        tags = element.get("tags", {})
        kind = element["type"]
        if kind == "node":
            geometry = Point(element["lon"], element["lat"])
        elif kind == "way":
            geometry = _way_geometry(element)
        elif tags.get("type") == "multipolygon":
            geometry = _multipolygon_geometry(element)
        else:
            geometry = None
        if geometry is not None and not geometry.is_empty:
            features.append(Feature(kind, element["id"], tags, geometry))
    return features
