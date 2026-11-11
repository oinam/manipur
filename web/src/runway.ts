import type { Aircraft } from "./aircraft";

// Runway 04/22 and the paths a plane follows on it: in to land on 22 from the northeast,
// and out on 22 to the southwest. Shared by the simulated arrival and the timetable.

const RUNWAY_22: [number, number] = [93.9049069, 24.7697927]; // threshold, OSM way 44884414
const RUNWAY_04: [number, number] = [93.8895255, 24.7494582];
const RUNWAY_M = 2746;
const APPROACH_MPS = 72;
const GLIDE = Math.tan((3 * Math.PI) / 180);
const THRESHOLD_HEIGHT_M = 15;
const TOUCHDOWN_M = 350;
const TAXI_MPS = 12;
const BRAKE_END_M = 1_900;
const VACATE_M = 2_300;
const BRAKING = (APPROACH_MPS ** 2 - TAXI_MPS ** 2) / (2 * (BRAKE_END_M - TOUCHDOWN_M));
const TAKEOFF_ACCELERATION = 2.2; // m/s²
const LIFTOFF_MPS = 75;
const CLIMB_MPS = 80;
const CLIMB_RATE_MPS = 9;

const TRACK =
  (Math.atan2(
    (RUNWAY_04[0] - RUNWAY_22[0]) * Math.cos((RUNWAY_22[1] * Math.PI) / 180),
    RUNWAY_04[1] - RUNWAY_22[1],
  ) *
    180) /
    Math.PI +
  360;

// Distance past the threshold of 22 and height, a number of seconds from touchdown;
// null before the approach starts or once the plane has left the runway.
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
  return along <= VACATE_M ? [along, 0] : null;
}

// The same, a number of seconds from the start of the takeoff roll at the threshold of 22.
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
  const share = along / RUNWAY_M;
  return {
    callsign,
    lon: RUNWAY_22[0] + (RUNWAY_04[0] - RUNWAY_22[0]) * share,
    lat: RUNWAY_22[1] + (RUNWAY_04[1] - RUNWAY_22[1]) * share,
    altitude,
    track: TRACK % 360,
  };
}
