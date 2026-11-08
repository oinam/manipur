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
