# Manipur

An isometric pixel-art map of Manipur, starting with Imphal, built entirely from
free and openly licensed map data. No photographs, no satellite imagery in the
output, no scraped tiles. Every pixel is rendered from vectors and open rasters
by code in this repo, so the whole map can be regenerated in minutes whenever the
underlying data improves.

Inspired by [tiny.london](https://tiny.london), [isometric.nyc](https://isometric.nyc)
and [Pixel Singapore](https://www.yadongxie.com/blog/how-pixel-singapore-was-made),
which repaint Google's photogrammetry with a fine-tuned image model. Google has no
3D mesh for any Indian city, so this project takes the other road: a procedural
SimCity-style renderer over OpenStreetMap, Google Open Buildings, Copernicus DEM
and ESA WorldCover, with hand-placed pixel-art sprites for landmarks.

This is a spare-time, for-fun project. It is not a product. See `docs/PLAN.md`
for the plan and `CLAUDE.md` for how an agent picks it up.

## Inspiration

The maps that made us want one of Imphal:

- [tiny.london](https://tiny.london) by Boris Starkov, with a [write-up of how it was made](https://tiny.london/how/).
- [isometric.nyc](https://isometric.nyc) by Andy Coenen, with a [write-up](https://cannoneyed.com/projects/isometric-nyc) and [source code](https://github.com/cannoneyed/isometric-nyc).
- [Pixel Singapore](https://www.yadongxie.com/blog/how-pixel-singapore-was-made) by Yadong Xie.
- [Isopolis SF](https://sf.isopolis.city/) by lawrencechen.

The look and the method owe more to:

- SimCity 2000, for the 2:1 dimetric view and a small vocabulary of building types.
- [osm-isometric-3d](https://github.com/bitsteller/osm-isometric-3d) and [OSM2World](https://osm2world.org/), which showed that isometric maps can be drawn straight from OpenStreetMap.

Notes on how each of these was made are in `docs/RESEARCH.md`.

## Status

Phase 1 (Imphal v1) is live at https://manipur.oinam.com: the full municipal bbox, a zoomable viewer, search, and shareable URLs. Phase 2 (landmarks and polish) is in progress. Phase 0 closed with projection B, 0.5 m/px, and the monsoon palette; see `docs/DECISIONS.md`.

## Layout

```
docs/        plan, research notes, decisions, data register
src/         pipeline: fetch -> prepare -> render -> tile
tools/       one-off helpers, palette tools
data/raw/    downloaded sources (gitignored)
data/derived/ clipped, reprojected, cached (gitignored)
out/         rendered frames and tile pyramids (gitignored)
web/         OpenSeadragon viewer (created in Phase 1)
```

## Licence

Code: MIT. Rendered map: CC BY-SA 4.0 (inherits OpenStreetMap's ODbL share-alike
obligation via the produced work). Data attributions in `docs/DATA.md`.
