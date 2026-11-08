# Research: how the reference maps were made

Collected 8 November 2026. All four share one recipe; the differences are
polish and how seams were handled. None of it transfers directly to Imphal
because the recipe begins with Google Photorealistic 3D Tiles, which do not
exist for India. Recorded here so we know what we are and are not copying.

## The shared recipe

1. Stream Google Photorealistic 3D Tiles into three.js (NASA-AMMOS
   `3d-tiles-renderer` in the NYC repo) in a headless browser. One orthographic
   camera, tilted 45° down and rotated 15° west of north, at 0.25–0.3 m/px.
   Shots of 2048 px.
2. Have a frontier image model (Nano Banana / Gemini 3 Pro Image) redraw a few
   hundred to a few thousand frames as pixel art. Filter automatically
   (compare to render and to OSM) and by eye. These become training pairs.
3. Fine-tune a LoRA on an open image-edit model (Qwen-Image-Edit, later
   Qwen-Image-2.1-Turbo). Cheap: NYC's first was ~40 pairs, 4 h, $12 on
   oxen.ai; London's final was rank 32, 6,326 pairs, 8,000 steps, ~3h50 on one
   H100.
4. Run the LoRA over the whole city. Seams are the hard problem.
5. Cut into a Deep Zoom pyramid of 512 px WebP tiles; serve with OpenSeadragon.

## tiny.london (Boris Starkov, live 13 Oct 2026)

- 1,591 km² of Greater London. Canvas 221,184 × 135,168 px (~29.9 gigapixels),
  432 × 264 grid of 512 px tiles, 10 zoom levels, 0.293 m/px.
- 3,570 source renders; teacher Gemini 3 Pro Image redrew ~2,500; ~31% rejected
  by automatic checks against the render and OSM.
- Seams: "a sampling problem, not a model problem." Whole city denoised as one
  latent in overlapping windows, MultiDiffusion-style, with RePaint-style
  pinning of finished pixels. 125 blocks, 31 GPU-hours for the final run; ~70
  H100-hours across all experiments. A tile-by-tile attempt in August had 55 of
  169 boundaries with visible seams, which forced the redesign.
- OSM water polygons used to find and remove 10 hallucinated landmarks on water.
- Viewer: React + OpenSeadragon, WebP pyramid on Cloudflare R2, immutable
  version folders, cloud shader from distance fields, search over 3,180 places
  plus TfL stations, postcodes via postcodes.io.
- Built on isometric-nyc (MIT). Most code, GPU jobs and training run by Claude
  Code; the author set rules and style and judged bugs.
- Source: https://tiny.london/how/

## isometric.nyc (Andy Coenen, Jan 2026)

- Tried CityGML building data with a custom renderer first; rejected because it
  did not match satellite imagery well enough. Switched to Google 3D Tiles.
- Unit is a 512 px "quadrant"; each model call produces a 2×2 quadrant image.
  ~32k–40k quadrants. Infill training: part of the target masked so new tiles
  generate next to existing ones. Legal-generation rules to avoid seams, plus
  manual repair. SQLite for quadrant state, a bespoke web app for planning.
- Fine-tune on oxen.ai (~40 pairs, 4 h, $12). Inference on Lambda H100s at
  under $3/h, >200 generations/h.
- Code: https://github.com/cannoneyed/isometric-nyc (MIT). Author warns it was
  almost entirely agent-written and he has read under 1% of it. Layout:
  `src/web_render` (3D Tiles renderer, needs `VITE_GOOGLE_TILES_API_KEY`),
  `src/isometric_nyc` (pipeline + generation app), `src/app` (React +
  OpenSeadragon viewer), `inference/` (Modal), `docs/`.
- Write-up: https://cannoneyed.com/projects/isometric-nyc

## Pixel Singapore (Yadong Xie, 2026)

- 8 × 6 km, 31,744 × 16,384 px (~520 MP), 160 shots of 2048 px (512 m each),
  0.25 m/px. Also renders a height pass in cm that drives animation.
- Qwen-Image-2.1-Turbo + style LoRA conditioned on the render. MultiDiffusion
  over 1024 px windows spaced 768 px, second grid shifted 384 px, 8 steps.
  Five blocks of 16,384 × 10,240 px with 1,024 px overlap, RePaint-style
  re-noising of known neighbour pixels.
- One RTX 5080, 14.84 GB peak VRAM. ~83–112 min per block; ~6.6 h for the
  four Marina Bay blocks. Resumable per step.
- 2,660 WebP tiles at q60, 189 MB (321 MB with animation), 16 levels, 1 px
  overlap, sparse pyramid with a manifest.
- Animation layer: ~490 km of OSM roads split into ~14k edges, intelligent
  driver model, two-phase signals on a 70 s cycle, vehicle sprites at 32
  headings, occlusion from the height pass and canopy detection, trees via
  watershed on canopy height, water from flat teal areas, birds and 769
  chickens from OSM locations. Tilt-shift via stacked backdrop-filter blurs.
- Notes "hazy rectangles where the source has no high-resolution 3D model".
  That is what all of Imphal would look like.
- Not open source. Source: https://www.yadongxie.com/blog/how-pixel-singapore-was-made

## Isopolis SF (lawrencechen, 2026)

- Same recipe; Qwen Image Edit 2511 fine-tune on Google 3D renders, Nano Banana
  teacher in a Ghibli-ish style. 583 curated places, guided tours. Not open
  source. HN thread noted the hills look flat because the view cannot rotate.
- https://sf.isopolis.city/

## Why Imphal cannot use the recipe

- Google Maps Platform coverage table: "Maps 3D" unavailable for India
  (https://developers.google.com/maps/coverage#countryregion-coverage).
- Government permission for 3D imagery of Indian cities has been discussed
  since 2015 and never granted.
- No free high-resolution satellite imagery licensed for derivatives:
  Sentinel-2 is 10 m; Esri/Bing/Google imagery terms forbid derived artworks;
  Maxar Open Data is disaster-only; Bhuvan/Cartosat is not openly licensed.

## What we do take from them

- Projection conventions (45°/15° orthographic) as one of two options.
- 512 px WebP Deep Zoom pyramid, sparse, with a manifest and versioned folders.
- OpenSeadragon viewer with URL-hash position and a name search index.
- The idea of a height pass driving later effects (tilt-shift, occlusion).
- Using OSM as the truth check: anything the renderer puts on water is a bug.

## Older open-source prior art for the procedural route

- bitsteller/osm-isometric-3d: isometric 3D renders of German cities from OSM,
  circa 2012. Proof that the vector route works; dated tooling.
- OSM2World: OSM to 3D, has had isometric map outputs.
- The CityGML attempt inside isometric-nyc is the same idea with better data
  than we have; worth reading for what failed.
