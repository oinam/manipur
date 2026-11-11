import type { Aircraft, Feed, Snapshot } from "./aircraft";
import { landing, onRunway, takeoff } from "./runway";

// Planes drawn from today's timetable, not from any receiver: each arrival lands on runway
// 22 at its scheduled (or revised) time, and each departure takes off at its own. They are
// labeled as not live, and give way to a live plane with the same callsign.

interface Scheduled {
  number: string;
  callsign?: string;
  time: number;
  revised?: number;
  status: string;
}

interface Schedule {
  arrivals: Scheduled[];
  departures: Scheduled[];
}

const API = "/api/aircraft";
const RELOAD_MS = 60_000;
// Snapshots this far apart; the layer reloads every five seconds, inside each span.
const SNAPSHOT_MS = 10_000;
// How far out a plane is drawn: about six minutes of approach, or of climb.
const PATH_M = 25_000;
const SKIPPED = ["canceled", "may be canceled", "diverted"];

let schedule: Schedule | null = null;
let loadedAt = 0;

async function current(): Promise<Schedule | null> {
  if (Date.now() - loadedAt > RELOAD_MS) {
    loadedAt = Date.now();
    const response = await fetch(API);
    if (response.ok) {
      ({ schedule = null } = (await response.json()) as { schedule?: Schedule });
    }
  }
  return schedule;
}

// The id the airplanes panel looks a flight up by.
export function flightId(flight: { number: string; callsign?: string }): string {
  return flight.callsign ?? flight.number;
}

function planes(board: Schedule, time: number): Aircraft[] {
  const drawn = (
    flights: Scheduled[],
    path: (seconds: number) => [number, number] | null,
  ): Aircraft[] =>
    flights.flatMap((flight) => {
      if (SKIPPED.includes(flight.status)) {
        return [];
      }
      const position = path((time - (flight.revised ?? flight.time)) / 1000);
      if (!position) {
        return [];
      }
      return [{ ...onRunway(...position, flightId(flight)), name: flight.number }];
    });
  return [
    ...drawn(board.arrivals, (seconds) => landing(seconds, PATH_M)),
    ...drawn(board.departures, (seconds) => takeoff(seconds, PATH_M)),
  ];
}

export const timetableFeed: Feed = {
  label: "scheduled, not live",
  delay: 0,
  async load(time: number) {
    const board = await current();
    if (!board) {
      return null;
    }
    const first = Math.floor(time / SNAPSHOT_MS) * SNAPSHOT_MS;
    const at = (moment: number): Snapshot => ({ time: moment, aircraft: planes(board, moment) });
    return [at(first), at(first + SNAPSHOT_MS)];
  },
};
