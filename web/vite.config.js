import { defineConfig } from "vite";

// `vite preview` serves the built map with its local tiles and passes the aircraft
// API to `wrangler dev` on port 8790, so live planes can be tried before anything is deployed.
export default defineConfig({
  preview: {
    port: 8644,
    proxy: { "/api": "http://localhost:8790" },
  },
});
