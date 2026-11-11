# CLAUDE.md

An isometric pixel-art map of Manipur, starting with Imphal, rendered procedurally
from free, openly licensed data. Read `docs/PLAN.md` once before doing anything;
it is the brief. `docs/RESEARCH.md` is the prior art, `docs/DECISIONS.md` is what
has already been settled, `docs/DATA.md` is the register of every source we use.

## The three rules

1. **No pixels from photographs.** Nothing in the output may derive from satellite
   or aerial imagery, Google/Esri/Bing tiles, Street View, or photogrammetry. Open
   rasters (Sentinel-2, WorldCover, DEM) may *drive* the renderer (land cover
   class, elevation, tree density) but are never sampled for colour or texture.
   Landmark sprites may be drawn from reference photos only when those photos are
   on Wikimedia Commons under CC BY / CC BY-SA / CC0 / public domain, and the
   sprite is a drawing, not a filtered photo.
2. **Licence-clean, or it does not go in.** Every source gets a row in
   `docs/DATA.md` with licence, URL, download date and what we use it for, before
   the first line of code touches it. If you are unsure of a licence, stop and ask.
3. **Deterministic and regenerable.** Same inputs, same seed, same output. The map
   must rebuild from `data/raw/` with one command. No hand-edited pixels in the
   pipeline output; manual art lives in `assets/sprites/` as named source files.

## Who decides what

Brajeshwar owns the look: palette, projection, tile vocabulary, which landmarks
get sprites, what the site is called. You propose by rendering options into
`out/` as PNGs and asking; you do not pick. Everything else (data plumbing,
renderer internals, tiling, viewer code) is yours to decide and document in
`docs/DECISIONS.md`.

## How to work here

This is a spare-time project done in short sessions, often while other things
run. So: small tasks, each ending in something visible. Every session should
leave a new PNG in `out/` that Brajeshwar can look at in ten seconds. If a task
cannot produce a picture, it is probably too big; split it.

Do not start Phase N+1 while Phase N has an open go/no-go. Phases and their
exit criteria are in `docs/PLAN.md`.

Prefer boring tools. Python with `uv`, GeoPandas/Shapely/Rasterio/pyproj for
data, NumPy + Pillow for the first renderer, libvips for the tile pyramid,
vanilla TypeScript + OpenSeadragon for the viewer. No framework unless a
decision says so. No GPU required for Phases 0 to 3.

## Commands

mise pins uv, Node, and pnpm, loads secrets from `.env` (copy `.env.example`; git
ignores it), and runs each command below as a task: `mise tasks` lists them, and
`mise run <task> [area]` runs one, for example `mise run frames` or
`mise run plan kangla`. Never print or commit the values in `.env`.

```
mise install && mise run setup           # installs the pinned tools, then both environments
uv sync                                  # installs the pinned Python 3.12 environment
uv run manipur fetch  --area kangla      # downloads into data/raw/<area>/
uv run manipur plan   --area kangla      # writes a top-down check to out/<area>/
uv run manipur prepare --area kangla     # writes data/derived/<area>.gpkg and stats
uv run manipur render --area kangla      # writes frame and full renders to out/<area>/
uv run manipur swatches --area kangla    # writes the candidate palette sheet to out/<area>/
uv run manipur detail --area kangla-sw   # writes the near-final 900 px crop to out/<area>/
uv run python tools/draw_sprites.py      # redraws the landmark sprites in assets/sprites/
uv run python tools/phumdi_options.py    # writes the phumdi style sheet to out/loktak/
uv run python tools/sangai_options.py    # writes the Sangai sprite sheet to out/loktak/
uv run manipur overview --area manipur  # writes a top-down state check from land cover and terrain to out/manipur/
uv run manipur build --area valley       # renders and tiles the site's 24 views one at a time; resumes if stopped
uv run manipur frames --area imphal      # renders all 24 views as seamless 2048 px frames
uv run manipur tile   --area imphal      # builds each view's Deep Zoom pyramid and the search index
pnpm --dir web install && pnpm --dir web build   # builds the viewer into web/dist
mise run dev                             # live-reloading viewer with local tiles: http://localhost:8645 (MAP_AREA=<area> for another)
uv run python tools/upload_tiles.py [area]  # uploads an area's new tile pyramids (default valley), then its index files, to R2
mise run live                            # local aircraft Worker and built viewer: http://localhost:8644
mise run relay                           # feeds live planes to the site from this Mac until stopped
pnpm --dir web run deploy                        # publishes the code by hand; a push to main does it too
uv run pytest                            # runs the tests
uv run ruff check . && uv run ruff format --check .   # lints and checks Python formatting
pnpm --dir web run lint                  # type-checks, lints, and checks viewer formatting
pnpm --dir web run format                # formats the viewer
```

Add `make`/`just` targets as they appear and keep this list current.

## Git

Work directly on `main`; no phase branches, no merging. Commit often,
small, with messages that say what changed in the picture. Never force-push.
Do not push unless asked. Remote: `git@github.com:oinam/manipur.git`.

**A push to `main` publishes the site.** Once lint and tests pass, GitHub Actions
deploys the viewer and Worker to manipur.oinam.com. So asking to push is asking to
publish. Map data is separate: after a re-render, run the upload before pushing, so
R2 has the new pyramids and indexes when the code arrives.

## /odo

The usual Oinam convention, once Brajeshwar creates the files:

- Queue: `~/_/Oinam/1-Projects/devCommands/manipur.md`
- Log:   `~/_/Oinam/1-Projects/devLogs/manipur.md`

## Things that are explicitly parked

AI restyling of the render with an image model (Qwen-Image-Edit LoRA, Nano
Banana passes, MultiDiffusion sampling). It is Phase 5 and may never happen.
Do not build towards it or let it shape the architecture; the procedural map
must stand on its own.
