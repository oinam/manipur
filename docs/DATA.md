# Data register

Every source used by the pipeline, recorded before first use. Add a row when
you add a source; never remove one. "Used for" must be specific.

| Source | Version / date fetched | Licence | URL | Used for | Attribution text |
|---|---|---|---|---|---|
| OpenStreetMap | Overpass, 2026-11-08 (`kangla`, `kangla-sw`, `imphal`) | ODbL 1.0 | https://www.openstreetmap.org/copyright | roads, water, land use, POIs, names, boundaries, buildings | "© OpenStreetMap contributors" |
| Geofabrik extract of OpenStreetMap | `north-eastern-zone`, data to 2026-11-07T21:21:36Z, fetched 2026-11-08 (`imphal`) | ODbL 1.0 | https://download.geofabrik.de/asia/india/north-eastern-zone.html | OSM features for areas too large for Overpass | "© OpenStreetMap contributors" |
| Google Open Buildings v3 | v3, S2 level 6 cell `3749`, 2026-11-08 (`kangla`, `kangla-sw`, `imphal`) | CC BY 4.0 / ODbL 1.0 | https://sites.research.google/open-buildings/ | building footprints where OSM has none | "Google Open Buildings, CC BY 4.0" |
| Google Open Buildings 2.5D Temporal | v1, 2023-06-30 epoch, `gs://open-buildings-temporal-data/v1/geotiffs/37494_2023_06_30/`, 2026-11-08 (`kangla`, `kangla-sw`, `imphal`) | CC BY 4.0 or ODbL 1.0, user's choice; we use CC BY 4.0 | https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings-temporal_v1 | building heights (band 2, `building_height`, meters) | "Google Open Buildings 2.5D Temporal, CC BY 4.0. Contains modified Copernicus Sentinel data" |
| Copernicus GLO-30 DEM | — | Copernicus DEM licence (free, attribution) | https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model | terrain | "Copernicus DEM © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018, provided under COPERNICUS by the European Union and ESA" |
| ESA WorldCover 2021 | v200, tile `N24E093`, 2026-11-08 (`kangla`, `kangla-sw`, `imphal`) | CC BY 4.0 | https://esa-worldcover.org/ | ground class (paddy, built, forest, water) | "© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium" |
| Sentinel-2 L2A | — | CC BY-SA 3.0 IGO | https://dataspace.copernicus.eu/ | NDVI as tree-density cue only; never sampled for colour | "Contains modified Copernicus Sentinel data" |
| Wikimedia Commons | per file; landmark references viewed 2026-11-08 and 2026-11-09 | per file (CC BY / BY-SA / CC0 / PD only) | per file | landmark sprite references; each sprite's sidecar records the file URL and licence | per file |
| adsb.lol API | live; terms read 2026-11-10. The API page says "the API is available to everyone" and gives the license as ODbL 1.0. No key needed; keys are offered and may become required. | ODbL 1.0 | https://www.adsb.lol/docs/open-data/api | live aircraft near Imphal airport: position, altitude, track, speed, and callsign, filtered to airline flights and served two minutes late | "Aircraft data © adsb.lol, ODbL 1.0" |
| OpenSky Network REST API | live; terms read 2026-11-10; account and API client created by Brajeshwar 2026-11-10 | OpenSky General Terms of Use: non-profit research and educational use only. **Public use on the site needs OpenSky's written license, not yet requested or granted.** Data may not be passed on; public pages must cite OpenSky and send them a link. | https://opensky-network.org/about/terms-of-use | local research only, until a license arrives: measuring coverage near Imphal, and building and testing the aircraft layer on Brajeshwar's machine | "The OpenSky Network, https://opensky-network.org" and the citation their terms give |

Fetch dates and exact file names are filled in by `manipur fetch`, which
should append to `data/raw/<area>/SOURCES.txt` and remind you to update this
table.
