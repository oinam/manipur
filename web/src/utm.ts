// Latitude and longitude to UTM zone 46N (EPSG:32646), the map's ground coordinates.
// Snyder's series on WGS 84; well under a meter of error across Manipur.

const A = 6378137;
const F = 1 / 298.257223563;
const K0 = 0.9996;
const CENTRAL_MERIDIAN = 93;
const FALSE_EASTING = 500000;

const E2 = F * (2 - F);
const EP2 = E2 / (1 - E2);

function meridianArc(phi: number): number {
  const e4 = E2 * E2;
  const e6 = e4 * E2;
  return (
    A *
    ((1 - E2 / 4 - (3 * e4) / 64 - (5 * e6) / 256) * phi -
      ((3 * E2) / 8 + (3 * e4) / 32 + (45 * e6) / 1024) * Math.sin(2 * phi) +
      ((15 * e4) / 256 + (45 * e6) / 1024) * Math.sin(4 * phi) -
      ((35 * e6) / 3072) * Math.sin(6 * phi))
  );
}

export function toUtm(lon: number, lat: number): [number, number] {
  const phi = (lat * Math.PI) / 180;
  const lambda = ((lon - CENTRAL_MERIDIAN) * Math.PI) / 180;
  const sin = Math.sin(phi);
  const cos = Math.cos(phi);
  const tan = Math.tan(phi);
  const n = A / Math.sqrt(1 - E2 * sin * sin);
  const t = tan * tan;
  const c = EP2 * cos * cos;
  const a = lambda * cos;
  const easting =
    FALSE_EASTING +
    K0 *
      n *
      (a + ((1 - t + c) * a ** 3) / 6 + ((5 - 18 * t + t * t + 72 * c - 58 * EP2) * a ** 5) / 120);
  const northing =
    K0 *
    (meridianArc(phi) +
      n *
        tan *
        ((a * a) / 2 +
          ((5 - t + 9 * c + 4 * c * c) * a ** 4) / 24 +
          ((61 - 58 * t + t * t + 600 * c - 330 * EP2) * a ** 6) / 720));
  return [easting, northing];
}
