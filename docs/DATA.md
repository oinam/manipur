# Data register

Every source used by the pipeline, recorded before first use. Add a row when
you add a source; never remove one. "Used for" must be specific.

| Source | Version / date fetched | Licence | URL | Used for | Attribution text |
|---|---|---|---|---|---|
| OpenStreetMap | Overpass, 2026-11-08 (`kangla`) | ODbL 1.0 | https://www.openstreetmap.org/copyright | roads, water, land use, POIs, names, boundaries, buildings | "© OpenStreetMap contributors" |
| Google Open Buildings v3 | v3, S2 level 6 cell `3749`, 2026-11-08 (`kangla`) | CC BY 4.0 / ODbL 1.0 | https://sites.research.google/open-buildings/ | building footprints where OSM has none | "Google Open Buildings, CC BY 4.0" |
| Google Open Buildings 2.5D Temporal | v1, 2023-06-30 epoch, `gs://open-buildings-temporal-data/v1/geotiffs/37494_2023_06_30/`, 2026-11-08 (`kangla`) | CC BY 4.0 or ODbL 1.0, user's choice; we use CC BY 4.0 | https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings-temporal_v1 | building heights (band 2, `building_height`, meters) | "Google Open Buildings 2.5D Temporal, CC BY 4.0" |
| Copernicus GLO-30 DEM | — | Copernicus DEM licence (free, attribution) | https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model | terrain | "Copernicus DEM © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018, provided under COPERNICUS by the European Union and ESA" |
| ESA WorldCover 2021 | v200, tile `N24E093`, 2026-11-08 (`kangla`) | CC BY 4.0 | https://esa-worldcover.org/ | ground class (paddy, built, forest, water) | "© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium" |
| Sentinel-2 L2A | — | CC BY-SA 3.0 IGO | https://dataspace.copernicus.eu/ | NDVI as tree-density cue only; never sampled for colour | "Contains modified Copernicus Sentinel data" |
| Wikimedia Commons | per file | per file (CC BY / BY-SA / CC0 / PD only) | per file | landmark sprite references; each sprite's sidecar records the file URL and licence | per file |

Fetch dates and exact file names are filled in by `manipur fetch`, which
should append to `data/raw/<area>/SOURCES.txt` and remind you to update this
table.
