import OpenSeadragon from "openseadragon";
import { startAircraft, toImage, type AircraftLayer } from "./aircraft";
import { startInfo } from "./info";
import { liveFeed } from "./live";
import { simulatedArrival } from "./simulation";
import { TILE_BASE } from "./tiles";
import { startWater } from "./water";
import {
  DEFAULT_VIEW,
  FORMER_VIEWS,
  NORTH_UP_VIEW,
  VIEW_ORDER,
  convertPoint,
  northAngle,
  type View,
} from "./views";

interface Place {
  name: string;
  kind: string;
  x: number;
  y: number;
  tier: number;
}

interface Target {
  x: number;
  y: number;
  zoom: number;
  view: string;
}

interface Label {
  place: Place;
  element: HTMLElement;
}

const MANIFEST = `${TILE_BASE}manifest.json`;
const STILL_MAX_MS = 4000;
// Live planes come from the Worker; ?aircraft=demo shows a simulated arrival instead,
// and ?aircraft=off shows none.
const AIRCRAFT_MODE = new URLSearchParams(location.search).get("aircraft");
const AIRCRAFT_DEMO = AIRCRAFT_MODE === "demo";
const SEARCH_INDEX = `${TILE_BASE}search.json`;
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
const OPENING_VIEW: Target = { x: 18900, y: 8400, zoom: 0.5, view: DEFAULT_VIEW };
// The demo opens on the final approach to runway 22, where the simulated plane flies.
const DEMO_OPENING_VIEW: Target = { x: 8800, y: 8700, zoom: 0.35, view: DEFAULT_VIEW };
// The middle of runway 04/22 (OSM way 44884414), where the panel looks for a plane it
// cannot find in the live feed.
const RUNWAY_MIDDLE = { lon: 93.8972, lat: 24.7596 };
const AIRPORT_ZOOM = 0.35;
const PLANE_ZOOM = 0.6;
const SHORTCUT_ZOOM = 0.9;
// The info panel's places to go to: a short name, the name in the search index, and the
// zoom that fits the place on screen.
const SHORTCUTS: [string, string, number][] = [
  ["Airport", "Bir Tikendrajit International Airport", AIRPORT_ZOOM],
  ["Kangla", "Kangla Sha", 0.5],
  ["Ima Keithel", "Ima Keithel", SHORTCUT_ZOOM],
  ["Govindajee Temple", "Shree Govindajee Temple", SHORTCUT_ZOOM],
  ["Khuman Lampak", "Khuman Lampak Main Stadium", 0.6],
  ["RIMS", "Regional Institute of Medical Sciences", SHORTCUT_ZOOM],
  ["JNIMS", "J.N. Hospital Management Society", SHORTCUT_ZOOM],
  ["Shija Hospitals", "Shija Hospitals and Research Institute, Langol", SHORTCUT_ZOOM],
  ["Manipur University", "Manipur University", 0.6],
  ["War Cemetery", "Imphal War Cemetery", SHORTCUT_ZOOM],
];

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
  crossOriginPolicy: "Anonymous",
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

function readHash(): Target | null {
  const parts = location.hash.slice(1).split("/");
  const [zoom = NaN, x = NaN, y = NaN] = parts.slice(0, 3).map(Number);
  const view = FORMER_VIEWS[parts[3] ?? ""] ?? parts[3] ?? DEFAULT_VIEW;
  if (parts.length < 3 || parts.length > 4 || ![zoom, x, y].every(Number.isFinite)) {
    return null;
  }
  return VIEW_ORDER.includes(view) ? { zoom, x, y, view } : null;
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
  const suffix = currentView === DEFAULT_VIEW ? "" : `/${currentView}`;
  return `#${zoom.toFixed(3)}/${Math.round(center.x)}/${Math.round(center.y)}${suffix}`;
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
const needle = byId("needle", HTMLElement);
let views: Record<string, View> = {};
let currentView = DEFAULT_VIEW;
let pendingTarget: Target | null = null;
let still: HTMLCanvasElement | null = null;
let water: ReturnType<typeof startWater> | null = null;
let marker: HTMLElement | null = null;
let aircraft: AircraftLayer | null = null;

// Brings a flight from the airplanes panel into view: the plane if the live feed has it,
// otherwise the runway it is about to use.
function focusFlight(callsign?: string): void {
  const plane = callsign ? aircraft?.locate(callsign) : null;
  const [x, y] = plane ?? toImage(viewData(currentView), RUNWAY_MIDDLE.lon, RUNWAY_MIDDLE.lat);
  goTo(x, y, plane ? PLANE_ZOOM : AIRPORT_ZOOM, false);
}

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

function toCurrentView(x: number, y: number): [number, number] {
  return convertPoint(x, y, viewData(DEFAULT_VIEW), viewData(currentView));
}

function viewData(name: string): View {
  const view = views[name];
  if (!view) {
    throw new Error(`Unknown view ${name}`);
  }
  return view;
}

function placeLabelsInView(): void {
  if (Object.keys(views).length) {
    places = basePlaces.map((place) => {
      const [x, y] = toCurrentView(place.x, place.y);
      return { ...place, x, y };
    });
  }
}

function openView(target: Target): void {
  currentView = target.view;
  pendingTarget = target;
  needle.style.transform = `rotate(${String(northAngle(viewData(target.view)))}deg)`;
  placeLabelsInView();
  // Opening clears the overlays, so the labels and marker are rebuilt or dropped.
  labels.length = 0;
  marker = null;
  viewer.open(`${TILE_BASE}pyramid/${viewData(target.view).pyramid}/imphal.dzi`);
}

// Keeps the last frame on screen until the next view's tiles arrive.
function holdPicture(): void {
  const source = (viewer.drawer as unknown as { canvas: HTMLCanvasElement }).canvas;
  still?.remove();
  const picture = document.createElement("canvas");
  picture.className = "still";
  picture.width = source.width;
  picture.height = source.height;
  picture.getContext("2d")?.drawImage(source, 0, 0);
  source.after(picture);
  still = picture;
  window.setTimeout(() => {
    picture.remove();
  }, STILL_MAX_MS);
}

function rotateView(step: number): void {
  const count = VIEW_ORDER.length;
  turnTo(VIEW_ORDER[(VIEW_ORDER.indexOf(currentView) + step + count) % count]);
}

function turnTo(next: string | undefined): void {
  if (next && next !== currentView && viewer.world.getItemCount()) {
    const center = viewCenter();
    const [x, y] = convertPoint(center.x, center.y, viewData(currentView), viewData(next));
    holdPicture();
    openView({ x, y, zoom: imageZoom(), view: next });
  }
}

viewer.addHandler("open", () => {
  if (pendingTarget) {
    goTo(pendingTarget.x, pendingTarget.y, pendingTarget.zoom, true);
    pendingTarget = null;
  }
  viewer.world.getItemAt(0).addOnceHandler("fully-loaded-change", () => {
    still?.remove();
  });
  updateTilt();
  buildLabels();
  updateCorrectionLink();
  writeHash();
  if (water) {
    water.refresh();
  } else {
    water = startWater(viewer, byId("animation", HTMLInputElement), toCurrentView);
    if (AIRCRAFT_MODE !== "off") {
      const feed = AIRCRAFT_DEMO ? simulatedArrival : liveFeed;
      aircraft = startAircraft(viewer, () => viewData(currentView), feed);
    }
    startInfo(focusFlight);
    viewer.addHandler("animation-finish", writeHash);
    viewer.addHandler("animation-finish", updateLabels);
    viewer.addHandler("animation-finish", updateCorrectionLink);
    viewer.addHandler("animation", updateTilt);
  }
});

window.addEventListener("hashchange", () => {
  const target = readHash();
  if (!target) {
    return;
  }
  if (target.view === currentView) {
    goTo(target.x, target.y, target.zoom, false);
  } else {
    openView(target);
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
// Home is the opening view, near enough to read the city, in whichever way it faces now.
bindZoom("home", () => {
  const [x, y] = toCurrentView(OPENING_VIEW.x, OPENING_VIEW.y);
  goTo(x, y, OPENING_VIEW.zoom, false);
});
bindZoom("compass", () => {
  turnTo(NORTH_UP_VIEW);
});
byId("rotate", HTMLButtonElement).addEventListener("click", (event) => {
  rotateView(event.altKey ? -1 : 1);
});

const settingsButton = byId("settings", HTMLButtonElement);
const settingsPanel = byId("settings-panel", HTMLElement);

function showSettings(open: boolean): void {
  settingsPanel.hidden = !open;
  settingsButton.setAttribute("aria-expanded", String(open));
}

settingsButton.addEventListener("click", () => {
  showSettings(settingsPanel.hidden);
});
// Capture, because the map stops pointer events from bubbling.
document.addEventListener(
  "pointerdown",
  (event) => {
    const target = event.target;
    if (
      target instanceof Node &&
      !settingsPanel.contains(target) &&
      !settingsButton.contains(target)
    ) {
      showSettings(false);
    }
  },
  true,
);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    showSettings(false);
  }
});

const input = byId("search", HTMLInputElement);
const results = byId("results", HTMLUListElement);
let basePlaces: Place[] = [];
let places: Place[] = [];

fetch(MANIFEST)
  .then((response) => response.json())
  .then((manifest: { views: Record<string, View> }) => {
    views = manifest.views;
    openView(readHash() ?? (AIRCRAFT_DEMO ? DEMO_OPENING_VIEW : OPENING_VIEW));
  })
  .catch((error: unknown) => {
    console.error("Tile manifest failed to load", error);
  });

// Browsers may still hold the tierless Phase 1 index under its old one-day header.
fetch(SEARCH_INDEX, { cache: "no-cache" })
  .then((response) => response.json())
  .then((entries: Place[]) => {
    basePlaces = entries;
    places = entries;
    placeLabelsInView();
    buildLabels();
    buildShortcuts();
    if (viewer.world.getItemCount()) {
      updateCorrectionLink();
    }
  })
  .catch((error: unknown) => {
    console.error("Search index failed to load", error);
    input.placeholder = "Search is unavailable";
    input.disabled = true;
  });

function buildShortcuts(): void {
  const known = new Set(basePlaces.map((place) => place.name));
  byId("shortcuts", HTMLDivElement).replaceChildren(
    ...SHORTCUTS.filter(([, name]) => known.has(name)).map(([label, name, zoom]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.title = name;
      button.addEventListener("click", () => {
        // Looked up on click, so it lands right in whichever view is open.
        const place = places.find((candidate) => candidate.name === name);
        if (place) {
          goTo(place.x, place.y, zoom, false);
          showMarker(place.x, place.y);
        }
      });
      return button;
    }),
  );
}

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
