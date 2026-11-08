"""Named areas the pipeline can build. Bounding boxes come from docs/PLAN.md."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Area:
    name: str
    south: float
    west: float
    north: float
    east: float

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
}


def get_area(name: str) -> Area:
    try:
        return AREAS[name]
    except KeyError:
        raise SystemExit(f"Unknown area {name!r}. Known areas: {', '.join(AREAS)}") from None
