# Picking this up in Claude Code

Open the repo and paste the first prompt. Each later session gets one of the
task prompts, in order. Every session ends with a PNG in `out/` to look at.

## First prompt (Phase 0, session 1)

> Read CLAUDE.md and docs/PLAN.md. We are in Phase 0. Set up the Python project
> with uv (pyproject, `manipur` CLI with `fetch` and `render` subcommands,
> ruff, pytest). Implement `fetch --area kangla`: pull the Kangla bbox from
> Overpass (roads, waterways, water, landuse, natural, buildings, named POIs,
> admin boundaries) and the overlapping Google Open Buildings v3 polygons, into
> data/raw/kangla/. Record fetch dates in data/raw/kangla/SOURCES.txt. Then
> write a throwaway plan view (top-down, not isometric yet) to out/kangla/ so I
> can confirm the data is right before we touch projection. Tell me how many
> OSM buildings vs Open Buildings polygons we got, and what fraction of Open
> Buildings polygons overlap an OSM one.

## Session 2 (Phase 0)

> Implement `prepare --area kangla`: reproject to EPSG:32646, merge OSM and
> Open Buildings footprints (IoU dedupe, OSM wins), attach heights from Open
> Buildings 2.5D Temporal (download the tile covering Imphal, register it in
> docs/DATA.md), classify ground from WorldCover. Write data/derived/kangla.gpkg.
> Then implement the first `render` in NumPy + Pillow: ground, water, roads,
> extruded buildings as flat-shaded boxes, 8-colour placeholder palette. Render
> the same patch in projection A (45°/15° orthographic) and projection B (2:1
> dimetric), 0.5 m/px, 2048 px frames. Save both to out/kangla/ with the
> projection in the filename. Do not pick a projection; I will.

## Session 3 (Phase 0 exit)

> Here is my projection choice and my notes on the two renders: [...]. Fix what
> I flagged, re-render, and then produce a palette swatch sheet: 4 candidate
> palettes of up to 32 colours each, applied to the same frame, side by side in
> one PNG. Then write a short Phase 0 summary at the top of docs/PLAN.md under
> "Status" with the go/no-go facts: footprint counts, Open Buildings noise,
> render time, what looked wrong.

## Then Phase 1

Branch `phase-1-imphal`. Widen to the municipal bbox, switch to Geofabrik
`india-latest.osm.pbf` clipped with osmium rather than Overpass, build the tile
vocabulary from PLAN.md, add trees and paddy, build the pyramid with libvips,
scaffold the viewer. Break into sessions the same way: each ends with a
picture.

## House style for sessions

- Start by reading `docs/DECISIONS.md` so you do not relitigate settled things.
- If a step needs a decision from Brajeshwar, render the options and stop.
- Commit at the end of every session with a message describing the visible
  change. Do not push unless told.
- Update `CLAUDE.md` "Commands" when you add one.
