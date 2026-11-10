// Where the tile pyramids and their index files live: R2 for the published site,
// out/imphal/tiles (linked into dist) for local builds.
export const TILE_BASE = (import.meta.env.VITE_TILE_BASE as string | undefined) ?? "tiles/";
