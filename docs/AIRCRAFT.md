# Aircraft at Imphal

Goal: planes landing at and leaving Bir Tikendrajit International Airport (IMF / VEIM),
moving on the map. Brajeshwar asked for it to be built on 2026-11-10.

**Since 2026-11-14 the planes come from the timetable alone.** The site showed OpenSky's
live positions from 2026-11-10 on the strength of an automated reply. On 2026-11-11
OpenSky's staff wrote that a live public site needs their paid license ($99 a month),
with no free one for non-commercial sites. Brajeshwar declined, and OpenSky was taken
out of the site (`docs/DECISIONS.md`, "OpenSky off the site").

## Live sources looked at

Read 2026-11-10; the rows used are in `docs/DATA.md`.

| Source | Terms found | Fit |
|---|---|---|
| OpenSky Network | Terms of use, read 2026-11-10: the REST API is for "non-profit research and educational use only," and use "in any operational capacity — including but not limited to integration into a live product, service, or automated system — requires a written license," even for non-profits. They also bar passing the data on. | **Not used on the site.** On 2026-11-11 they confirmed a public site needs the paid license. Logged privately for coverage. |
| adsb.lol | API page: "the API is available to everyone"; license ODbL 1.0. No key needed today. | Logged for comparison. Saw nothing near Imphal on the morning of 2026-11-10. |
| adsb.fi | "personal, non-commercial use only." | Not used. |
| airplanes.live | Terms page refuses automated reading. | Not checked. |

## The main risk: coverage

Public flight data comes from volunteers' ADS-B receivers. A plane on final
approach is low, and Imphal sits in a valley ringed by hills, so a receiver has to
be close to hear it. We may see planes at cruise and lose them on approach, which
is the part worth drawing. A logger measures this before anything is published.

Measured on the morning of 2026-11-11: OpenSky heard nine airline flights, and none came
closer than 125 km. 6E 6514 from Kolkata, due to land at 08:40 IST, was last heard at
08:07 IST, 126 km out at 8,400 m. The rendered map covers about 13 km around Imphal, so
no live plane would have reached it even with a license.

## How it works

1. **Server** (`web/worker/index.ts`): the site's Worker with one Durable Object,
   `AircraftFeed`, which keeps today's timetable at Imphal from AeroDataBox within the
   free plan's budget. `GET /api/aircraft` returns it as `schedule`, cached at the edge
   for 10 seconds. It holds no aircraft positions, and deletes the ones it kept while
   OpenSky was in use. `mise run api` runs it locally with `.env`, behind the viewer
   from `mise run dev` (port 8645) or `mise run live` (port 8644).
2. **Timetable planes** (`web/src/timetable.ts`, paths in `web/src/runway.ts`): each
   scheduled flight is drawn as a plane labeled "scheduled, not live". An arrival lands
   on runway 22 at its scheduled or revised time, after about six minutes of approach
   from 25 km out, leaves by the southern taxiway, and parks nose-in at one of four
   stands on the apron (OSM way 151116248). Imphal has no hangar for airliners, so it
   waits there for the same airline's next departure at least 20 minutes later, which
   pushes back, taxis out by the northern taxiway, backtracks to the threshold of 22,
   holds, starts its roll at its time, and climbs out to 25 km. A plane with no later
   departure stays overnight; a departure with no earlier arrival starts the day
   parked. Canceled and diverted flights are skipped.
3. **Viewer** (`web/src/aircraft.ts`): a canvas layer like the water's. It is not under
   the Animation switch: Brajeshwar decided on 2026-11-10 that planes show even with
   Animation off. Positions go from latitude and longitude to UTM in the browser
   (`web/src/utm.ts`), then through the current view's matrix, so a plane turns with
   every view. It is lifted by altitude and casts a shadow on the ground.
   `?aircraft=demo` shows a simulated arrival on runway 22 (OSM way 44884414, 2,746 m)
   every five minutes, labeled as simulated (`web/src/simulation.ts`). `?aircraft=off`
   shows no planes.
4. **Info panel** (`web/src/info.ts`): today's timetable at Imphal, in IST, refreshed
   every minute. A flight within ten minutes of its time can be clicked to find its
   plane.
5. **Credits:** AeroDataBox in the credits panel, `/about.html`, and the API response.
6. **Logger** (`tools/log_aircraft.py`): a private coverage check, run by hand. It
   writes every aircraft adsb.lol and OpenSky report within 150 km to
   `data/raw/aircraft/`, which is not committed. Nothing from it reaches the site.

- **Style C, bold.** The plane is the A320-sized model with body, fin, and engines,
  drawn at twice real size so it reads when zoomed out (`out/imphal/aircraft-options.png`,
  from `tools/aircraft_options.py`). The fin is a plain red, not an airline's colors.

## Decisions for Brajeshwar

- **A local receiver near the airport,** for real approaches on the map. Needs a check
  of India's rules on radio receivers. Open. OpenSky said on 2026-11-11 that a receiver
  feeding them from Imphal would be valuable, and that they would look at what it could
  mean for a license once it runs.

## Sources read

- [adsb.lol API](https://www.adsb.lol/docs/open-data/api) and [API repository](https://github.com/adsblol/api)
- [OpenSky terms of use](https://opensky-network.org/about/terms-of-use)
- [OpenSky REST API](https://openskynetwork.github.io/opensky-api/rest.html)
- [adsb.fi open data](https://github.com/adsbfi/opendata)
- [FlightAware VEIM](https://flightaware.com/live/airport/VEIM)
