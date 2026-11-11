# Live aircraft at Imphal

Goal: real planes landing at and leaving Bir Tikendrajit International Airport
(IMF / VEIM), moving on the map. Brajeshwar asked for it to be built on 2026-11-10.

## Source: OpenSky

Read 2026-11-10; both rows are in `docs/DATA.md`. Brajeshwar chose OpenSky and set up
an API client on 2026-11-10. It sees flights near Imphal that adsb.lol misses. Its
terms ask for a written license for a live product. Brajeshwar asked for one on
2026-11-10 and got an automated reply that use is fine within the credit limit, so
the site shows live planes (`docs/DECISIONS.md`, "Live planes on the site").

| Source | Terms found | Fit |
|---|---|---|
| OpenSky Network | Terms of use, read 2026-11-10: the REST API is for "non-profit research and educational use only," and use "in any operational capacity — including but not limited to integration into a live product, service, or automated system — requires a written license," even for non-profits. They also bar passing the data on. | **Used on the site,** within the daily credit limit; license requested from contact[at]opensky-network.org. |
| adsb.lol | API page: "the API is available to everyone"; license ODbL 1.0. No key needed today. | Logged for comparison. Saw nothing near Imphal on the morning of 2026-11-10. |
| adsb.fi | "personal, non-commercial use only." | Not used. |
| airplanes.live | Terms page refuses automated reading. | Not checked. |

The upstream request is one small function in the Worker, so the source can change
without touching the rest.

## The main risk: coverage

Public flight data comes from volunteers' ADS-B receivers. A plane on final
approach is low, and Imphal sits in a valley ringed by hills, so a receiver has to
be close to hear it. We may see planes at cruise and lose them on approach, which
is the part worth drawing. A logger measures this before anything is published.

Measured on the morning of 2026-11-11: OpenSky heard nine airline flights, and none came
closer than 125 km. 6E 6514 from Kolkata, due to land at 08:40 IST, was last heard at
08:07 IST, 126 km out at 8,400 m. The rendered map covers about 13 km around Imphal, so
no live plane reached it. The panel's times are the scheduled landing and leaving times
at Imphal; its tick means only that OpenSky heard the flight within 150 km.

## Decided

Brajeshwar decided these on 2026-11-10.

- **Airline flights only.** An aircraft is kept only when its callsign starts with
  the ICAO code of an airline on a short allowlist (IndiGo `IGO`, Air India `AIC`,
  Air India Express `AXB`, SpiceJet `SEJ`, Alliance Air `LLR`, Akasa `AKJ`)
  followed by a flight number, and it is not flagged military. Everything else is
  dropped on the server and never reaches a browser. The private log records
  everything, so the allowlist can be checked against what flies.
- **A two-minute delay.** The server
  keeps the last few minutes of positions and serves the ones from two minutes ago,
  with the next ones so the viewer can move planes smoothly between two real
  points. The map says the planes are two minutes behind.
- **Polling by need.** Every 5 minutes while no airline flight is within 150 km of
  the airport, every 20 seconds while one is.

## How it works

1. **Logger** (`tools/log_aircraft.py`): the same polling, run locally, writing
   every aircraft within 150 km from both sources to `data/raw/aircraft/`, which is
   not committed.
2. **Server** (built; `web/worker/index.ts`): the site's Worker with one Durable
   Object, `AircraftFeed`. Its alarm is the poller; it fetches OpenSky's states in a
   150 km box (one credit), keeps airline flights, stores timestamped snapshots, and
   keeps five minutes. `/api/aircraft` returns the newest snapshot at least two
   minutes old and the one after it, cached at the edge for 10 seconds so visitors
   share one read. Only callsign, position, height above the field, and track are
   served. It polls at the busy rate for at most 3,600 polls a UTC day, and stops ten
   minutes after the last request, so it stays under OpenSky's 4,000 daily credits.
   OpenSky refuses Cloudflare's addresses (error 522 at its login server), so the
   polling actually happens on Brajeshwar's Mac: `mise run relay` runs the logger,
   which posts each OpenSky reply to `POST /api/aircraft` with the `RELAY_TOKEN`
   bearer token. The Worker filters and stores it as if it had polled, and polls
   OpenSky itself only after ten quiet minutes from the relay. Planes show only while
   the relay runs. `mise run api` runs it locally with `.env`, behind the viewer from
   `mise run dev` (port 8645) or `mise run live` (port 8644).
3. **Viewer** (built; `web/src/aircraft.ts`): a canvas layer like the water's. It
   is not under the Animation switch: a plane is a real event, so it shows even
   with Animation off. A setting of its own may come later. Positions go from latitude and longitude to UTM in the
   browser (`web/src/utm.ts`), then through the current view's matrix, so a plane
   turns with all 24 views. It is lifted by altitude and casts a shadow on the
   ground, and moves smoothly between two snapshots shown two minutes late. `?aircraft=demo` shows a simulated arrival on runway 22 (OSM
   way 44884414, 2,746 m) every five minutes, labeled as simulated
   (`web/src/simulation.ts`). `?aircraft=off` shows no planes.
4. **Info panel** (`web/src/info.ts`): today's timetable at Imphal from AeroDataBox
   (`schedule` in the same API), with a tick on flights OpenSky heard within 150 km. Without a
   timetable it lists OpenSky's sightings as landed, took off, or passed. In IST,
   refreshed every minute.
5. **Credits:** OpenSky in the credits panel, `/about.html`, and the API response.

- **Style C, bold.** The plane is the A320-sized model with body, fin, and engines,
  drawn at twice real size so it reads when zoomed out (`out/imphal/aircraft-options.png`,
  from `tools/aircraft_options.py`). The fin is a plain red, not an airline's colors.

## Decisions for Brajeshwar

- **What to do if coverage is poor:** a local receiver near the airport (needs a
  check of India's rules on radio receivers), planes from the timetable labeled as
  not live, or stopping.

## Sources read

- [adsb.lol API](https://www.adsb.lol/docs/open-data/api) and [API repository](https://github.com/adsblol/api)
- [OpenSky terms of use](https://opensky-network.org/about/terms-of-use)
- [OpenSky REST API](https://openskynetwork.github.io/opensky-api/rest.html)
- [adsb.fi open data](https://github.com/adsbfi/opendata)
- [FlightAware VEIM](https://flightaware.com/live/airport/VEIM)
