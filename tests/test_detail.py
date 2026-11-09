import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import shapely
from PIL import Image

from manipur.areas import get_area
from manipur.detail import (
    DEFAULT_VIEW,
    FRAME_PX,
    LANDMARKS_PATH,
    SLOTS_32,
    STYLE_PAINTERS,
    TRANSPARENT,
    build_scene,
    detail_colors,
    frames_dir,
    manifest_path,
    render_detail,
    render_frame,
    view_projection,
)
from manipur.render import PROJECTION_B, Layers, centered_viewport


def sample_layers():
    patch = shapely.box(0, 0, 300, 300)
    empty = gpd.GeoDataFrame({"width_m": [], "road_class": []}, geometry=[], crs=32646)
    ground = gpd.GeoDataFrame({"ground": ["tree"]}, geometry=[patch], crs=32646)
    water = gpd.GeoDataFrame(geometry=[shapely.box(10, 10, 60, 60)], crs=32646)
    buildings = gpd.GeoDataFrame(
        {"building_id": ["a", "b"], "height_m": [5.0, 14.0]},
        geometry=[shapely.box(120, 120, 134, 130), shapely.box(170, 100, 200, 130)],
        crs=32646,
    )
    return Layers(patch, ground, water, empty, empty, buildings)


def test_detail_palette_stays_within_the_limit():
    colors = detail_colors()
    assert set(colors) == set(SLOTS_32)
    assert len(SLOTS_32) <= 32
    assert sorted(SLOTS_32.values()) == list(range(len(SLOTS_32)))


def test_detail_render_is_deterministic_and_grows_trees():
    layers = sample_layers()
    view = centered_viewport(PROJECTION_B, 150, 150, 600, 600)
    scene = build_scene(layers)
    first = render_detail(scene, view)
    assert np.array_equal(first, render_detail(scene, view))
    painted = set(np.unique(first).tolist())
    assert {SLOTS_32["canopy_light"], SLOTS_32["water"], SLOTS_32["wall_lit"]} <= painted


@pytest.mark.parametrize("path", sorted(Path("assets/sprites").glob("*.png")))
def test_landmark_sprites_use_only_palette_slots_and_transparency(path):
    values = set(np.unique(np.asarray(Image.open(path))).tolist())
    assert TRANSPARENT in values
    assert values - {TRANSPARENT} <= set(SLOTS_32.values())


def test_every_landmark_style_has_a_painter_and_a_reference():
    for entry in json.loads(LANDMARKS_PATH.read_text()):
        assert entry["style"] in STYLE_PAINTERS
        assert entry["replaces"]
        assert entry["references"]


def test_adjacent_frames_join_without_a_seam():
    scene = build_scene(sample_layers())
    width = 2 * FRAME_PX
    canvas = centered_viewport(PROJECTION_B, 150, 150, width, FRAME_PX)
    joined = np.hstack([render_frame(scene, canvas, 0, 0), render_frame(scene, canvas, 1, 0)])
    assert np.array_equal(joined, render_detail(scene, canvas))


def test_default_view_keeps_its_paths():
    area = get_area("imphal")
    assert frames_dir(area).name == "frames"
    assert frames_dir(area, "sw").name == "frames-sw"
    assert manifest_path(area).name == "manifest.json"
    assert manifest_path(area, "ne").name == "manifest-ne.json"


def test_views_are_quarter_turns_of_the_chosen_projection():
    assert view_projection(DEFAULT_VIEW) == PROJECTION_B
    a, b, _, _ = view_projection("nw").matrix
    next_a, next_b, _, _ = view_projection("sw").matrix
    assert (round(next_a, 6), round(next_b, 6)) == (round(-b, 6), round(a, 6))
