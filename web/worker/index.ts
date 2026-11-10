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

interface Secrets {
  OPENSKY_CLIENT_ID: string;
  OPENSKY_CLIENT_SECRET: string;
  AIRCRAFT_FEED?: string; // "on" turns the feed on; anything else answers 404
  RELAY_TOKEN?: string; // the Mac relay's bearer token; no token, no relay
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
const TOKEN_MARGIN_MS = 60_000;

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

  private async store(snapshot: Snapshot): Promise<void> {
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
  async delayed(): Promise<Snapshot[]> {
    await this.ctx.storage.put("watched", Date.now());
    if ((await this.ctx.storage.getAlarm()) === null) {
      await this.ctx.storage.setAlarm(Date.now());
    }
    const shown = Date.now() - DELAY_MS;
    const snapshots = (await this.ctx.storage.get<Snapshot[]>("snapshots")) ?? [];
    const index = snapshots.findLastIndex((snapshot) => snapshot.time <= shown);
    const before = snapshots[index];
    if (!before) {
      return [];
    }
    const after = snapshots[index + 1];
    return after && after.time <= shown + NEXT_SLACK_MS ? [before, after] : [before, before];
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
    const body = { source: SOURCE, delay_ms: DELAY_MS, snapshots: await feed.delayed() };
    const response = Response.json(body, {
      headers: { "Cache-Control": `public, max-age=${String(EDGE_CACHE_S)}` },
    });
    context.waitUntil(cache.put(request, response.clone()));
    return response;
  },
} satisfies ExportedHandler<Bindings>;
