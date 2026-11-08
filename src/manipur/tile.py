"""Stage 4: join the frames into a Deep Zoom pyramid and write the search index."""

import json
import shutil
from pathlib import Path

import geopandas as gpd
import pyvips

from manipur.areas import Area
from manipur.detail import PROJECTION, frames_dir, manifest_path
from manipur.prepare import derived_path

TILE_PX = 512
TILE_SUFFIX = ".webp[lossless=true,effort=4]"


def tiles_dir(area: Area) -> Path:
    return Path("out") / area.name / "tiles"


def search_index(area: Area, x_offset: float, y_offset: float) -> list[dict]:
    """Return OSM names with their canvas positions, one entry per name and place."""
    a, b, d, e = PROJECTION.matrix
    pois = gpd.read_file(derived_path(area), layer="pois")
    entries = {}
    for row in pois.itertuples():
        x, y = row.geometry.x, row.geometry.y
        px = round(a * x + b * y + x_offset)
        py = round(d * x + e * y + y_offset)
        key = (row.name, px // 200, py // 200)
        entries[key] = {"name": row.name, "kind": row.kind or "", "x": px, "y": py}
    return sorted(entries.values(), key=lambda entry: (entry["name"], entry["x"]))


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
    shutil.copy(manifest_path(area), target / "manifest.json")
    print(f"{target}: {joined.width} x {joined.height}, {len(entries)} search entries")
