import type { Feed, Snapshot } from "./aircraft";
import { landing, onRunway } from "./runway";

// A made-up arrival on runway 22, repeating every five minutes, for trying the layer
// without live data. It is labeled as simulated wherever it is drawn.

const SNAPSHOT_MS = 20_000; // the server polls this often while a flight is near
const CYCLE_S = 300;
const APPROACH_M = 12_000;
// The approach starts the cycle; touchdown comes this many seconds in.
const TOUCHDOWN_S = 170;

function snapshot(time: number): Snapshot {
  const position = landing(((time / 1000) % CYCLE_S) - TOUCHDOWN_S, APPROACH_M);
  return { time, aircraft: position ? [onRunway(...position, "DEMO1")] : [] };
}

export const simulatedArrival: Feed = {
  label: "simulated",
  delay: 120_000,
  load(time: number) {
    const first = Math.floor(time / SNAPSHOT_MS) * SNAPSHOT_MS;
    return Promise.resolve([snapshot(first), snapshot(first + SNAPSHOT_MS)]);
  },
};
