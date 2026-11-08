# Plan

## Status

*Phase 0 closed 2026-11-08: Brajeshwar said to go ahead with Phase 1 after seeing
the detail crop. Phase 1 is in progress on `phase-1-imphal`. The notes below are
the Phase 0 record.*

**Phase 1, 2026-11-08.** Imphal renders end to end and runs locally: 262,527 buildings,
162 frames in about 150 seconds, a 161 MB pyramid, a viewer with search and
shareable URLs. Live at https://manipur.oinam.com. The Phase 1 exit (a link a Manipuri friend
recognizes) is still open.

**Phase 2, 2026-11-08.** In progress on `phase-2-landmarks`, not yet published. Eight
landmarks are drawn: Shaheed Minar, Kangla Sanathong, Kangla Sha, Shree Govindajee
Temple, Ima Keithel, Mapal Kangjeibung, the airport terminal, and the two war
cemeteries. Labels, tilt-shift, and a credits page work. RIMS and Manipur University
have no usable Commons photo yet, so they have labels only.

**Phase 0 record:**

- **Chosen:** projection B, 0.5 m/px, `monsoon` palette.
- **Footprints:** 57 OSM and 8,170 Open Buildings polygons, 127 (1.6%) of them
  overlapping an OSM building. 7,034 remain after dropping 1,106 below 0.70
  confidence, 62 duplicates of OSM, and 25 on mapped water.
- **Open Buildings noise:** looks extrudable without hand-fixing; awaiting
  confirmation from someone who knows the ground. Footprints follow the road
  grid, 197 polygons are under 10 m², and a few merged blobs reach 4,539 m².
- **Heights:** 6,845 from the 2.5D raster, 19 from OSM tags, 170 defaults.
- **Render time:** under a second per frame; reruns are byte-identical.
- **What looked wrong:** WorldCover's 10 m cells show as stair-steps in the
  ground, most visibly inside Kangla, and OSM land use is fetched but unused.
  Rivers mapped only as lines use a default 30 m width. Trees, labels, and
  building types are not drawn yet.

*Draft 1, 8 November 2026. Written so that Brajeshwar can decide whether to
spend spare time on this, and so that Claude Code can pick it up cold.*

## What this is

A zoomable, searchable isometric pixel-art map of Imphal, then the Imphal valley,
then Manipur, in the spirit of tiny.london and isometric.nyc, but with one hard
constraint that changes everything underneath: no photographs. The map is
rendered procedurally from OpenStreetMap, Google Open Buildings, Copernicus DEM,
ESA WorldCover and (for colour cues only) Sentinel-2. Landmarks get hand-placed
pixel-art sprites.

The result will get the geography right: every road, river, pond, campus,
market and building footprint where it really is, at its real height, with its
real name searchable. It will not get individual facades right; buildings are
drawn from a small vocabulary of types, the way SimCity 2000 drew them. Think
"the most accurate SimCity map of Imphal ever made", not "Imphal photographed
and repainted".

## Why this way and not theirs

The London, NYC, Singapore and San Francisco maps all follow one recipe: render
Google Photorealistic 3D Tiles orthographically, have Gemini redraw frames as
pixel art, fine-tune a Qwen image-edit LoRA on the pairs, run it over the city,
fight the seams. The numbers are in `RESEARCH.md`.

Google has no photogrammetry mesh for any Indian city (Google's own coverage
table marks "Maps 3D" unavailable for India; the proposal has been stuck at the
ministry since about 2015). Without the mesh there is no faithful conditioning
image and no teacher pairs, so the AI route would produce an invented Imphal.
There is also no free high-resolution satellite imagery of Imphal licensed for
derivative works: Sentinel-2 is 10 m (a house is one pixel), and Esri, Bing and
Google imagery forbid it.

So the only honest version of "free data, no photos" is vector-driven rendering.
That turns out to have its own advantages: licence-clean, deterministic,
regenerable in minutes when OSM improves, no GPU, and it scales to the whole
state because hills and forest come from DEM and land cover rather than from
gigapixels of generated texture.

## Honest expectations

This is a lab piece. Nobody will pay for it. What it can be: a thing Manipuris
share widely, a tidy demonstration of an agent building a real geospatial
pipeline from open data, and a map of Imphal that is nicer to look at than
anything that exists. What it will not be: tiny.london. If the tripwires below
fire, stop without guilt.

Time: Phase 0 is half a day. Phase 1 is two to four weekends of spare time.
Money: effectively zero; Cloudflare Pages and R2 free tiers cover hosting at
this size, and the only paid calls are image-model generations for landmark
sprite drafts, tens of dollars at most.

## Data sources

All free, all permit derivative works with attribution. Register each in
`DATA.md` before use.

| Source | What we take | Licence | Notes |
|---|---|---|---|
| OpenStreetMap | roads, rivers, water, land use, railway, airport, POIs, names, admin boundaries, some buildings | ODbL | via Geofabrik `india-latest.osm.pbf` clipped, or Overpass for small bboxes. Building coverage in Imphal is patchy; expect gaps. |
| Google Open Buildings v3 | building footprint polygons for all of India | CC BY 4.0 / ODbL | fills OSM gaps. Confidence score per polygon; threshold and dedupe against OSM. |
| Google Open Buildings 2.5D Temporal | building height estimates (≈4 m raster), presence, counts, 2016–2023 | CC BY 4.0 | heights for extrusion. Sample per footprint. |
| Copernicus GLO-30 DEM | terrain, 30 m | free, open | valley floor and hills; essential from Phase 3. |
| ESA WorldCover 2021 | land cover classes, 10 m | CC BY 4.0 | paddy vs built vs forest vs water; drives ground tile choice. |
| Sentinel-2 L2A | seasonal greenness only (NDVI) | CC BY-SA 3.0 IGO | optional; tree-density cue. Never sampled for colour. |
| Wikimedia Commons | landmark reference photos | CC BY / BY-SA / CC0 per file | for drawing sprites, not for pixels. Record each file URL. |

Approximate bounding boxes, to be confirmed in Phase 0:

- Kangla test patch: 24.800–24.815 N, 93.935–93.952 E (about 1.5 × 1.7 km)
- Imphal municipal area: 24.74–24.86 N, 93.88–94.00 E (about 161 km²; the municipality itself is smaller, but this box is what we render)
- Imphal valley incl. Loktak: 24.45–24.95 N, 93.70–94.10 E
- Manipur state: 23.83–25.68 N, 93.03–94.78 E (about 22,300 km²)

## Architecture

Four stages, each a CLI subcommand, each cacheable:

1. **fetch** — download the sources for a named area into `data/raw/<area>/`.
2. **prepare** — clip, reproject to a local metric CRS (UTM 46N, EPSG:32646),
   merge OSM and Open Buildings footprints (dedupe by IoU, prefer OSM where it
   has a polygon), attach heights, classify ground from WorldCover, sample DEM.
   Output: one GeoPackage per area in `data/derived/`.
3. **render** — the pixel-art renderer. Transform metric coordinates to screen
   via the chosen projection, sort by depth, paint ground tiles, then water,
   roads, buildings (extruded, type chosen by footprint area and height),
   trees, then sprites and labels. Output: a single large PNG, or a grid of
   2048 px frames for big areas.
4. **tile** — `vips dzsave` to a Deep Zoom pyramid of 512 px WebP tiles, plus a
   manifest, plus a search index built from OSM names and coordinates.

Viewer: OpenSeadragon, vanilla TypeScript, Vite. Crisp pixels above 1× zoom,
URL hash carries position and zoom (as the reference sites do), search box over
the index, attribution footer. Hosted on Cloudflare Pages with tiles on R2.
Domain: `manipur.oinam.com`.

Renderer choice for v1: pure Python, NumPy + Pillow, painter's algorithm. It is
slow compared to a GPU but Imphal at 0.5 m/px is about 645 megapixels of canvas and renders
in minutes, it is exact to the pixel, and it is easy for an agent to debug from
PNG diffs. Move to a headless three.js or a Rust renderer only if Phase 3 makes
Python painful.

Projection: to be decided in Phase 0 by rendering the same patch both ways.
Option A is the 45° tilt / 15° rotation orthographic view the AI maps use,
which reads as "aerial". Option B is classic 2:1 dimetric (26.565°), the native
pixel-art projection of SimCity 2000, which gives crisp integer-stepped edges
and looks unmistakably like pixel art. The rotation should be chosen so
Imphal's dominant road grid around Kangla reads cleanly.

Pixel scale: 0.5 m/px for Imphal (London is 0.293, Singapore 0.25). A typical
Imphal house is then roughly 20 × 30 px, enough for a roof and two windows.
Revisit after Phase 0 renders.

## Tile vocabulary (first cut)

A small palette, 32 colours or fewer, decided by Brajeshwar from a swatch sheet
the renderer produces. Buildings are typed by footprint area and height: small
and low becomes a house with pitched tin or RCC flat roof; medium becomes a
shophouse with ground-floor shutters; large and low becomes a shed, market or
hangar; tall becomes a block with repeated storeys. Roof colour varies by a
seeded hash of the footprint so neighbourhoods are not uniform. Roads by OSM
highway class: trunk and primary get centre lines and footpaths, residential
get none, tracks are dirt-coloured. Water is flat with a dithered highlight
pattern; rivers get banks. Trees come from OSM `natural=tree` and wooded land
use, plus a density cue from WorldCover tree cover. Paddy is the valley's
signature and gets its own ground tile with field boundaries from OSM where
mapped, else a procedural pattern.

Landmarks (Phase 2) get individual sprites: Kangla gate and the Kangla Sha,
Shree Govindajee temple, Ima Keithel, the Polo Ground, Shaheed Minar, Manipur
University, RIMS, the airport terminal, the Imphal war cemeteries, Khwairamband
bazaar, and whatever else Brajeshwar lists. Draft sprites may come from an
image model prompted with Commons photos, then cleaned by hand in Affinity or
Aseprite, and saved as named PNGs in `assets/sprites/` with the Commons source
URL in a sidecar.

## Phases

**Phase 0 — Feasibility (half a day).** Fetch the Kangla patch from OSM and
Open Buildings. Render one 2048 px frame in both projections with a crude
8-colour palette. Exit: Brajeshwar looks at the two PNGs and answers one
question: does the real street pattern read as Imphal? If no, stop here.

**Phase 1 — Imphal v1 (2–4 weekends).** Full municipal bbox. Merged footprints
with heights. Palette and tile vocabulary chosen. Roads, water, trees, paddy,
buildings. Tile pyramid, viewer online with search and shareable URLs. Exit:
a link that can be sent to a Manipuri friend who recognises their locality.

**Phase 2 — Landmarks and polish.** 20–30 sprites. Labels at appropriate zooms.
Tilt-shift blur at low zoom. Attribution page. Exit: Brajeshwar is happy to
post it publicly.

**Phase 3 — The valley.** Widen to the Loktak bbox. DEM shading for the
surrounding hills, Loktak's phumdis as a special water tile, Moirang, Sendra,
the airport. Exit: the valley reads as a valley.

**Phase 4 — Manipur.** Multi-scale: state from WorldCover + DEM at coarse
pixels per metre, district headquarters (Churachandpur, Ukhrul, Thoubal,
Senapati, Bishnupur, Kakching, Tamenglong, Chandel, Jiribam) at medium scale,
Imphal at full. One pyramid, sparse where nothing is rendered. Exit: zoom from
the whole state to a Kangla gate without a seam.

**Phase 5 — Parked.** AI restyle experiments. Only if the procedural map is
done and there is still appetite.

## Tripwires

Stop, or re-scope, if any of these happens:

- Phase 0 render does not read as Imphal to someone who knows the city.
- Phase 1 exceeds four weekends of spare time.
- Open Buildings coverage in central Imphal turns out to be too noisy to
  extrude without hand-fixing (test in Phase 0).
- A data source's licence turns out to be unclear. No grey zones; that was the
  whole point.

## Open decisions for Brajeshwar

1. Which landmarks get sprites first.
