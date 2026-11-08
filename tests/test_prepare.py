import geopandas as gpd
import numpy as np
import shapely

from manipur.prepare import assign_heights, duplicate_mask, mostly_on_mask


def frame(*polygons):
    return gpd.GeoDataFrame(geometry=list(polygons), crs=32646)


def test_duplicate_mask_separates_touching_from_duplicate():
    osm = frame(shapely.box(0, 0, 10, 10))
    candidates = frame(
        shapely.box(1, 1, 11, 11),  # mostly the same building
        shapely.box(9, 9, 30, 30),  # clips a corner only
        shapely.box(50, 50, 60, 60),  # unrelated
    )
    intersects, duplicate = duplicate_mask(candidates, osm)
    assert intersects.tolist() == [True, True, False]
    assert duplicate.tolist() == [True, False, False]


def test_mostly_on_mask_flags_mostly_covered_polygons():
    water = shapely.box(0, 0, 10, 10)
    candidates = frame(shapely.box(1, 1, 5, 5), shapely.box(8, 0, 18, 10))
    assert mostly_on_mask(candidates, water).tolist() == [True, False]


def test_assign_heights_prefers_tag_then_raster_then_default():
    buildings = frame(
        shapely.box(0, 0, 10, 10), shapely.box(20, 0, 30, 10), shapely.box(40, 0, 50, 10)
    )
    buildings["tagged_height"] = [12.0, np.nan, np.nan]
    result = assign_heights(buildings, np.array([5.0, 7.0, np.nan]))
    assert result["height_m"].tolist() == [12.0, 7.0, 3.5]
    assert result["height_source"].tolist() == ["osm_tag", "temporal_2023", "default"]
