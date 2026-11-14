import { DurableObject } from "cloudflare:workers";

// Planes for the map: one Durable Object keeps today's timetable at Imphal, which the
// viewer draws planes from. It holds no aircraft positions; see docs/AIRCRAFT.md.

interface Secrets {
  AIRCRAFT_FEED?: string; // "on" turns the timetable on; anything else answers 404
  AERODATABOX_KEY?: string; // RapidAPI key for the timetable; no key, no timetable
}

// One scheduled flight at Imphal, as the info panel shows it.
interface Scheduled {
  number: string; // "6E 6514"
  callsign?: string; // "IGO6514"
  airline: string;
  place: string; // the other airport
  time: number; // scheduled, at Imphal
  revised?: number;
  status: string;
}

interface Board {
  date: string; // in Imphal's time zone
  calls: number; // requests made for this date
  units?: number; // API units left on the plan after the last request
  fetched: [number, number]; // when each half of the day was last fetched
  arrivals: Scheduled[][]; // per half of the day
  departures: Scheduled[][];
}

interface FidsTime {
  utc?: string;
}

interface FidsLeg {
  airport?: { name?: string; iata?: string };
  scheduledTime?: FidsTime;
  revisedTime?: FidsTime;
}

interface FidsFlight {
  number: string;
  callSign?: string;
  status?: string;
  airline?: { name?: string };
  departure?: FidsLeg;
  arrival?: FidsLeg;
}

type Bindings = Env & Secrets;

const EDGE_CACHE_S = 10;
const SCHEDULE_SOURCE = "AeroDataBox, https://aerodatabox.com";
const IMPHAL_OFFSET_MS = 5.5 * 3_600_000; // India Standard Time, UTC+5:30
// AeroDataBox's free plan has 400 units a month and each board request costs 2, so at
// most 6 a day (372 units in a long month): both halves of the day, then refreshes for
// status as they go stale. It also stops when the plan reports few units left.
const FIDS = "https://aerodatabox.p.rapidapi.com/flights/airports/iata/IMF";
const FIDS_HOST = "aerodatabox.p.rapidapi.com";
const FIDS_DAILY_CALLS = 6;
const FIDS_STALE_MS = 3 * 3_600_000;
const FIDS_MIN_UNITS = 20;
const HALF_DAY_MS = 12 * 3_600_000;

function utcTime(time: FidsTime | undefined): number | undefined {
  return time?.utc ? Date.parse(time.utc.replace(" ", "T")) : undefined;
}

// AeroDataBox's statuses, in words for the panel; "Unknown" says nothing, so it is blank.
function statusWords(status = "Unknown"): string {
  const words: Record<string, string> = {
    Unknown: "",
    EnRoute: "en route",
    CheckIn: "check-in",
    GateClosed: "gate closed",
    CanceledUncertain: "may be canceled",
  };
  return words[status] ?? status.toLowerCase();
}

function toScheduled(flight: FidsFlight, here: FidsLeg | undefined, there: FidsLeg | undefined) {
  const time = utcTime(here?.scheduledTime);
  if (time === undefined) {
    return [];
  }
  const scheduled: Scheduled = {
    number: flight.number,
    airline: flight.airline?.name ?? "",
    place: there?.airport?.name ?? there?.airport?.iata ?? "",
    time,
    status: statusWords(flight.status),
  };
  const revised = utcTime(here?.revisedTime);
  if (revised !== undefined && revised !== time) {
    scheduled.revised = revised;
  }
  if (flight.callSign) {
    scheduled.callsign = flight.callSign;
  }
  return [scheduled];
}

// Midnight in Imphal, as a UTC time, for the Imphal date of the given time.
function imphalMidnight(time: number): number {
  return Date.parse(`${imphalDate(time)}T00:00Z`) - IMPHAL_OFFSET_MS;
}

function imphalLocal(time: number): string {
  return new Date(time + IMPHAL_OFFSET_MS).toISOString().slice(0, 16);
}

function imphalDate(time: number): string {
  return new Date(time + IMPHAL_OFFSET_MS).toISOString().slice(0, 10);
}

export class AircraftFeed extends DurableObject<Bindings> {
  private refreshing: Promise<void> | null = null;

  // Fetches one half of today's board, the one most in need, within the daily budget.
  private async refreshBoard(): Promise<void> {
    const key = this.env.AERODATABOX_KEY;
    const now = Date.now();
    const date = imphalDate(now);
    const stored = await this.ctx.storage.get<Board>("board");
    const board: Board =
      stored?.date === date
        ? stored
        : { date, calls: 0, fetched: [0, 0], arrivals: [[], []], departures: [[], []] };
    const midnight = imphalMidnight(now);
    const current = now - midnight < HALF_DAY_MS ? 0 : 1;
    const half = board.fetched.findIndex((fetched) => fetched === 0);
    const pick = half >= 0 ? half : now - board.fetched[current] > FIDS_STALE_MS ? current : -1;
    if (
      !key ||
      pick < 0 ||
      board.calls >= FIDS_DAILY_CALLS ||
      (board.units ?? Infinity) < FIDS_MIN_UNITS
    ) {
      if (stored?.date !== date) {
        await this.ctx.storage.put("board", board);
      }
      return;
    }
    const from = midnight + pick * HALF_DAY_MS;
    const window = `${imphalLocal(from)}/${imphalLocal(from + HALF_DAY_MS - 60_000)}`;
    const query = new URLSearchParams({
      withLeg: "true",
      direction: "Both",
      withCancelled: "true",
      withCodeshared: "false",
      withCargo: "false",
      withPrivate: "false",
      withLocation: "false",
    });
    board.calls += 1;
    board.fetched[pick] = now;
    try {
      const response = await fetch(`${FIDS}/${window}?${query.toString()}`, {
        headers: { "X-RapidAPI-Key": key, "X-RapidAPI-Host": FIDS_HOST },
      });
      const units = Number(response.headers.get("X-RateLimit-API-Units-Remaining"));
      if (Number.isFinite(units) && response.headers.has("X-RateLimit-API-Units-Remaining")) {
        board.units = units;
      }
      if (response.status === 204) {
        board.arrivals[pick] = [];
        board.departures[pick] = [];
      } else if (!response.ok) {
        throw new Error(`AeroDataBox ${String(response.status)}`);
      } else {
        const data: { arrivals?: FidsFlight[]; departures?: FidsFlight[] } = await response.json();
        board.arrivals[pick] = (data.arrivals ?? []).flatMap((flight) =>
          toScheduled(flight, flight.arrival, flight.departure),
        );
        board.departures[pick] = (data.departures ?? []).flatMap((flight) =>
          toScheduled(flight, flight.departure, flight.arrival),
        );
      }
      console.log(`AeroDataBox: ${date} half ${String(pick)}, ${String(board.units)} units left`);
    } catch (error) {
      console.error("Timetable fetch failed", error);
    }
    await this.ctx.storage.put("board", board);
  }

  // Today's scheduled flights at Imphal, refreshed within the budget, by scheduled time.
  private async board(): Promise<{ arrivals: Scheduled[]; departures: Scheduled[] }> {
    this.refreshing ??= this.refreshBoard().finally(() => {
      this.refreshing = null;
    });
    await this.refreshing;
    const board = await this.ctx.storage.get<Board>("board");
    const byTime = (a: Scheduled, b: Scheduled) => a.time - b.time;
    return {
      arrivals: (board?.arrivals.flat() ?? []).sort(byTime),
      departures: (board?.departures.flat() ?? []).sort(byTime),
    };
  }

  // What the Worker kept while it polled OpenSky, which it no longer does: the snapshots,
  // the day's sightings, and the polling state. Deleted the first time this runs.
  private async forgetPositions(): Promise<void> {
    await this.ctx.storage.deleteAlarm();
    await this.ctx.storage.delete(["snapshots", "day", "credits", "relayed", "watched"]);
  }

  // Today's timetable at Imphal.
  async schedule(): Promise<{ arrivals: Scheduled[]; departures: Scheduled[] }> {
    await this.forgetPositions();
    return this.board();
  }
}

export default {
  async fetch(request, env: Bindings, context): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/api/aircraft") {
      return env.ASSETS.fetch(request);
    }
    // The timetable alone is served; AIRCRAFT_FEED switches it off.
    if (env.AIRCRAFT_FEED !== "on") {
      return new Response("Not found", { status: 404 });
    }
    if (request.method !== "GET") {
      return new Response("Method not allowed", { status: 405, headers: { Allow: "GET" } });
    }
    const cache = caches.default;
    const cached = await cache.match(request);
    if (cached) {
      return cached;
    }
    const feed = env.AIRCRAFT.get(env.AIRCRAFT.idFromName("imphal"));
    const body = { schedule_source: SCHEDULE_SOURCE, schedule: await feed.schedule() };
    const response = Response.json(body, {
      headers: { "Cache-Control": `public, max-age=${String(EDGE_CACHE_S)}` },
    });
    context.waitUntil(cache.put(request, response.clone()));
    return response;
  },
} satisfies ExportedHandler<Bindings>;
