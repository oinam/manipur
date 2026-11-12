import geopandas as gpd
from shapely.geometry import LineString

from manipur.areas import Area
from manipur.detail import PROJECTION
from manipur.prepare import METRIC_CRS, derived_path
from manipur.tile import flow_lines, pyramid_version


def test_pyramid_version_follows_the_frame_bytes(tmp_path):
    frame = tmp_path / "000_000.png"
    frame.write_bytes(b"first")
    first = pyramid_version([frame], 1)
    assert pyramid_version([frame], 1) == first
    assert pyramid_version([frame], 2) != first
    frame.write_bytes(b"second")
    assert pyramid_version([frame], 1) != first


def test_flow_lines_keep_the_drawn_direction(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    area = Area("test", 0.0, 0.0, 1.0, 1.0)
    path = derived_path(area)
    path.parent.mkdir(parents=True)
    river = LineString([(0.0, 0.0), (100.0, 0.0)])
    frame = gpd.GeoDataFrame(
        {"waterway": ["river"], "width_m": [30.0], "name": ["Test"]},
        geometry=[river],
        crs=METRIC_CRS,
    )
    frame.to_file(path, layer="waterways", driver="GPKG")

    [line] = flow_lines(area, 10.0, 20.0)

    a, _, d, _ = PROJECTION.matrix
    assert line["width"] == 30
    assert line["points"] == [[10, 20], [round(a * 100 + 10), round(d * 100 + 20)]]
    assert line["name"] == "Test"


def test_flow_lines_name_rivers_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    area = Area("test", 0.0, 0.0, 1.0, 1.0)
    path = derived_path(area)
    path.parent.mkdir(parents=True)
    frame = gpd.GeoDataFrame(
        {"waterway": ["stream", "river"], "width_m": [4.0, 30.0], "name": ["Brook", None]},
        geometry=[LineString([(0.0, 0.0), (50.0, 0.0)]), LineString([(0.0, 9.0), (50.0, 9.0)])],
        crs=METRIC_CRS,
    )
    frame.to_file(path, layer="waterways", driver="GPKG")

    assert [line.get("name") for line in flow_lines(area, 0.0, 0.0)] == [None, None]
