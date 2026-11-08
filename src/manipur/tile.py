"""Stage 4: join the frames into a Deep Zoom pyramid and write the search index."""

import json
import shutil
from pathlib import Path

import geopandas as gpd
import pyvips
from pyproj import Transformer

from manipur.areas import Area
from manipur.detail import LANDMARKS_PATH, PROJECTION, SPRITE_DIR, frames_dir, manifest_path
from manipur.prepare import METRIC_CRS, derived_path

TILE_PX = 512
CEMETERY_CREDIT = Path("assets/cemetery.json")
AREA_KINDS = {"city", "suburb", "town"}
LOCALITY_KINDS = {"village", "neighbourhood", "locality", "quarter", "hamlet"}
NOTABLE_KINDS = {"landmark", "university"}
NOTABLE_NAMES = {"Kangla Palace", "Imphal War Cemetery", "Imphal Indian War Cemetary"}
TILE_SUFFIX = ".webp[lossless=true,effort=4]"


def tiles_dir(area: Area) -> Path:
    return Path("out") / area.name / "tiles"


def search_index(area: Area, x_offset: float, y_offset: float) -> list[dict]:
    """Return OSM names with their canvas positions, one entry per name and place."""
    a, b, d, e = PROJECTION.matrix
    pois = gpd.read_file(derived_path(area), layer="pois")
    landmarks = landmark_positions(area)
    entries = {}
    for row in pois.itertuples():
        x, y = row.geometry.x, row.geometry.y
        px = round(a * x + b * y + x_offset)
        py = round(d * x + e * y + y_offset)
        if row.name in landmarks:
            continue
        key = (row.name, px // 200, py // 200)
        kind = row.kind or ""
        entries[key] = {
            "name": row.name,
            "kind": kind,
            "x": px,
            "y": py,
            "tier": _tier(row.name, kind),
        }
    for name, (x, y) in landmarks.items():
        px = round(a * x + b * y + x_offset)
        py = round(d * x + e * y + y_offset)
        entries[(name, "landmark")] = {
            "name": name,
            "kind": "landmark",
            "x": px,
            "y": py,
            "tier": 2,
        }
    return sorted(entries.values(), key=lambda entry: (entry["name"], entry["x"]))


def _tier(name: str, kind: str) -> int:
    """Return the zoom tier for a label: 1 shows first, 3 only when zoomed well in."""
    if kind in AREA_KINDS:
        return 1
    if kind in LOCALITY_KINDS or kind in NOTABLE_KINDS or name in NOTABLE_NAMES:
        return 2
    return 3


def landmark_positions(area: Area) -> dict[str, tuple[float, float]]:
    """Return metric positions for every labeled landmark."""
    to_metric = Transformer.from_crs(4326, METRIC_CRS, always_xy=True)
    positions = {}
    for path in sorted(SPRITE_DIR.glob("*.json")):
        sidecar = json.loads(path.read_text())
        if "label" in sidecar:
            placed = sidecar["placed_at"]
            positions[sidecar["label"]] = to_metric.transform(placed["lon"], placed["lat"])
    buildings = gpd.read_file(derived_path(area), layer="buildings", columns=["building_id"])
    centers = buildings.set_index("building_id").geometry.centroid
    for entry in json.loads(LANDMARKS_PATH.read_text()):
        if "label" in entry and entry["replaces"][0] in centers.index:
            center = centers.loc[entry["replaces"][0]]
            positions[entry["label"]] = (center.x, center.y)
    return positions


def landmark_credits() -> list[dict]:
    """Return one credit per landmark, with the photographs it was drawn from."""
    sources = [json.loads(path.read_text()) for path in sorted(SPRITE_DIR.glob("*.json"))]
    sources += json.loads(LANDMARKS_PATH.read_text())
    sources.append(json.loads(CEMETERY_CREDIT.read_text()))
    credits = {}
    for source in sources:
        name = source.get("credit") or source.get("label") or source["name"]
        credits.setdefault(name, {"name": name, "references": source["references"]})
    return sorted(credits.values(), key=lambda credit: credit["name"])


def tile(area: Area) -> None:
    manifest = json.loads(manifest_path(area).read_text())
    columns, rows = manifest["columns"], manifest["rows"]
    paths = [
        frames_dir(area) / f"{row:03d}_{column:03d}.png"
        for row in range(rows)
        for column in range(columns)
    ]
    images = [pyvips.Image.new_from_file(str(path), access="sequential") for path in paths]
    joined = pyvips.Image.arrayjoin(images, across=columns)

    target = tiles_dir(area)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    joined.dzsave(
        str(target / area.name),
        tile_size=TILE_PX,
        overlap=0,
        suffix=TILE_SUFFIX,
        depth="onepixel",
    )

    entries = search_index(area, manifest["x_offset"], manifest["y_offset"])
    (target / "search.json").write_text(json.dumps(entries, ensure_ascii=False))
    (target / "credits.json").write_text(json.dumps(landmark_credits(), ensure_ascii=False))
    shutil.copy(manifest_path(area), target / "manifest.json")
    print(f"{target}: {joined.width} x {joined.height}, {len(entries)} search entries")
