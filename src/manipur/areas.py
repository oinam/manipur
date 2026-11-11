"""Named areas the pipeline can build. Bounding boxes come from docs/PLAN.md."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Area:
    name: str
    south: float
    west: float
    north: float
    east: float
    # A Geofabrik extract to cut OSM from; small areas use Overpass instead.
    osm_extract: str | None = None
    # Coarser height sampling keeps large areas in memory; None keeps the source's 0.5 m.
    height_res_m: float | None = None

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """Return (west, south, east, north) in degrees."""
        return (self.west, self.south, self.east, self.north)

    @property
    def center(self) -> tuple[float, float]:
        """Return (lon, lat) of the bounding box center."""
        return ((self.west + self.east) / 2, (self.south + self.north) / 2)


AREAS = {
    "kangla": Area("kangla", 24.800, 93.935, 24.815, 93.952),
    # Wide enough that the 900 px detail crop never runs off the data.
    "kangla-sw": Area("kangla-sw", 24.796, 93.931, 24.811, 93.945),
    "imphal": Area(
        "imphal",
        24.74,
        93.88,
        24.86,
        94.00,
        osm_extract="asia/india/north-eastern-zone",
        height_res_m=2.0,
    ),
    # Loktak Lake with Keibul Lamjao National Park and Moirang, the first step into the valley.
    "loktak": Area(
        "loktak",
        24.42,
        93.74,
        24.62,
        93.90,
        osm_extract="asia/india/north-eastern-zone",
        height_res_m=2.0,
    ),
    # Imphal down to Loktak, one canvas for the site from Phase 3 on.
    "valley": Area(
        "valley",
        24.42,
        93.74,
        24.86,
        94.00,
        osm_extract="asia/india/north-eastern-zone",
        height_res_m=2.0,
    ),
    # The whole state; only `overview` reads it so far.
    "manipur": Area(
        "manipur", 23.83, 93.03, 25.68, 94.78, osm_extract="asia/india/north-eastern-zone"
    ),
}


def get_area(name: str) -> Area:
    try:
        return AREAS[name]
    except KeyError:
        raise SystemExit(f"Unknown area {name!r}. Known areas: {', '.join(AREAS)}") from None
