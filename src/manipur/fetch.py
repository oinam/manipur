"""Stage 1: download the sources for an area into data/raw/<area>/."""

import csv
import datetime as dt
import gzip
import io
import json
import time
from pathlib import Path

import rasterio
import osmium
import requests
import s2sphere
from pyproj import Transformer
from rasterio.merge import merge
from rasterio.windows import from_bounds

from manipur.areas import Area

USER_AGENT = "manipur-map/0.1 (https://github.com/oinam/manipur)"
OVERPASS_ENDPOINTS = (
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
OPEN_BUILDINGS_URL = (
    "https://storage.googleapis.com/open-buildings-data/v3/"
    "polygons_s2_level_6_gzip_no_header/{token}_buildings.csv.gz"
)
OPEN_BUILDINGS_COLUMNS = (
    "latitude",
    "longitude",
    "area_in_meters",
    "confidence",
    "geometry",
    "full_plus_code",
)
WORLDCOVER_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
)
GEOFABRIK_URL = "https://download.geofabrik.de/{extract}-latest.osm.pbf"
TEMPORAL_BUCKET = "https://storage.googleapis.com/open-buildings-temporal-data"
TEMPORAL_MANIFEST = TEMPORAL_BUCKET + "/v1/manifests/{token}_EPSG_{epsg}_{year}_06_30.json"
TEMPORAL_YEAR = 2023
TEMPORAL_HEIGHT_BAND = 2
UTM_46N = 32646
OVERPASS_TAGS = (
    '["highway"]',
    '["railway"]',
    '["aeroway"]',
    '["waterway"]',
    '["water"]',
    '["landuse"]',
    '["leisure"]',
    '["natural"]',
    '["amenity"]',
    '["building"]',
    '["name"]',
)
OSM_KEYS = tuple(tag.strip('[]"') for tag in OVERPASS_TAGS)


def raw_dir(area: Area) -> Path:
    return Path("data/raw") / area.name


def overpass_query(area: Area) -> str:
    bbox = f"{area.south},{area.west},{area.north},{area.east}"
    # Relations are limited to multipolygons: named routes span the continent.
    selectors = "".join(
        f'nw{tag}({bbox});rel["type"="multipolygon"]{tag}({bbox});' for tag in OVERPASS_TAGS
    )
    return (
        "[out:json][timeout:180];"
        f"({selectors})->.features;"
        ".features out geom;"
        f'rel["boundary"="administrative"]({bbox});'
        f"out geom({bbox});"
    )


def fetch_osm(area: Area, attempts: int = 8) -> tuple[Path, str]:
    """Download OSM features, rotating endpoints with exponential backoff."""
    target = raw_dir(area) / "osm.json"
    query = overpass_query(area)
    headers = {"User-Agent": USER_AGENT}
    delay = 15
    for attempt in range(attempts):
        endpoint = OVERPASS_ENDPOINTS[attempt % len(OVERPASS_ENDPOINTS)]
        print(f"osm: attempt {attempt + 1} via {endpoint}")
        try:
            response = requests.post(endpoint, data={"data": query}, headers=headers, timeout=240)
            if response.ok:
                payload = response.json()
                if payload.get("elements"):
                    target.write_text(json.dumps(payload))
                    print(f"osm: {len(payload['elements'])} elements")
                    return target, endpoint
                print("osm: empty response")
            else:
                print(f"osm: HTTP {response.status_code}")
        except (requests.RequestException, json.JSONDecodeError) as error:
            print(f"osm: {type(error).__name__}: {error}")
        time.sleep(delay)
        delay = min(delay * 2, 240)
    raise SystemExit("osm: every Overpass endpoint failed")


class _RelationMembers(osmium.SimpleHandler):
    """Collect the ways that make up multipolygons we keep."""

    def __init__(self) -> None:
        super().__init__()
        self.ways: set[int] = set()

    def relation(self, relation) -> None:
        tags = dict(relation.tags)
        if tags.get("type") == "multipolygon" and _is_kept(tags):
            self.ways.update(member.ref for member in relation.members if member.type == "w")


class _AreaExtract(osmium.SimpleHandler):
    """Write kept features in the same shape Overpass returns."""

    def __init__(self, area: Area, member_ways: set[int]) -> None:
        super().__init__()
        self.area = area
        self.member_ways = member_ways
        self.member_points: dict[int, list[dict[str, float]]] = {}
        self.elements: list[dict] = []

    def _inside(self, lat: float, lon: float) -> bool:
        west, south, east, north = self.area.bounds
        return south <= lat <= north and west <= lon <= east

    def node(self, node) -> None:
        if len(node.tags) and node.location.valid():
            lat, lon = node.location.lat, node.location.lon
            tags = dict(node.tags)
            if self._inside(lat, lon) and _is_kept(tags):
                self.elements.append(
                    {"type": "node", "id": node.id, "lat": lat, "lon": lon, "tags": tags}
                )

    def way(self, way) -> None:
        tags = dict(way.tags)
        wanted = way.id in self.member_ways
        if not wanted and not _is_kept(tags):
            return
        points = [
            {"lat": node.location.lat, "lon": node.location.lon}
            for node in way.nodes
            if node.location.valid()
        ]
        if wanted:
            self.member_points[way.id] = points
        if _is_kept(tags) and any(self._inside(p["lat"], p["lon"]) for p in points):
            self.elements.append({"type": "way", "id": way.id, "tags": tags, "geometry": points})

    def relation(self, relation) -> None:
        tags = dict(relation.tags)
        if tags.get("type") != "multipolygon" or not _is_kept(tags):
            return
        members = [
            {"type": "way", "role": member.role, "geometry": self.member_points[member.ref]}
            for member in relation.members
            if member.type == "w" and member.ref in self.member_points
        ]
        if any(self._inside(p["lat"], p["lon"]) for m in members for p in m["geometry"]):
            self.elements.append(
                {"type": "relation", "id": relation.id, "tags": tags, "members": members}
            )


def _is_kept(tags: dict[str, str]) -> bool:
    return any(key in tags for key in OSM_KEYS)


def fetch_osm_extract(area: Area) -> tuple[Path, str]:
    """Cut the area out of a cached Geofabrik extract."""
    url = GEOFABRIK_URL.format(extract=area.osm_extract)
    cache = Path("data/raw/_geofabrik") / url.rsplit("/", 1)[1]
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        print(f"osm: downloading {url}")
        partial = cache.with_suffix(".part")
        with requests.get(url, stream=True, timeout=120) as response:
            response.raise_for_status()
            with partial.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    output.write(chunk)
        partial.rename(cache)
    members = _RelationMembers()
    members.apply_file(str(cache))
    extract = _AreaExtract(area, members.ways)
    extract.apply_file(str(cache), locations=True, idx="flex_mem")
    target = raw_dir(area) / "osm.json"
    target.write_text(json.dumps({"elements": extract.elements}))
    print(f"osm: {len(extract.elements)} elements")
    reader = osmium.io.Reader(str(cache), osmium.osm.osm_entity_bits.NOTHING)
    stamp = reader.header().get("osmosis_replication_timestamp")
    reader.close()
    return target, f"{url} (data to {stamp})"


def s2_tokens(area: Area, level: int = 6) -> list[str]:
    """Return the S2 cell tokens covering the area at the given level."""
    coverer = s2sphere.RegionCoverer()
    coverer.min_level = level
    coverer.max_level = level
    rect = s2sphere.LatLngRect.from_point_pair(
        s2sphere.LatLng.from_degrees(area.south, area.west),
        s2sphere.LatLng.from_degrees(area.north, area.east),
    )
    return sorted(cell.to_token() for cell in coverer.get_covering(rect))


def fetch_open_buildings(area: Area) -> tuple[Path, list[str]]:
    """Stream the covering cells, keeping only rows whose center is in the area."""
    target = raw_dir(area) / "open_buildings_v3.csv"
    urls = [OPEN_BUILDINGS_URL.format(token=token) for token in s2_tokens(area)]
    west, south, east, north = area.bounds
    kept = 0
    with target.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(OPEN_BUILDINGS_COLUMNS)
        for url in urls:
            print(f"open buildings: streaming {url}")
            with requests.get(url, stream=True, timeout=120) as response:
                response.raise_for_status()
                response.raw.decode_content = False
                with gzip.GzipFile(fileobj=response.raw) as unzipped:
                    for row in csv.reader(io.TextIOWrapper(unzipped, encoding="utf-8")):
                        latitude, longitude = float(row[0]), float(row[1])
                        if south <= latitude <= north and west <= longitude <= east:
                            writer.writerow(row)
                            kept += 1
    print(f"open buildings: kept {kept} polygons")
    return target, urls


def fetch_worldcover(area: Area) -> tuple[Path, str]:
    """Read the area's window from the WorldCover cloud-optimized GeoTIFF."""
    target = raw_dir(area) / "worldcover_2021.tif"
    # Tiles are 3 degrees square and named by their southwest corner.
    lat = int(area.south // 3 * 3)
    lon = int(area.west // 3 * 3)
    url = WORLDCOVER_URL.format(tile=f"N{lat:02d}E{lon:03d}")
    with rasterio.open(url) as source:
        window = (
            from_bounds(*area.bounds, transform=source.transform).round_offsets().round_lengths()
        )
        data = source.read(1, window=window)
        profile = source.profile | {
            "driver": "GTiff",
            "height": data.shape[0],
            "width": data.shape[1],
            "transform": source.window_transform(window),
            "compress": "deflate",
        }
        for key in ("blockxsize", "blockysize", "tiled", "interleave"):
            profile.pop(key, None)
    with rasterio.open(target, "w", **profile) as sink:
        sink.write(data, 1)
    print(f"worldcover: {data.shape[1]} x {data.shape[0]} cells")
    return target, url


def fetch_heights(area: Area) -> tuple[Path, list[str]]:
    """Mosaic the area's window of the 2.5D Temporal building height band."""
    target = raw_dir(area) / f"temporal_height_{TEMPORAL_YEAR}.tif"
    lon, lat = area.center
    cell = s2sphere.CellId.from_lat_lng(s2sphere.LatLng.from_degrees(lat, lon))
    manifest_url = TEMPORAL_MANIFEST.format(
        token=cell.parent(2).to_token(), epsg=UTM_46N, year=TEMPORAL_YEAR
    )
    response = requests.get(manifest_url, timeout=120)
    response.raise_for_status()
    manifest = response.json()
    prefix = manifest["uriPrefix"].replace("gs://", "https://storage.googleapis.com/")

    to_utm = Transformer.from_crs(4326, UTM_46N, always_xy=True)
    xs, ys = to_utm.transform(
        [area.west, area.west, area.east, area.east],
        [area.south, area.north, area.south, area.north],
    )
    left, bottom, right, top = min(xs), min(ys), max(xs), max(ys)

    urls = []
    for tileset in manifest["tilesets"]:
        for source in tileset["sources"]:
            affine = source["affineTransform"]
            size = source["dimensions"]
            tile_left = affine["translateX"]
            tile_top = affine["translateY"]
            tile_right = tile_left + affine["scaleX"] * size["width"]
            tile_bottom = tile_top + affine["scaleY"] * size["height"]
            if tile_left < right and tile_right > left and tile_bottom < top and tile_top > bottom:
                urls.append(f"{prefix}{source['uris'][0]}")
    if not urls:
        raise SystemExit("heights: no 2.5D Temporal tile covers this area")

    datasets = [rasterio.open(url) for url in urls]
    try:
        mosaic, transform = merge(
            datasets,
            bounds=(left, bottom, right, top),
            res=area.height_res_m,
            indexes=[TEMPORAL_HEIGHT_BAND],
        )
        profile = {
            "driver": "GTiff",
            "height": mosaic.shape[1],
            "width": mosaic.shape[2],
            "count": 1,
            "dtype": mosaic.dtype,
            "crs": datasets[0].crs,
            "transform": transform,
            "nodata": datasets[0].nodata,
            "compress": "deflate",
        }
    finally:
        for dataset in datasets:
            dataset.close()
    with rasterio.open(target, "w", **profile) as sink:
        sink.write(mosaic[0], 1)
    print(f"heights: {mosaic.shape[2]} x {mosaic.shape[1]} cells from {len(urls)} tile(s)")
    return target, urls


def fetch(area: Area) -> None:
    directory = raw_dir(area)
    directory.mkdir(parents=True, exist_ok=True)
    osm_path, endpoint = fetch_osm_extract(area) if area.osm_extract else fetch_osm(area)
    buildings_path, building_urls = fetch_open_buildings(area)
    cover_path, cover_url = fetch_worldcover(area)
    heights_path, height_urls = fetch_heights(area)
    today = dt.date.today().isoformat()
    with (directory / "SOURCES.txt").open("a") as sources:
        sources.write(f"{today}\tOpenStreetMap\t{endpoint}\t{osm_path.name}\n")
        for url in building_urls:
            sources.write(f"{today}\tGoogle Open Buildings v3\t{url}\t{buildings_path.name}\n")
        sources.write(f"{today}\tESA WorldCover 2021 v200\t{cover_url}\t{cover_path.name}\n")
        for url in height_urls:
            sources.write(f"{today}\tOpen Buildings 2.5D Temporal\t{url}\t{heights_path.name}\n")
    print(f"Recorded in {directory / 'SOURCES.txt'}. Update docs/DATA.md if a source changed.")
