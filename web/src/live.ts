import type { Feed, Snapshot } from "./aircraft";

// Airline flights near Imphal from the site's Worker, already two minutes old.

const API = "/api/aircraft";

export const liveFeed: Feed = {
  label: "2 min ago",
  delay: 120_000,
  async load() {
    const response = await fetch(API);
    if (!response.ok) {
      throw new Error(`Aircraft API ${String(response.status)}`);
    }
    const body = (await response.json()) as { snapshots: Snapshot[] };
    const [first, second] = body.snapshots;
    return first && second ? [first, second] : null;
  },
};
