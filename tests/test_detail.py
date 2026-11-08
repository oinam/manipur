import geopandas as gpd
import numpy as np
import shapely
from PIL import Image

from manipur.detail import (
    SLOTS_32,
    TRANSPARENT,
    build_scene,
    detail_colors,
    render_detail,
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


def test_landmark_sprite_uses_only_palette_slots_and_transparency():
    art = np.asarray(Image.open("assets/sprites/shaheed_minar.png"))
    values = set(np.unique(art).tolist())
    assert TRANSPARENT in values
    assert values - {TRANSPARENT} <= set(SLOTS_32.values())
