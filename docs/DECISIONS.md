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

## 2026-11-08 — Hosting

The map is served as Cloudflare Workers static assets in the Oinam account, with
`manipur.oinam.com` as its custom domain. This replaces the planned Pages + R2:
161 MB in about 3,500 files needs no R2, and Wrangler attaches the domain itself.

## 2026-11-08 — Landmarks, labels, and tilt-shift

Landmarks come from the list in `PLAN.md`. A mapped building keeps its real
footprint and gets a painted style (`assets/landmarks.json`); a small point-like
monument is a sprite at its mapped position (`assets/sprites/`). All are drawn in
code from the palette's 32 slots, so the domes are pale rather than true gold. The
gate is drawn 1.7 times scale and the Kangla Sha about 2.5 times, so their forms read.

The two war cemeteries are a ground pattern on their OSM polygons. Grave positions
are a regular grid, not surveyed.

Labels are viewer overlays rather than pixels in the tiles, so changing script
later needs no re-render. Tilt-shift is a CSS blur that appears when zoomed out.

## 2026-11-09 — Versioned tiles

The pyramid lives at `tiles/pyramid/<hash>/`, where the hash covers the frame bytes
and tile settings, and is cached as immutable. `tiles/manifest.json` names the
current hash and is revalidated on every load, as are the pages and the search and
credits files. A re-render therefore gets new tile URLs, and no visitor can see old
and new tiles mixed.

## 2026-11-09 — Second landmark round

The inner Kangla and the Assembly come next because Commons covers them well. OSM
names the Pakhangba temple, the Kangla Museum, and the Assembly at points on their
footprints. It does not name the Uttra Shanglen or the citadel walls. The Uttra
Shanglen is the cruciform footprint beside the Kangla Sha, as a photo shows. The
citadel walls are two adjoining footprints that fit coarse photo geotags, so they
are drawn without a label until someone confirms them.

Dome finials are a spike and ball; the earlier crossbar read as a Christian cross.

## 2026-11-09 — Living water

Flowing water is a viewer layer, so it needs no re-render and leaves the tiles
deterministic. It reads the drawn map to find open water, which keeps it off trees,
bridges, and windows. Rivers and streams move along OSM's way direction, which is
downstream by convention; moats and ponds only shimmer. The viewer now uses
OpenSeadragon's canvas drawer, because the layer has to read its pixels. A map
control turns the motion off; it starts off under the system's Reduce Motion setting.

Live aircraft are planned in `docs/AIRCRAFT.md`; nothing is built yet.

## 2026-11-09 — Opening view

The map opens on central Imphal at image zoom 0.5, with Ima Keithel and Kangla both
in frame, instead of fitting the whole canvas. A URL hash still wins, and the home
button still shows all of Imphal.

## 2026-11-09 — Four viewing directions

The map can be seen from four sides: the chosen 2:1 projection at quarter turns,
later narrowed to 15 degree steps (below). Each is a
full render and its own pyramid, because the art is pre-drawn; free rotation would need
a different renderer. The default view's frames are unchanged. Search and flow stay in
default-view coordinates, and the viewer converts them through the ground plane using
each view's matrix from the manifest. Non-default views add a fourth hash segment, so
older links still open as they did.

## 2026-11-09 — Fifteen degree turns

Brajeshwar asked for 15 degree steps, so the four views become 24, named for the turn
from the default (`0`, `15`, ... `345`). Links using the earlier `sw`, `se`, and `ne`
names still open. Alt or Option reverses the turn. While a new view loads, the last
frame stays on screen.

## 2026-11-09 — Tiles on R2

Twenty-four pyramids need about 68,000 files, over the free Workers limit of 20,000.
Brajeshwar chose R2 (bucket `manipur-tiles`), which fits in its free 10 GB. The bucket
is served directly from its own domain, `manipur-tiles.oinam.com`, so tile requests do
not count against Workers' daily free requests. That domain is one level under
`oinam.com` because Universal SSL does not cover deeper names. The viewer asks for
tiles with CORS, since the water layer reads the drawn pixels. Only the versioned
pyramids move; the manifest and indexes stay with the site. Local builds still read
tiles from `out/`.

## 2026-11-09 — Compass

A compass control turns the map to view `315`, the one with true north at the top. Its
needle always points north, using the angle from each view's matrix. It is not the
opening view; the default stays the one Brajeshwar chose.

## 2026-11-09 — Local buildings

Brajeshwar chose "recognizably Imphal" as the realism target and, from a rendered
comparison, local buildings ahead of street life. Pitched houses under 160 m² are now
low tin houses with a veranda on their near long side, and two-thirds of flat roofs of
at least 25 m² carry a black water tank. Which houses get them comes from the existing
seeded hash, so they are plausible rather than surveyed.

## 2026-11-09 — Settings

A gear opens a settings panel. Its first entry, Animation, replaces the water button
and is the one switch for moving things: water now, aircraft if they are built. It
keeps the saved water choice and still starts off under Reduce Motion.
