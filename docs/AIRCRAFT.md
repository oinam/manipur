# Live aircraft at Imphal

Goal: real planes landing at and leaving Bir Tikendrajit International Airport
(IMF / VEIM), moving on the map. Brajeshwar asked for it to be built on 2026-11-10.

## Source: adsb.lol

Read 2026-11-10; the row is in `docs/DATA.md`.

| Source | Terms found | Fit |
|---|---|---|
| adsb.lol | API page: "the API is available to everyone"; license ODbL 1.0. No key needed today; keys are offered and may become required. | **Used.** Same license as OpenStreetMap, which the map already follows. |
| OpenSky Network | Terms of use, read 2026-11-10: the REST API is for "non-profit research and educational use only," and use "in any operational capacity — including but not limited to integration into a live product, service, or automated system — requires a written license," even for non-profits. They also bar passing the data on. | **Not used** without a written license from contact[at]opensky-network.org. |
| adsb.fi | "personal, non-commercial use only." | Not used. |
| airplanes.live | Terms page refuses automated reading. | Not checked. |

The upstream request is one small function, so OpenSky can replace adsb.lol if it
ever grants a license.

## The main risk: coverage

Public flight data comes from volunteers' ADS-B receivers. A plane on final
approach is low, and Imphal sits in a valley ringed by hills, so a receiver has to
be close to hear it. We may see planes at cruise and lose them on approach, which
is the part worth drawing. A logger measures this before anything is published.

## Decided

Brajeshwar decided these on 2026-11-10.

- **Airline flights only.** An aircraft is kept only when its callsign starts with
  the ICAO code of an airline on a short allowlist (IndiGo `IGO`, Air India `AIC`,
  Air India Express `AXB`, SpiceJet `SEJ`, Alliance Air `LLR`, Akasa `AKJ`)
  followed by a flight number, and it is not flagged military. Everything else is
  dropped on the server and never reaches a browser. The private log records
  everything, so the allowlist can be checked against what flies.
- **A two-minute delay.** adsb.lol has no way to ask for the past, so the server
  keeps the last few minutes of positions and serves the ones from two minutes ago,
  with the next ones so the viewer can move planes smoothly between two real
  points. The map says the planes are two minutes behind.
- **Polling by need.** Every 5 minutes while no airline flight is within 150 km of
  the airport, every 20 seconds while one is.

## How it works

1. **Logger** (`tools/log_aircraft.py`): the same polling, run locally, writing
   every aircraft within 150 km to `data/raw/aircraft/`, which is not committed.
2. **Server:** a Cloudflare Worker with one Durable Object. Its alarm is the poller;
   it stores timestamped snapshots, filters them, and keeps about five minutes.
   `/api/aircraft` returns the snapshot at least two minutes old and the one after
   it, cached at the edge for a few seconds so visitors share one read. Only
   callsign, position, altitude, track, speed, and time are served.
3. **Viewer:** a canvas layer like the water's, under the Animation switch. Planes
   are placed with the map's projection, lifted by altitude, and cast a shadow on
   the ground. The runway (OSM way 44884414, 04/22, 2,746 m) is on the map.
4. **Credits:** adsb.lol in the credits panel, `/about.html`, and the API response.

- **Style C, bold.** The plane is the A320-sized model with body, fin, and engines,
  drawn at twice real size so it reads when zoomed out (`out/imphal/aircraft-options.png`,
  from `tools/aircraft_options.py`). The fin is a plain red, not an airline's colors.

## Decisions for Brajeshwar

- **What to do if coverage is poor:** a local receiver near the airport (needs a
  check of India's rules on radio receivers), planes from the timetable labeled as
  not live, or stopping.
- **Deploying the Worker,** the site's first server code.

## Sources read

- [adsb.lol API](https://www.adsb.lol/docs/open-data/api) and [API repository](https://github.com/adsblol/api)
- [OpenSky terms of use](https://opensky-network.org/about/terms-of-use)
- [OpenSky REST API](https://openskynetwork.github.io/opensky-api/rest.html)
- [adsb.fi open data](https://github.com/adsbfi/opendata)
- [FlightAware VEIM](https://flightaware.com/live/airport/VEIM)
