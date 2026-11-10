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

  override async alarm(): Promise<void> {
    const now = Date.now();
    let aircraft: Aircraft[] = [];
    try {
      aircraft = await this.fetchAircraft();
    } catch (error) {
      console.error("Aircraft poll failed", error);
    }
    const kept = ((await this.ctx.storage.get<Snapshot[]>("snapshots")) ?? []).filter(
      (snapshot) => snapshot.time > now - KEEP_MS,
    );
    kept.push({ time: now, aircraft });
    await this.ctx.storage.put("snapshots", kept);
    await this.ctx.storage.setAlarm(now + (aircraft.length ? BUSY_MS : IDLE_MS));
  }

  // The newest snapshot at least two minutes old, and the one after it if that is old enough too.
  async delayed(): Promise<Snapshot[]> {
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

export default {
  async fetch(request, env: Bindings, context): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/api/aircraft") {
      return env.ASSETS.fetch(request);
    }
    const cache = caches.default;
    const cached = await cache.match(request);
    if (cached) {
      return cached;
    }
    const feed = env.AIRCRAFT.get(env.AIRCRAFT.idFromName("imphal"));
    const body = { source: SOURCE, delay_ms: DELAY_MS, snapshots: await feed.delayed() };
    const response = Response.json(body, {
      headers: { "Cache-Control": `public, max-age=${String(EDGE_CACHE_S)}` },
    });
    context.waitUntil(cache.put(request, response.clone()));
    return response;
  },
} satisfies ExportedHandler<Bindings>;
