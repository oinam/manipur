import { DurableObject } from "cloudflare:workers";

// Live aircraft for the map: one Durable Object polls OpenSky by need, keeps a few
// minutes of filtered snapshots, and serves only positions at least two minutes old.

interface Aircraft {
  callsign: string;
  lon: number;
  lat: number;
  altitude: number; // meters above the field
  track: number;
}

interface Snapshot {
  time: number;
  aircraft: Aircraft[];
}

// One airline flight's first, last, and closest sightings today, for the info panel.
interface Sighting {
  time: number;
  km: number; // from the airport
  altitude: number;
}

interface Track {
  first: Sighting;
  last: Sighting;
  closest: Sighting;
}

interface Day {
  date: string; // in Imphal's time zone
  applied: number; // newest snapshot time already folded in
  tracks: Record<string, Track>;
}

type FlightKind = "arrival" | "departure" | "passing";

interface Flight {
  callsign: string;
  kind: FlightKind;
  time: number;
  km: number;
}

interface Secrets {
  OPENSKY_CLIENT_ID: string;
  OPENSKY_CLIENT_SECRET: string;
  AIRCRAFT_FEED?: string; // "on" turns the feed on; anything else answers 404
  RELAY_TOKEN?: string; // the Mac relay's bearer token; no token, no relay
  AERODATABOX_KEY?: string; // RapidAPI key for the timetable; no key, no timetable
}

// One scheduled flight at Imphal, as the info panel shows it.
interface Scheduled {
  number: string; // "6E 6514"
  callsign?: string; // "IGO6514", to match OpenSky sightings
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

const AIRPORT = { lat: 24.76, lon: 93.8967 }; // Bir Tikendrajit International Airport, VEIM
const FIELD_ELEVATION_M = 774;
const BOX_DEGREES = { lat: 1.35, lon: 1.49 }; // about 150 km; one OpenSky credit
const IDLE_MS = 300_000;
const BUSY_MS = 20_000;
const DELAY_MS = 120_000;
const KEEP_MS = 300_000;
const NEXT_SLACK_MS = 30_000;
const EDGE_CACHE_S = 10;
// OpenSky allows 4,000 credits a day. Past this many, poll at the idle rate (288 a day at most).
const DAILY_BUSY_CREDITS = 3_600;
// Stop polling when nobody has asked for planes in this long; the next visitor restarts it.
const WATCHED_MS = 600_000;
// The Worker polls OpenSky itself only when the relay has been quiet this long.
const RELAYED_MS = 600_000;
const MAX_RELAY_BYTES = 1_000_000;
const RELAY_CLOCK_SLACK_MS = 60_000;
const AIRLINES = ["IGO", "AIC", "AXB", "SEJ", "LLR", "AKJ"];
const AIRLINE_CALLSIGN = new RegExp(`^(${AIRLINES.join("|")})\\d`);
const OPENSKY = "https://opensky-network.org/api/states/all";
const OPENSKY_TOKEN =
  "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token";
const SOURCE = "The OpenSky Network, https://opensky-network.org";
const SCHEDULE_SOURCE = "AeroDataBox, https://aerodatabox.com";
const TOKEN_MARGIN_MS = 60_000;
const IMPHAL_OFFSET_MS = 5.5 * 3_600_000; // India Standard Time, UTC+5:30
// A flight last seen this close and low, and lower than it was first seen, came in to land;
// one first seen like that and climbing took off. Anything else passed by.
const NEAR_KM = 40;
const LOW_M = 3_000;
const KM_PER_DEGREE = 111.2;
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

function kmFromAirport(aircraft: Aircraft): number {
  const dLat = aircraft.lat - AIRPORT.lat;
  const dLon = (aircraft.lon - AIRPORT.lon) * Math.cos((AIRPORT.lat * Math.PI) / 180);
  return Math.round(Math.hypot(dLat, dLon) * KM_PER_DEGREE);
}

function imphalDate(time: number): string {
  return new Date(time + IMPHAL_OFFSET_MS).toISOString().slice(0, 10);
}

function classify(callsign: string, track: Track): Flight {
  const { first, last, closest } = track;
  const lowNear = (sighting: Sighting) => sighting.km <= NEAR_KM && sighting.altitude <= LOW_M;
  if (lowNear(last) && last.altitude < first.altitude) {
    return { callsign, kind: "arrival", time: last.time, km: last.km };
  }
  if (lowNear(first) && last.altitude > first.altitude) {
    return { callsign, kind: "departure", time: first.time, km: first.km };
  }
  return { callsign, kind: "passing", time: closest.time, km: closest.km };
}

type State = [
  string, // icao24
  string | null, // callsign
  string, // origin country
  number | null, // time of position
  number, // last contact
  number | null, // longitude
  number | null, // latitude
  number | null, // barometric altitude, meters
  boolean, // on ground
  number | null, // velocity
  number | null, // true track
  ...unknown[],
];

// Only airline flights with a position leave this function; everything else is dropped.
function toAircraft(states: State[]): Aircraft[] {
  return states.flatMap((state) => {
    const callsign = (state[1] ?? "").trim();
    const [lon, lat, altitude, onGround, track] = [
      state[5],
      state[6],
      state[7],
      state[8],
      state[10],
    ];
    if (!AIRLINE_CALLSIGN.test(callsign) || lon === null || lat === null) {
      return [];
    }
    const height = onGround ? 0 : Math.max(0, (altitude ?? FIELD_ELEVATION_M) - FIELD_ELEVATION_M);
    return [{ callsign, lon, lat, altitude: Math.round(height), track: track ?? 0 }];
  });
}

export class AircraftFeed extends DurableObject<Bindings> {
  private token = "";
  private tokenExpires = 0;
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

  private async bearer(): Promise<string> {
    if (Date.now() > this.tokenExpires - TOKEN_MARGIN_MS) {
      const form = new URLSearchParams({
        grant_type: "client_credentials",
        client_id: this.env.OPENSKY_CLIENT_ID,
        client_secret: this.env.OPENSKY_CLIENT_SECRET,
      });
      const response = await fetch(OPENSKY_TOKEN, { method: "POST", body: form });
      if (!response.ok) {
        throw new Error(`OpenSky token ${String(response.status)}`);
      }
      const reply: { access_token: string; expires_in: number } = await response.json();
      this.token = reply.access_token;
      this.tokenExpires = Date.now() + reply.expires_in * 1000;
    }
    return this.token;
  }

  // The one place that talks to the upstream source.
  private async fetchAircraft(): Promise<Aircraft[]> {
    const box = new URLSearchParams({
      lamin: String(AIRPORT.lat - BOX_DEGREES.lat),
      lamax: String(AIRPORT.lat + BOX_DEGREES.lat),
      lomin: String(AIRPORT.lon - BOX_DEGREES.lon),
      lomax: String(AIRPORT.lon + BOX_DEGREES.lon),
    });
    const response = await fetch(`${OPENSKY}?${box.toString()}`, {
      headers: { Authorization: `Bearer ${await this.bearer()}` },
    });
    if (!response.ok) {
      throw new Error(`OpenSky states ${String(response.status)}`);
    }
    const data: { states: State[] | null } = await response.json();
    const states = data.states ?? [];
    const aircraft = toAircraft(states);
    console.log(`OpenSky: ${states.length} aircraft near Imphal, ${aircraft.length} airline`);
    return aircraft;
  }

  // Folds snapshots into today's log once they are two minutes old, so the log is no
  // newer than the planes on the map. A snapshot is kept long enough to be folded.
  private async fold(snapshots: Snapshot[]): Promise<Day> {
    const now = Date.now();
    const date = imphalDate(now);
    const stored = await this.ctx.storage.get<Day>("day");
    const day: Day = stored?.date === date ? stored : { date, applied: 0, tracks: {} };
    const ready = snapshots.filter(
      (snapshot) =>
        snapshot.time > day.applied &&
        snapshot.time <= now - DELAY_MS &&
        imphalDate(snapshot.time) === date,
    );
    for (const snapshot of ready) {
      for (const aircraft of snapshot.aircraft) {
        const sighting = {
          time: snapshot.time,
          km: kmFromAirport(aircraft),
          altitude: aircraft.altitude,
        };
        const track = day.tracks[aircraft.callsign];
        if (!track) {
          day.tracks[aircraft.callsign] = { first: sighting, last: sighting, closest: sighting };
          continue;
        }
        track.last = sighting;
        if (sighting.km < track.closest.km) {
          track.closest = sighting;
        }
      }
      day.applied = snapshot.time;
    }
    if (ready.length || stored?.date !== date) {
      await this.ctx.storage.put("day", day);
    }
    return day;
  }

  private async store(snapshot: Snapshot): Promise<void> {
    await this.fold((await this.ctx.storage.get<Snapshot[]>("snapshots")) ?? []);
    const kept = ((await this.ctx.storage.get<Snapshot[]>("snapshots")) ?? []).filter(
      (kept) => kept.time > snapshot.time - KEEP_MS && kept.time < snapshot.time,
    );
    kept.push(snapshot);
    await this.ctx.storage.put("snapshots", kept);
  }

  // OpenSky refuses Cloudflare's addresses, so a relay on Brajeshwar's Mac polls it and
  // posts each reply here. While it does, the alarm leaves OpenSky alone.
  async relay(time: number, states: State[]): Promise<void> {
    const now = Date.now();
    await this.ctx.storage.put("relayed", now);
    // A relay clock more than a minute off is ignored in favor of the Worker's.
    const shown = Math.abs(time - now) < RELAY_CLOCK_SLACK_MS ? time : now;
    await this.store({ time: shown, aircraft: toAircraft(states) });
  }

  override async alarm(): Promise<void> {
    const now = Date.now();
    const watched = (await this.ctx.storage.get<number>("watched")) ?? 0;
    if (now - watched > WATCHED_MS) {
      return;
    }
    const relayed = (await this.ctx.storage.get<number>("relayed")) ?? 0;
    if (now - relayed < RELAYED_MS) {
      await this.ctx.storage.setAlarm(now + IDLE_MS);
      return;
    }
    const day = new Date(now).toISOString().slice(0, 10);
    const credits = await this.ctx.storage.get<{ day: string; used: number }>("credits");
    const used = credits?.day === day ? credits.used + 1 : 1;
    await this.ctx.storage.put("credits", { day, used });
    let aircraft: Aircraft[] = [];
    try {
      aircraft = await this.fetchAircraft();
    } catch (error) {
      console.error("Aircraft poll failed", error);
    }
    await this.store({ time: now, aircraft });
    const busy = aircraft.length > 0 && used < DAILY_BUSY_CREDITS;
    await this.ctx.storage.setAlarm(now + (busy ? BUSY_MS : IDLE_MS));
  }

  // The newest snapshot at least two minutes old, and the one after it if that is old enough too.
  // Also today's airline flights, each as an arrival, a departure, or a pass, by time,
  // and today's timetable at Imphal.
  async delayed(): Promise<{
    snapshots: Snapshot[];
    today: Flight[];
    schedule: { arrivals: Scheduled[]; departures: Scheduled[] };
  }> {
    const schedule = await this.board();
    await this.ctx.storage.put("watched", Date.now());
    if ((await this.ctx.storage.getAlarm()) === null) {
      await this.ctx.storage.setAlarm(Date.now());
    }
    const shown = Date.now() - DELAY_MS;
    const snapshots = (await this.ctx.storage.get<Snapshot[]>("snapshots")) ?? [];
    const day = await this.fold(snapshots);
    const today = Object.entries(day.tracks)
      .map(([callsign, track]) => classify(callsign, track))
      .sort((a, b) => a.time - b.time);
    const index = snapshots.findLastIndex((snapshot) => snapshot.time <= shown);
    const before = snapshots[index];
    if (!before) {
      return { snapshots: [], today, schedule };
    }
    const after = snapshots[index + 1];
    const pair = after && after.time <= shown + NEXT_SLACK_MS ? [before, after] : [before, before];
    return { snapshots: pair, today, schedule };
  }
}

function sameToken(given: string, expected: string): boolean {
  const encoder = new TextEncoder();
  const [a, b] = [encoder.encode(given), encoder.encode(expected)];
  return a.byteLength === b.byteLength && crypto.subtle.timingSafeEqual(a, b);
}

async function relay(
  request: Request,
  env: Bindings,
  feed: DurableObjectStub<AircraftFeed>,
): Promise<Response> {
  const token = env.RELAY_TOKEN ?? "";
  const given = request.headers.get("Authorization") ?? "";
  if (!token || !sameToken(given, `Bearer ${token}`)) {
    return new Response("Unauthorized", { status: 401 });
  }
  const text = await request.text();
  if (text.length > MAX_RELAY_BYTES) {
    return new Response("Too large", { status: 413 });
  }
  let body: { time?: unknown; states?: unknown } = {};
  try {
    body = JSON.parse(text) as typeof body;
  } catch {
    // answered below as a bad request
  }
  if (typeof body.time !== "number" || !Array.isArray(body.states)) {
    return new Response("Expected {time, states}", { status: 400 });
  }
  await feed.relay(body.time, body.states as State[]);
  return new Response(null, { status: 204 });
}

export default {
  async fetch(request, env: Bindings, context): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/api/aircraft") {
      return env.ASSETS.fetch(request);
    }
    // OpenSky allowed use within its credit limit (docs/DATA.md); AIRCRAFT_FEED switches it off.
    if (env.AIRCRAFT_FEED !== "on") {
      return new Response("Not found", { status: 404 });
    }
    const feed = env.AIRCRAFT.get(env.AIRCRAFT.idFromName("imphal"));
    if (request.method === "POST") {
      return relay(request, env, feed);
    }
    const cache = caches.default;
    const cached = await cache.match(request);
    if (cached) {
      return cached;
    }
    const body = {
      source: SOURCE,
      schedule_source: SCHEDULE_SOURCE,
      delay_ms: DELAY_MS,
      ...(await feed.delayed()),
    };
    const response = Response.json(body, {
      headers: { "Cache-Control": `public, max-age=${String(EDGE_CACHE_S)}` },
    });
    context.waitUntil(cache.put(request, response.clone()));
    return response;
  },
} satisfies ExportedHandler<Bindings>;
