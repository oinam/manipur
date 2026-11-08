import OpenSeadragon from "openseadragon";

interface Place {
  name: string;
  kind: string;
  x: number;
  y: number;
}

const TILES = "tiles/imphal.dzi";
const SEARCH_INDEX = "tiles/search.json";
const MAX_RESULTS = 12;
const FLY_TO_IMAGE_ZOOM = 1.5;

const viewer = OpenSeadragon({
  element: document.getElementById("map") as HTMLElement,
  tileSources: TILES,
  prefixUrl: "",
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
  if (parts.length !== 3 || parts.some((part) => !Number.isFinite(part))) {
    return null;
  }
  return { zoom: parts[0], x: parts[1], y: parts[2] };
}

function goTo(x: number, y: number, imageZoom: number, immediately: boolean): void {
  const point = viewer.viewport.imageToViewportCoordinates(x, y);
  viewer.viewport.panTo(point, immediately);
  viewer.viewport.zoomTo(imageZoomToViewport(imageZoom), undefined, immediately);
}

function writeHash(): void {
  const center = viewer.viewport.viewportToImageCoordinates(viewer.viewport.getCenter());
  const zoom = viewer.viewport.viewportToImageZoom(viewer.viewport.getZoom());
  const hash = `#${zoom.toFixed(3)}/${Math.round(center.x)}/${Math.round(center.y)}`;
  history.replaceState(null, "", hash);
}

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
});

window.addEventListener("hashchange", () => {
  const target = readHash();
  if (target) {
    goTo(target.x, target.y, target.zoom, false);
  }
});

function bindZoom(id: string, action: () => void): void {
  (document.getElementById(id) as HTMLButtonElement).addEventListener("click", action);
}

bindZoom("zoom-in", () => viewer.viewport.zoomBy(1.6).applyConstraints());
bindZoom("zoom-out", () => viewer.viewport.zoomBy(1 / 1.6).applyConstraints());
bindZoom("home", () => viewer.viewport.goHome());

const input = document.getElementById("search") as HTMLInputElement;
const results = document.getElementById("results") as HTMLUListElement;
let places: Place[] = [];

fetch(SEARCH_INDEX)
  .then((response) => response.json())
  .then((entries: Place[]) => {
    places = entries;
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
