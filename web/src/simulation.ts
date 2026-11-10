import type { Aircraft, Feed, Snapshot } from "./aircraft";

// A made-up arrival on runway 22, repeating every five minutes, for trying the layer
// without live data. It is labeled as simulated wherever it is drawn.

const RUNWAY_22: [number, number] = [93.9049069, 24.7697927]; // threshold, OSM way 44884414
const RUNWAY_04: [number, number] = [93.8895255, 24.7494582];
const RUNWAY_M = 2746;
const SNAPSHOT_MS = 20_000; // the server polls this often while a flight is near
const CYCLE_S = 300;
const START_M = -12_000;
const APPROACH_MPS = 72;
const GLIDE = Math.tan((3 * Math.PI) / 180);
const THRESHOLD_HEIGHT_M = 15;
const TOUCHDOWN_M = 350;
const TAXI_MPS = 12;
const BRAKE_END_M = 1_900;
const VACATE_M = 2_300;
const BRAKING = (APPROACH_MPS ** 2 - TAXI_MPS ** 2) / (2 * (BRAKE_END_M - TOUCHDOWN_M));

const TRACK =
  (Math.atan2(
    (RUNWAY_04[0] - RUNWAY_22[0]) * Math.cos((RUNWAY_22[1] * Math.PI) / 180),
    RUNWAY_04[1] - RUNWAY_22[1],
  ) *
    180) /
    Math.PI +
  360;

// Distance past the threshold and height, at a moment of the cycle; null once off the runway.
function flight(seconds: number): [number, number] | null {
  const landing = (TOUCHDOWN_M - START_M) / APPROACH_MPS;
  if (seconds <= landing) {
    const along = START_M + APPROACH_MPS * seconds;
    const height =
      along < 0
        ? THRESHOLD_HEIGHT_M - along * GLIDE
        : THRESHOLD_HEIGHT_M * (1 - along / TOUCHDOWN_M);
    return [along, height];
  }
  const braking = (APPROACH_MPS - TAXI_MPS) / BRAKING;
  const rolled = seconds - landing;
  if (rolled <= braking) {
    return [TOUCHDOWN_M + APPROACH_MPS * rolled - (BRAKING * rolled * rolled) / 2, 0];
  }
  const along = BRAKE_END_M + TAXI_MPS * (rolled - braking);
  return along <= VACATE_M ? [along, 0] : null;
}

function snapshot(time: number): Snapshot {
  const position = flight((time / 1000) % CYCLE_S);
  if (!position) {
    return { time, aircraft: [] };
  }
  const [along, altitude] = position;
  const share = along / RUNWAY_M;
  const plane: Aircraft = {
    callsign: "DEMO1",
    lon: RUNWAY_22[0] + (RUNWAY_04[0] - RUNWAY_22[0]) * share,
    lat: RUNWAY_22[1] + (RUNWAY_04[1] - RUNWAY_22[1]) * share,
    altitude,
    track: TRACK % 360,
  };
  return { time, aircraft: [plane] };
}

export const simulatedArrival: Feed = {
  label: "simulated",
  load(time: number) {
    const first = Math.floor(time / SNAPSHOT_MS) * SNAPSHOT_MS;
    return Promise.resolve([snapshot(first), snapshot(first + SNAPSHOT_MS)]);
  },
};
