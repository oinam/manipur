import OpenSeadragon from "openseadragon";
import { startWater } from "./water";

interface Place {
  name: string;
  kind: string;
  x: number;
  y: number;
  tier: number;
}

interface Label {
  place: Place;
  element: HTMLElement;
}

const MANIFEST = "tiles/manifest.json";
const SEARCH_INDEX = "tiles/search.json";
const MAX_RESULTS = 12;
const FLY_TO_IMAGE_ZOOM = 1.5;
const TIER_MIN_ZOOM: Record<number, number> = { 1: 0, 2: 0.18, 3: 0.8 };
const LABEL_CHAR_PX = 7;
const LABEL_HEIGHT_PX = 20;
const TILT_FULL_ZOOM = 0.1;
const TILT_NONE_ZOOM = 0.4;
const SITE_URL = "https://manipur.oinam.com/";
const NEW_ISSUE_URL = "https://github.com/oinam/manipur/issues/new";
const NEAR_PLACE_MAX_PX = 800;

function byId<T extends HTMLElement>(id: string, type: new () => T): T {
  const element = document.getElementById(id);
  if (!(element instanceof type)) {
    throw new Error(`Missing element #${id}`);
  }
  return element;
}

const viewer = OpenSeadragon({
  element: byId("map", HTMLElement),
  prefixUrl: "",
  drawer: "canvas",
  showNavigationControl: false,
  imageSmoothingEnabled: false,
  maxZoomPixelRatio: 8,
  minZoomImageRatio: 0.8,
  visibilityRatio: 0.4,
  animationTime: 0.6,
  springStiffness: 9,
  background: "#1f2a2e",
} as OpenSeadragon.Options);

function imageZoomToViewport(zoom: number): number {
  return viewer.viewport.imageToViewportZoom(zoom);
}

function readHash(): { x: number; y: number; zoom: number } | null {
  const parts = location.hash.slice(1).split("/").map(Number);
  const [zoom = NaN, x = NaN, y = NaN] = parts;
  if (parts.length !== 3 || ![zoom, x, y].every(Number.isFinite)) {
    return null;
  }
  return { zoom, x, y };
}

function goTo(x: number, y: number, imageZoom: number, immediately: boolean): void {
  const point = viewer.viewport.imageToViewportCoordinates(x, y);
  viewer.viewport.panTo(point, immediately);
  viewer.viewport.zoomTo(imageZoomToViewport(imageZoom), undefined, immediately);
}

function viewCenter(): OpenSeadragon.Point {
  return viewer.viewport.viewportToImageCoordinates(viewer.viewport.getCenter());
}

function viewHash(): string {
  const center = viewCenter();
  const zoom = viewer.viewport.viewportToImageZoom(viewer.viewport.getZoom());
  return `#${zoom.toFixed(3)}/${Math.round(center.x)}/${Math.round(center.y)}`;
}

function writeHash(): void {
  history.replaceState(null, "", viewHash());
}

function nearestPlace(): string | null {
  const center = viewCenter();
  let nearest: string | null = null;
  let best = NEAR_PLACE_MAX_PX;
  for (const place of places) {
    const distance = Math.hypot(place.x - center.x, place.y - center.y);
    if (distance < best) {
      best = distance;
      nearest = place.name;
    }
  }
  return nearest;
}

function updateCorrectionLink(): void {
  const near = nearestPlace();
  const title = near ? `Correction near ${near}` : "Map correction";
  const body = [
    `**Map view:** ${SITE_URL}${viewHash()}`,
    "",
    "**What is wrong or missing?**",
    "",
    "",
    "**How do you know?** (For example, you live nearby, or a public document says so.)",
    "",
    "",
    "Please don't copy details from Google Maps or other proprietary maps; their licenses don't allow it.",
  ].join("\n");
  correctionLink.href = `${NEW_ISSUE_URL}?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
}

const correctionLink = byId("correction", HTMLAnchorElement);
let marker: HTMLElement | null = null;

function showMarker(x: number, y: number): void {
  if (marker) {
    viewer.removeOverlay(marker);
  }
  marker = document.createElement("div");
  marker.className = "marker";
  viewer.addOverlay({
    element: marker,
    location: viewer.viewport.imageToViewportCoordinates(x, y),
    placement: OpenSeadragon.Placement.CENTER,
  });
}

viewer.addOnceHandler("open", () => {
  const start = readHash();
  if (start) {
    goTo(start.x, start.y, start.zoom, true);
  }
  viewer.addHandler("animation-finish", writeHash);
  viewer.addHandler("animation-finish", updateLabels);
  viewer.addHandler("animation-finish", updateCorrectionLink);
  viewer.addHandler("animation", updateTilt);
  updateTilt();
  buildLabels();
  updateCorrectionLink();
  startWater(viewer, byId("water", HTMLButtonElement));
});

window.addEventListener("hashchange", () => {
  const target = readHash();
  if (target) {
    goTo(target.x, target.y, target.zoom, false);
  }
});

const labels: Label[] = [];

function buildLabels(): void {
  if (labels.length || !places.length || !viewer.world.getItemCount()) {
    return;
  }
  for (const place of places) {
    const element = document.createElement("div");
    element.className = `label label-${place.tier}`;
    element.textContent = place.name;
    element.hidden = true;
    viewer.addOverlay({
      element,
      location: viewer.viewport.imageToViewportCoordinates(place.x, place.y),
      placement: OpenSeadragon.Placement.CENTER,
      checkResize: false,
    });
    labels.push({ place, element });
  }
  updateLabels();
}

function imageZoom(): number {
  return viewer.viewport.viewportToImageZoom(viewer.viewport.getZoom());
}

function updateLabels(): void {
  const zoom = imageZoom();
  const taken: { left: number; right: number; top: number; bottom: number }[] = [];
  const ordered = [...labels].sort((a, b) => a.place.tier - b.place.tier);
  for (const { place, element } of ordered) {
    let show = zoom >= (TIER_MIN_ZOOM[place.tier] ?? Infinity);
    if (show) {
      const point = viewer.viewport.imageToViewerElementCoordinates(
        new OpenSeadragon.Point(place.x, place.y),
      );
      const halfWidth = (place.name.length * LABEL_CHAR_PX) / 2;
      const box = {
        left: point.x - halfWidth,
        right: point.x + halfWidth,
        top: point.y - LABEL_HEIGHT_PX / 2,
        bottom: point.y + LABEL_HEIGHT_PX / 2,
      };
      show = !taken.some(
        (other) =>
          box.left < other.right &&
          box.right > other.left &&
          box.top < other.bottom &&
          box.bottom > other.top,
      );
      if (show) {
        taken.push(box);
      }
    }
    element.hidden = !show;
  }
}

function updateTilt(): void {
  const amount = (TILT_NONE_ZOOM - imageZoom()) / (TILT_NONE_ZOOM - TILT_FULL_ZOOM);
  document.documentElement.style.setProperty("--tilt", String(Math.min(1, Math.max(0, amount))));
}

function bindZoom(id: string, action: () => void): void {
  byId(id, HTMLButtonElement).addEventListener("click", action);
}

bindZoom("zoom-in", () => viewer.viewport.zoomBy(1.6).applyConstraints());
bindZoom("zoom-out", () => viewer.viewport.zoomBy(1 / 1.6).applyConstraints());
bindZoom("home", () => viewer.viewport.goHome());

const input = byId("search", HTMLInputElement);
const results = byId("results", HTMLUListElement);
let places: Place[] = [];

fetch(MANIFEST)
  .then((response) => response.json())
  .then((manifest: { pyramid: string }) => {
    viewer.open(`tiles/pyramid/${manifest.pyramid}/imphal.dzi`);
  })
  .catch((error: unknown) => {
    console.error("Tile manifest failed to load", error);
  });

// Browsers may still hold the tierless Phase 1 index under its old one-day header.
fetch(SEARCH_INDEX, { cache: "no-cache" })
  .then((response) => response.json())
  .then((entries: Place[]) => {
    places = entries;
    buildLabels();
    if (viewer.world.getItemCount()) {
      updateCorrectionLink();
    }
  })
  .catch((error: unknown) => {
    console.error("Search index failed to load", error);
    input.placeholder = "Search is unavailable";
    input.disabled = true;
  });

function renderResults(matches: Place[]): void {
  results.replaceChildren(
    ...matches.map((place) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.append(place.name);
      if (place.kind) {
        const kind = document.createElement("small");
        kind.textContent = place.kind.replaceAll("_", " ");
        button.append(kind);
      }
      button.addEventListener("click", () => {
        goTo(place.x, place.y, FLY_TO_IMAGE_ZOOM, false);
        showMarker(place.x, place.y);
        results.hidden = true;
      });
      item.append(button);
      return item;
    }),
  );
  results.hidden = matches.length === 0;
}

input.addEventListener("input", () => {
  const query = input.value.trim().toLowerCase();
  if (!query) {
    results.hidden = true;
    return;
  }
  renderResults(
    places.filter((place) => place.name.toLowerCase().includes(query)).slice(0, MAX_RESULTS),
  );
});
