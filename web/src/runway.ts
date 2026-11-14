import type { Aircraft } from "./aircraft";

// Runway 04/22 and the paths a plane follows around it: in to land on 04 from the
// southwest, off at the southern taxiway to a stand on the apron, and back out by the
// northern taxiway to the threshold of 22 for takeoff toward the southwest, the way it
// came. Positions are
// from OSM: runway way 44884414, taxiways 788999103 and 151116252, apron 151116248.
// Shared by the simulated arrival and the timetable.

type LonLat = [number, number];

const RUNWAY_22: LonLat = [93.9049069, 24.7697927]; // threshold
const RUNWAY_04: LonLat = [93.8895255, 24.7494582];
const RUNWAY_M = 2746;
const APPROACH_MPS = 72;
const GLIDE = Math.tan((3 * Math.PI) / 180);
const THRESHOLD_HEIGHT_M = 15;
const TOUCHDOWN_M = 350;
const TAXI_MPS = 8;
// The southern exit, this far past the threshold of 22, and so this far past that of 04.
const EXIT_FROM_22_M = 1_219;
const EXIT_M = RUNWAY_M - EXIT_FROM_22_M;
// Slowed to taxi speed just before the exit.
const BRAKE_END_M = EXIT_M - 69;
const BRAKING = (APPROACH_MPS ** 2 - TAXI_MPS ** 2) / (2 * (BRAKE_END_M - TOUCHDOWN_M));
const TAKEOFF_ACCELERATION = 2.2; // m/s²
const LIFTOFF_MPS = 75;
const CLIMB_MPS = 80;
const CLIMB_RATE_MPS = 9;
const PUSHBACK_MPS = 2;
const METERS_PER_DEGREE = 111_320;
const COS_LAT = Math.cos((RUNWAY_22[1] * Math.PI) / 180);

// From the southern exit along taxiway 788999103 to the apron's southwest end, then up the
// apron's middle to its northeast end, and out along taxiway 151116252 to the runway.
const EXIT_SOUTH: LonLat[] = [
  [93.89805, 24.76072],
  [93.89795, 24.76104],
  [93.89742, 24.76138],
  [93.89715, 24.76157],
  [93.8968, 24.76178],
];
const APRON_SW: LonLat = [93.8968, 24.76178];
const APRON_NE: LonLat = [93.89852, 24.76404];
const EXIT_NORTH: LonLat[] = [
  [93.89866, 24.76355],
  [93.89896, 24.76336],
  [93.89946, 24.76305],
  [93.89957, 24.76273],
];
// Stands face the terminal, to the northwest of the apron's middle line.
const STAND_SHARES = [0.2, 0.42, 0.64, 0.86];
const STAND_OFFSET_M = 18;
export const STAND_COUNT = STAND_SHARES.length;

function bearing(from: LonLat, to: LonLat): number {
  const degrees = (Math.atan2((to[0] - from[0]) * COS_LAT, to[1] - from[1]) * 180) / Math.PI;
  return (degrees + 360) % 360;
}

function meters(from: LonLat, to: LonLat): number {
  return Math.hypot((to[0] - from[0]) * COS_LAT, to[1] - from[1]) * METERS_PER_DEGREE;
}

function lerp(from: LonLat, to: LonLat, share: number): LonLat {
  return [from[0] + (to[0] - from[0]) * share, from[1] + (to[1] - from[1]) * share];
}

const TRACK = bearing(RUNWAY_22, RUNWAY_04);

// A point this far past the threshold of 22 along the runway's line.
function runwayPoint(along: number): LonLat {
  return lerp(RUNWAY_22, RUNWAY_04, along / RUNWAY_M);
}

function plane(at: LonLat, altitude: number, track: number, callsign: string): Aircraft {
  return { callsign, lon: at[0], lat: at[1], altitude, track };
}

// Distance past the threshold of 04 and height, a number of seconds from touchdown;
// null before the approach starts or once the plane has slowed at the southern exit.
export function landing(fromTouchdown: number, approachM: number): [number, number] | null {
  if (fromTouchdown <= 0) {
    const along = TOUCHDOWN_M + APPROACH_MPS * fromTouchdown;
    if (along < -approachM) {
      return null;
    }
    const height =
      along < 0
        ? THRESHOLD_HEIGHT_M - along * GLIDE
        : THRESHOLD_HEIGHT_M * (1 - along / TOUCHDOWN_M);
    return [along, height];
  }
  const braking = (APPROACH_MPS - TAXI_MPS) / BRAKING;
  if (fromTouchdown <= braking) {
    const along =
      TOUCHDOWN_M + APPROACH_MPS * fromTouchdown - (BRAKING * fromTouchdown * fromTouchdown) / 2;
    return [along, 0];
  }
  const along = BRAKE_END_M + TAXI_MPS * (fromTouchdown - braking);
  return along <= EXIT_M ? [along, 0] : null;
}

// Seconds from touchdown until the plane turns off the runway.
export const LANDED_S = (() => {
  const braking = (APPROACH_MPS - TAXI_MPS) / BRAKING;
  return braking + (EXIT_M - BRAKE_END_M) / TAXI_MPS;
})();

// Distance past the threshold of 22 and height, a number of seconds from the start of the
// takeoff roll there.
export function takeoff(fromRoll: number, climbM: number): [number, number] | null {
  if (fromRoll < 0) {
    return null;
  }
  const rollTime = LIFTOFF_MPS / TAKEOFF_ACCELERATION;
  if (fromRoll <= rollTime) {
    return [(TAKEOFF_ACCELERATION * fromRoll * fromRoll) / 2, 0];
  }
  const climbing = fromRoll - rollTime;
  const along = LIFTOFF_MPS ** 2 / (2 * TAKEOFF_ACCELERATION) + CLIMB_MPS * climbing;
  return along <= climbM ? [along, CLIMB_RATE_MPS * climbing] : null;
}

// A plane on the runway's line, this far past the threshold of 22, heading southwest.
export function onRunway(along: number, altitude: number, callsign: string): Aircraft {
  return plane(runwayPoint(along), altitude, TRACK, callsign);
}

// A landing plane on the runway's line, this far past the threshold of 04, heading northeast.
export function onRunway04(along: number, altitude: number, callsign: string): Aircraft {
  return plane(runwayPoint(RUNWAY_M - along), altitude, (TRACK + 180) % 360, callsign);
}

interface Leg {
  points: LonLat[];
  speed: number; // meters per second
  heading?: number; // fixed, for a pushback; otherwise the direction of travel
}

// A taxi route: where the plane is a number of seconds in, and how long the whole takes.
export interface Route {
  seconds: number;
  at(seconds: number, callsign: string): Aircraft;
}

function route(legs: Leg[]): Route {
  const steps = legs.flatMap((leg) =>
    leg.points.slice(1).map((to, index) => {
      const from = leg.points[index] ?? to;
      return { from, to, seconds: meters(from, to) / leg.speed, heading: leg.heading };
    }),
  );
  const seconds = steps.reduce((sum, step) => sum + step.seconds, 0);
  return {
    seconds,
    at(time, callsign) {
      let left = Math.max(0, time);
      for (const step of steps) {
        if (left <= step.seconds || step === steps[steps.length - 1]) {
          const share = step.seconds > 0 ? Math.min(1, left / step.seconds) : 1;
          const heading = step.heading ?? bearing(step.from, step.to);
          return plane(lerp(step.from, step.to, share), 0, heading, callsign);
        }
        left -= step.seconds;
      }
      return plane(RUNWAY_22, 0, TRACK, callsign);
    },
  };
}

function standPoints(stand: number): { lane: LonLat; spot: LonLat } {
  const lane = lerp(APRON_SW, APRON_NE, STAND_SHARES[stand] ?? 0.5);
  // Northwest, square to the runway, toward the terminal.
  const facing = ((TRACK + 90) * Math.PI) / 180;
  const degrees = STAND_OFFSET_M / METERS_PER_DEGREE;
  const spot: LonLat = [
    lane[0] + (Math.sin(facing) * degrees) / COS_LAT,
    lane[1] + Math.cos(facing) * degrees,
  ];
  return { lane, spot };
}

// A plane parked nose-in at a stand.
export function parked(stand: number, callsign: string): Aircraft {
  const { lane, spot } = standPoints(stand);
  return plane(spot, 0, bearing(lane, spot), callsign);
}

// From the southern exit to the stand.
export function taxiIn(stand: number): Route {
  const { lane, spot } = standPoints(stand);
  return route([
    // The taxiway's first point is on the runway, a few meters back the way the plane came.
    {
      points: [runwayPoint(EXIT_FROM_22_M), ...EXIT_SOUTH.slice(1), lane, spot],
      speed: TAXI_MPS,
    },
  ]);
}

// Pushed back from the stand, along the apron, out to the runway, and back up it to the
// threshold of 22, ready to roll.
export function taxiOut(stand: number): Route {
  const { lane, spot } = standPoints(stand);
  return route([
    { points: [spot, lane], speed: PUSHBACK_MPS, heading: bearing(lane, spot) },
    { points: [lane, APRON_NE, ...EXIT_NORTH, RUNWAY_22], speed: TAXI_MPS },
  ]);
}
