import type { Aircraft, Feed, Snapshot } from "./aircraft";
import {
  LANDED_S,
  STAND_COUNT,
  landing,
  onRunway,
  parked,
  takeoff,
  taxiIn,
  taxiOut,
} from "./runway";

// Planes drawn from today's timetable, not from any receiver. Imphal has no hangar for
// airliners, so each plane stays on the apron between flights: an arrival lands on runway
// 22 at its scheduled (or revised) time, taxis to a stand, and waits there for the same
// airline's next departure, which pushes back, taxis out, and takes off at its own time.
// A plane with no departure after it stays overnight; a departure with nothing before it
// starts the day parked. They are labeled as not live, and give way to a live plane with
// the same callsign.

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

// One airliner's day at Imphal: in on one flight, out on the next, either of which may be
// missing, on one stand in between.
interface Visit {
  arrival?: Scheduled;
  departure?: Scheduled;
  stand: number;
  parkedFrom: number;
  parkedUntil: number;
}

const API = "/api/aircraft";
const RELOAD_MS = 60_000;
// Snapshots this far apart; the layer reloads every five seconds, inside each span.
const SNAPSHOT_MS = 10_000;
// How far out a plane is drawn: about six minutes of approach, or of climb.
const PATH_M = 25_000;
// Lined up at the threshold this long before the takeoff roll.
const HOLD_S = 40;
// The shortest turnaround that pairs an arrival with a departure, and the longest.
const TURNAROUND_MIN_MS = 20 * 60_000;
const TURNAROUND_MAX_MS = 8 * 3_600_000;
const DAY_MS = 86_400_000;
const IMPHAL_OFFSET_MS = 5.5 * 3_600_000;
const SKIPPED = ["canceled", "may be canceled", "diverted"];

let visits: Visit[] = [];
let loadedAt = 0;

// The id the airplanes panel looks a flight up by.
export function flightId(flight: { number: string; callsign?: string }): string {
  return flight.callsign ?? flight.number;
}

function timeOf(flight: Scheduled): number {
  return flight.revised ?? flight.time;
}

function airline(flight: Scheduled): string {
  return flight.number.split(" ")[0] ?? "";
}

// Seconds the departure's taxi out takes, counted back from its takeoff roll.
function outStart(departure: Scheduled, stand: number): number {
  return timeOf(departure) - (HOLD_S + taxiOut(stand).seconds) * 1000;
}

function inEnd(arrival: Scheduled, stand: number): number {
  return timeOf(arrival) + (LANDED_S + taxiIn(stand).seconds) * 1000;
}

// Pairs each departure with the same airline's earliest unpaired arrival that leaves time
// to turn around, then gives every visit the first stand free for its whole stay.
function plan(board: Schedule, now: number): Visit[] {
  const flying = (flights: Scheduled[]) =>
    flights
      .filter((flight) => !SKIPPED.includes(flight.status))
      .sort((a, b) => timeOf(a) - timeOf(b));
  const arrivals = flying(board.arrivals);
  const departures = flying(board.departures);
  const paired = new Set<Scheduled>();
  const pairs: { arrival?: Scheduled; departure?: Scheduled }[] = departures.map((departure) => {
    const arrival = arrivals.find(
      (candidate) =>
        !paired.has(candidate) &&
        airline(candidate) === airline(departure) &&
        timeOf(departure) - timeOf(candidate) >= TURNAROUND_MIN_MS &&
        timeOf(departure) - timeOf(candidate) <= TURNAROUND_MAX_MS,
    );
    if (arrival) {
      paired.add(arrival);
    }
    return { arrival, departure };
  });
  pairs.push(...arrivals.filter((arrival) => !paired.has(arrival)).map((arrival) => ({ arrival })));

  const midnight = Math.floor((now + IMPHAL_OFFSET_MS) / DAY_MS) * DAY_MS - IMPHAL_OFFSET_MS;
  const ordered = pairs.sort(
    (a, b) => (a.arrival ? timeOf(a.arrival) : 0) - (b.arrival ? timeOf(b.arrival) : 0),
  );
  const freeAt = new Array<number>(STAND_COUNT).fill(-Infinity);
  return ordered.map(({ arrival, departure }) => {
    // A stand is held from touchdown, before taxiing in, to the end of the taxi out.
    const from = arrival ? timeOf(arrival) : midnight;
    const until = departure ? timeOf(departure) : midnight + DAY_MS;
    const free = freeAt.findIndex((time) => time <= from);
    const stand = free >= 0 ? free : freeAt.indexOf(Math.min(...freeAt));
    freeAt[stand] = until;
    return {
      arrival,
      departure,
      stand,
      parkedFrom: arrival ? inEnd(arrival, stand) : midnight,
      parkedUntil: departure ? outStart(departure, stand) : midnight + DAY_MS,
    };
  });
}

async function current(): Promise<Visit[]> {
  if (Date.now() - loadedAt > RELOAD_MS) {
    loadedAt = Date.now();
    const response = await fetch(API);
    if (response.ok) {
      const { schedule } = (await response.json()) as { schedule?: Schedule };
      visits = schedule ? plan(schedule, Date.now()) : [];
    }
  }
  return visits;
}

// Where a visit's plane is at a moment, named for the flight it is on, or null if it is
// not at or near Imphal then.
function place(visit: Visit, time: number): Aircraft | null {
  const { arrival, departure, stand } = visit;
  // One id for the whole visit, so the layer can follow the plane from flight to flight.
  const id = flightId(arrival ?? departure ?? { number: "" });
  const named = (plane: Aircraft, flight: Scheduled): Aircraft => ({
    ...plane,
    callsign: id,
    name: flight.number,
    also: [arrival, departure].flatMap((each) => (each ? [flightId(each)] : [])),
  });
  if (arrival && time < visit.parkedFrom) {
    const seconds = (time - timeOf(arrival)) / 1000;
    if (seconds < LANDED_S) {
      const position = landing(seconds, PATH_M);
      return position ? named(onRunway(...position, flightId(arrival)), arrival) : null;
    }
    return named(taxiIn(stand).at(seconds - LANDED_S, flightId(arrival)), arrival);
  }
  const flight = departure ?? arrival;
  if (!flight) {
    return null;
  }
  if (time < visit.parkedUntil) {
    return named(parked(stand, flightId(flight)), flight);
  }
  if (!departure) {
    return null;
  }
  const roll = (time - timeOf(departure)) / 1000;
  if (roll < -HOLD_S) {
    return named(
      taxiOut(stand).at((time - visit.parkedUntil) / 1000, flightId(departure)),
      departure,
    );
  }
  if (roll < 0) {
    return named(onRunway(0, 0, flightId(departure)), departure);
  }
  const position = takeoff(roll, PATH_M);
  return position ? named(onRunway(...position, flightId(departure)), departure) : null;
}

export const timetableFeed: Feed = {
  label: "scheduled, not live",
  delay: 0,
  async load(time: number) {
    const planned = await current();
    if (!planned.length) {
      return null;
    }
    const first = Math.floor(time / SNAPSHOT_MS) * SNAPSHOT_MS;
    const at = (moment: number): Snapshot => ({
      time: moment,
      aircraft: planned.flatMap((visit) => {
        const plane = place(visit, moment);
        return plane ? [plane] : [];
      }),
    });
    return [at(first), at(first + SNAPSHOT_MS)];
  },
};
