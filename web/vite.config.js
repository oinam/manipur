import { createReadStream, statSync } from "node:fs";
import { extname, join, normalize } from "node:path";
import process from "node:process";
import { defineConfig } from "vite";

// Both local servers pass the aircraft API to `wrangler dev` on port 8790 (`mise run api`),
// so live planes and the timetable can be tried before anything is deployed. `vite preview`
// serves the built map, whose tiles are linked into dist; the dev server serves them
// straight from the render output.
const API = { "/api": "http://localhost:8790" };
// MAP_AREA picks another rendered area, such as `valley`, while it is being built.
const TILES = join(import.meta.dirname, "../out", process.env.MAP_AREA ?? "imphal", "tiles");
const TYPES = {
  ".json": "application/json",
  ".webp": "image/webp",
  ".dzi": "application/xml",
  ".xml": "application/xml",
};

const localTiles = {
  name: "local-tiles",
  configureServer(server) {
    server.middlewares.use("/tiles", (request, response, next) => {
      const path = normalize(join(TILES, decodeURIComponent(request.url.split("?")[0])));
      if (!path.startsWith(TILES)) {
        next();
        return;
      }
      try {
        if (!statSync(path).isFile()) {
          next();
          return;
        }
      } catch {
        next();
        return;
      }
      response.setHeader("Content-Type", TYPES[extname(path)] ?? "application/octet-stream");
      createReadStream(path).pipe(response);
    });
  },
};

export default defineConfig({
  plugins: [localTiles],
  server: { port: 8645, proxy: API },
  preview: { port: 8644, proxy: API },
});
