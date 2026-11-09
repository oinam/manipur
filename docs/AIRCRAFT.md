# Live aircraft at Imphal: plan

Goal: real planes landing at and leaving Bir Tikendrajit International Airport
(IMF / VEIM), moving on the map. This is a plan only. No flight source has been
queried and none is in `docs/DATA.md` yet, because rule 2 in `CLAUDE.md` requires
the row first.

## The main risk: coverage

Public flight data comes from volunteers' ADS-B receivers. A plane on final
approach is low, and Imphal sits in a valley ringed by hills, so a receiver has to
be close to hear it. FlightAware lists VEIM in its "secondary service area," and I
found no published feeder count or coverage map for Manipur. We may get planes at
cruise and lose them on approach, which is the part worth drawing.

So the first step measures coverage, and the rest depends on the result.

## Sources

Read 2026-11-09.

| Source | Terms found | Limits | Fit |
|---|---|---|---|
| OpenSky Network | Live data for commercial use needs contact; publications should cite OpenSky. Its terms page refused automated reading, so **read it by hand before use**. | OAuth2 client. 400 credits a day anonymous, 4,000 with an account, 8,000 for an active feeder. A box under 25 square degrees costs 1 credit. Resolution 10 s anonymous, 5 s with an account. | Best documented. Polling every 30 s uses 2,880 credits a day. |
| adsb.fi | Personal, non-commercial use only; must cite adsb.fi and link to it. Says nothing on public websites. | 1 request a second. `/v3/lat/{lat}/lon/{lon}/dist/{nm}`. | Usable only if a public, non-commercial site counts. Ask them. |
| adsb.lol | Its feeder API and historical data are ODbL 1.0. Terms for the public API are not stated. | Dynamic rate limits; API keys are planned. | Promising license, unclear for this use. Ask them. |
| airplanes.live | Page refused automated reading; unverified. | Unverified. | Check by hand. |

Recommended: OpenSky first, once its terms are read by hand.

## Steps

1. **Measure (go or no-go).** Register the source in `docs/DATA.md`, then log every
   aircraft within 40 km of the airport for 48 hours. Count how many arrivals stay
   visible below 1,500 m above the field.
2. **If coverage is poor,** choose between a local receiver and stopping. A
   receiver near the airport also earns OpenSky's feeder credits. It needs a check
   of India's rules on radio receivers, which I have not done. Animating planes
   from a timetable is possible, but it would have to be labeled as not live.
3. **Sprites.** Draw a small airliner in eight headings, with a ground shadow,
   and render options for you to choose from.
4. **Proxy.** Add a Cloudflare Worker route that holds the OAuth secret, caches one
   upstream response for about 30 s for all visitors, and passes on only the fields
   the map needs. The site is static today, so this is its first server code.
5. **Viewer.** Draw planes on a canvas layer like the water's. Place them with the
   map's projection, lift them by altitude, and put the shadow on the ground.
   Interpolate between polls so that motion stays smooth. The runway (OSM way
   44884414, 04/22, 2,746 m) is inside the Imphal map.
6. **Credits.** Add the source to the credits panel and `/about.html`.

## Decisions for Brajeshwar

- **Which aircraft to show.** Imphal also sees military and government flights, and
  Manipur is a sensitive place to publish those movements. Recommended: show only
  scheduled airline callsigns and drop everything else on the server.
- **Whether to delay the feed.** A delay of a minute or two costs little for a
  map like this and lowers that sensitivity further.
- **Whether a local receiver is on the table,** if step 1 fails.
- **The plane sprite,** once options are rendered.

## Sources read

- [OpenSky REST API](https://openskynetwork.github.io/opensky-api/rest.html)
- [adsb.fi open data](https://github.com/adsbfi/opendata)
- [adsb.lol feeder API](https://www.adsb.lol/docs/feeders-only/re-api/) and [API repository](https://github.com/adsblol/api)
- [FlightAware VEIM](https://flightaware.com/live/airport/VEIM)
