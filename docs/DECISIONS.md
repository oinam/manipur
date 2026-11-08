# Decisions

One entry per settled question. Newest at the bottom. Proposals that are not
yet decided live in `PLAN.md` under "Open decisions".

## 2026-11-08 — Procedural rendering, not AI repaint

Google has no 3D mesh for India and there is no derivative-licensed
high-resolution imagery of Imphal, so the tiny.london recipe has no honest
input. The map is rendered from vectors and open rasters. AI restyling is
Phase 5 and parked; the procedural map must stand alone.

## 2026-11-08 — Licence line: no grey zones

Only sources that permit derivative works with attribution. Rendered map
released CC BY-SA 4.0 to satisfy ODbL produced-work obligations cleanly.
Code MIT, copyright Oinam.

## 2026-11-08 — Start with Imphal, specifically a Kangla test patch

Phase 0 renders ~1.5 km around Kangla before any wider work. The go/no-go is
whether the street pattern reads as Imphal.

## 2026-11-08 — Python-first renderer

NumPy + Pillow painter's algorithm for Phases 0–3. Exact pixels, no GPU, easy
for an agent to debug from PNG diffs. Revisit only if Phase 3 is painful.

## 2026-11-08 — Tiles and viewer

512 px WebP Deep Zoom pyramid via libvips; OpenSeadragon, vanilla TypeScript,
Vite; Cloudflare Pages + R2. Same shape as the reference sites so the viewer
code can borrow from isometric-nyc (MIT) where useful.

## 2026-11-08 — Phase 0 plumbing

Python is pinned to 3.12 so the geo stack installs from wheels without GDAL.
Open Buildings is streamed from the S2 level 6 cell and filtered to the area, so
the full cell never touches the disk. 2.5D heights come from the public
`open-buildings-temporal-data` bucket, so no Earth Engine account is needed.

Footprints: Open Buildings polygons need confidence of at least 0.70. One is
a duplicate of an OSM building, which wins, at IoU of at least 0.30 or when at
least 50% of it lies inside the OSM polygon. One at least 50% on mapped water is
dropped. Heights prefer OSM tags, then the 75th percentile of the 2023 raster
inside the footprint (the raster's effective 4 m resolution smears edges), then
3.5 m or 6.5 m by footprint area; all are clamped to 2.5–80 m. Rivers mapped only
as lines default to 30 m wide.

Rendering paints semantic color slots, then applies a palette, so a palette
change never re-renders geometry. Each building's depth is its centroid. DEM is
left out until Phase 3 because the patch is on the flat valley floor.

## 2026-11-08 — Projection, pixel scale, and palette

Brajeshwar chose projection B (2:1 dimetric, 45° rotation), 0.5 m/px, and the
`monsoon` palette from the swatch sheet. The renderer uses these by default.

## 2026-11-08 — Detail crop as the quality test

`manipur detail` styles one 900 px crop to near-final quality, to judge what the
procedural map can become; `render` is unchanged. The `kangla-sw` area is wider
than `kangla` so the crop never runs off the data.

The monsoon palette gains 11 shades derived from its own colors (roof shades,
canopy, water, shadow), for 32 slots in all. Ground stays WorldCover, smoothed by
a box-blur vote, because OSM land use is thin here. Tree positions are procedural:
WorldCover class sets the odds, and OSM `tree_row` lines are followed. Roof type
and color come from a seeded hash, so they are plausible rather than real.

The Shaheed Minar sprite is drawn from shapes in code; no photo pixels are read.
Its position is hand-placed at the center of OSM's park polygon, because no
surveyed coordinate exists, and needs checking by someone who knows the park.

## 2026-11-08 — Phase 0 closed; Phase 1 scale and source

Brajeshwar said to go ahead with Phase 1 after seeing the detail crop.

The municipal bbox in `PLAN.md` is 161 km², not the 35 km² it first said, so the
canvas is about 645 megapixels and is rendered as a grid of frames. OSM comes from
Geofabrik's `north-eastern-zone` extract, read with pyosmium (110 MB, against 1.7 GB
for all of India, on a nearly full disk). Heights are resampled to 2 m for this
area; the raster's effective resolution is about 4 m.

## 2026-11-08 — Phase 1 rendering and tiles

Frames are 2048 px on one integer canvas, each rendered with a 256 px apron and
cropped, so neighbors join without a differing pixel; a test holds that true.
Trees and paddy are anchored to world coordinates. OSM maps no paddy or farmland
here, so WorldCover cropland gets a procedural field lattice.

Open Buildings polygons at least 50% on a road 8 m or wider are dropped: they are
flyovers and footbridges read as roofs. Tiles are lossless WebP, which measured
smaller than lossy for this flat-color art (41 KB per tile against 65 KB at q60)
and stays pixel-exact, so this differs from the reference sites' q60.

Search uses OSM `name` only. The site's name, its domain, and label scripts are
still open in `PLAN.md`; the viewer's title is a placeholder.

## 2026-11-08 — Domain and labels

Brajeshwar chose `manipur.oinam.com` for the site, and Latin labels for now.
