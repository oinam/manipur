# Making the map more realistic

Read 2026-11-09. Brajeshwar chose "recognizably Imphal" as the target, and local
buildings first: low tin houses with verandas and rooftop tanks are built. The rest
of item 3 and the other items are not.

## Do we need real pictures?

Not as pixels, and not for most of the gain. Rule 1 keeps photo pixels out, and
there is no honest source for them anyway: Google has no 3D mesh for India, and no
high-resolution imagery of Imphal is licensed for derivative works (`docs/PLAN.md`).
A map that looks like a photograph would need that imagery, or an AI repaint that
invents the city, which is parked as Phase 5.

Photos do help in one place: as references for drawing, which rule 1 allows. Commons
has run out for Imphal, so these would have to be contributed under CC BY, CC BY-SA,
or CC0.

## What is real today, and what is guessed

| Part of the map | Today | Status |
|---|---|---|
| Building footprints | 262,527; only 429 come from OSM, the rest from Open Buildings | Real shapes |
| Building heights | 256,355 from the 2.5D raster, 6,130 defaults, 42 OSM tags | Mostly measured |
| Roof type and color | Seeded hash | **Guessed** |
| Facades | A small shared vocabulary | **Generic** |
| Tree positions | Procedural, from land cover class | **Guessed** |
| Ground | WorldCover at 10 m, which shows as stair-steps | Coarse |
| Terrain | None; DEM arrives in Phase 3 | **Missing** |
| Landmarks | 14 drawn of a planned 20–30 | Partial |

## What would help most, in order

No photos needed:

1. **Terrain.** Hills around the valley are the most recognizable thing missing. The
   DEM is already planned for Phase 3.
2. **Street life.** Drawn vehicles, market stalls, and power lines, placed by road
   class. Most of what reads as "toy" today is empty roads.
3. **A closer tile vocabulary.** Assam-type houses, tin roofs in the real proportion,
   rooftop water tanks, and shutters along market roads.
4. **Softer ground.** Use OSM land use where it exists, and smooth WorldCover edges.

With photos, as drawing references only:

5. **The remaining landmarks.** RIMS, Manipur University, the State Museum, Khuman
   Lampak Stadium, and Khwairamband Bazaar.
6. **A typical-streets set.** About 30 to 50 photos, taken by you or friends, of
   ordinary houses, shopfronts, and roofs in different localities. This tells the
   vocabulary in item 3 what Imphal actually looks like, and sets the real mix of
   roof types.

Real mapping also helps: roof colors and building types added to OSM by people who
know the area flow straight into the next render.

## Decisions for Brajeshwar

- **Item 2, and the rest of item 3,** which change the look, once options are rendered.
- **Whether you can collect the street photos,** and under which license.
