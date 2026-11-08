import geopandas as gpd
import numpy as np
import pytest
import shapely

from manipur.palettes import CANDIDATES, PLACEHOLDER, SLOT, SLOTS
from manipur.render import (
    PROJECTION_A,
    PROJECTION_B,
    Layers,
    centered_viewport,
    render_slots,
)


def sample_layers():
    patch = shapely.box(0, 0, 200, 200)
    empty = gpd.GeoDataFrame({"width_m": [], "road_class": []}, geometry=[], crs=32646)
    ground = gpd.GeoDataFrame({"ground": ["grass"]}, geometry=[patch], crs=32646)
    water = gpd.GeoDataFrame(geometry=[shapely.box(10, 10, 40, 40)], crs=32646)
    buildings = gpd.GeoDataFrame(
        {"building_id": ["a", "b"], "height_m": [6.0, 12.0]},
        geometry=[shapely.box(100, 100, 120, 120), shapely.box(130, 90, 150, 110)],
        crs=32646,
    )
    return Layers(patch, ground, water, empty, empty, buildings)


def test_dimetric_ground_axes_step_two_to_one():
    a, b, d, e = PROJECTION_B.matrix
    assert abs(a / d) == pytest.approx(2.0)
    assert abs(b / e) == pytest.approx(2.0)


@pytest.mark.parametrize("projection", [PROJECTION_A, PROJECTION_B])
def test_north_moves_up_the_screen(projection):
    _, _, _, e = projection.matrix
    assert e < 0


@pytest.mark.parametrize("projection", [PROJECTION_A, PROJECTION_B])
def test_render_is_deterministic_and_paints_every_layer(projection):
    layers = sample_layers()
    view = centered_viewport(projection, 100, 100, 800, 800)
    first = render_slots(layers, projection, view)
    assert np.array_equal(first, render_slots(layers, projection, view))
    painted = set(np.unique(first).tolist())
    assert {SLOT["grass"], SLOT["water"], SLOT["wall_lit"], SLOT["wall_shade"]} <= painted


@pytest.mark.parametrize("palette", [PLACEHOLDER, *CANDIDATES.values()])
def test_palettes_fill_every_slot_within_the_limit(palette):
    assert set(palette) == set(SLOTS)
    assert len(set(palette.values())) <= 32


def test_placeholder_has_eight_colors():
    assert len(set(PLACEHOLDER.values())) == 8
