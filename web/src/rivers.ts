import OpenSeadragon from "openseadragon";

import { TILE_BASE } from "./tiles";

// River names that ride along their rivers. Each named river gets one label, set on the
// point of the river nearest the middle of the screen and turned to follow it, so the
// label slides along the river as the map pans and stays on the stretch in view.

interface FlowLine {
  name?: string;
  points: [number, number][];
}

interface River {
  name: string;
  lines: [number, number][][]; // in the default view's image pixels, as loaded
  shown: [number, number][][]; // in the current view's image pixels
  element: HTMLDivElement;
}

const FLOW_INDEX = `${TILE_BASE}flow.json`;
// Below this the whole valley is on screen and the names would crowd it.
const MIN_IMAGE_ZOOM = 0.06;
// Kept this far inside the edges of the map, in screen pixels.
const EDGE_PX = 60;
// Two rivers' labels closer than this, the second waits until they part.
const CLEARANCE_PX = 140;

// The point on a segment nearest p, and how far along the segment it is.
function nearestOnSegment(
  p: [number, number],
  a: [number, number],
  b: [number, number],
): [number, number] {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const length = dx * dx + dy * dy;
  const t = length > 0 ? ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length : 0;
  const share = Math.min(1, Math.max(0, t));
  return [a[0] + dx * share, a[1] + dy * share];
}

// The point of the river nearest p, with the direction of the river there in degrees.
function nearest(p: [number, number], lines: [number, number][][]): [number, number, number] {
  let best: [number, number, number] = [NaN, NaN, 0];
  let bestDistance = Infinity;
  for (const line of lines) {
    for (let index = 1; index < line.length; index++) {
      const a = line[index - 1];
      const b = line[index];
      if (!a || !b) {
        continue;
      }
      const [x, y] = nearestOnSegment(p, a, b);
      const distance = (x - p[0]) ** 2 + (y - p[1]) ** 2;
      if (distance < bestDistance) {
        bestDistance = distance;
        best = [x, y, (Math.atan2(b[1] - a[1], b[0] - a[0]) * 180) / Math.PI];
      }
    }
  }
  return best;
}

// Turned to read left to right, never upside down.
function upright(degrees: number): number {
  if (degrees > 90) {
    return degrees - 180;
  }
  if (degrees < -90) {
    return degrees + 180;
  }
  return degrees;
}

export function startRivers(
  viewer: OpenSeadragon.Viewer,
  toImage: (x: number, y: number) => [number, number],
): { refresh: () => void } {
  const source = (viewer.drawer as unknown as { canvas: HTMLCanvasElement }).canvas;
  const layer = document.createElement("div");
  layer.className = "rivers";
  source.after(layer);
  let rivers: River[] = [];

  function place(): void {
    const imageZoom = viewer.viewport.viewportToImageZoom(viewer.viewport.getZoom(true));
    const tooFar = imageZoom < MIN_IMAGE_ZOOM;
    const width = layer.clientWidth;
    const height = layer.clientHeight;
    const center = viewer.viewport.viewportToImageCoordinates(viewer.viewport.getCenter(true));
    const placed: [number, number][] = [];
    for (const river of rivers) {
      const [x, y, degrees] = nearest([center.x, center.y], river.shown);
      const point = viewer.viewport.imageToViewerElementCoordinates(new OpenSeadragon.Point(x, y));
      const inside =
        point.x > EDGE_PX &&
        point.y > EDGE_PX &&
        point.x < width - EDGE_PX &&
        point.y < height - EDGE_PX;
      const clear = placed.every(
        ([otherX, otherY]) => Math.hypot(otherX - point.x, otherY - point.y) > CLEARANCE_PX,
      );
      const show = !tooFar && inside && clear;
      river.element.hidden = !show;
      if (show) {
        placed.push([point.x, point.y]);
        river.element.style.transform =
          `translate(${point.x.toFixed(1)}px, ${point.y.toFixed(1)}px) ` +
          `translate(-50%, -50%) rotate(${upright(degrees).toFixed(1)}deg)`;
      }
    }
  }

  // Back into the open view's pixels, after loading or turning the map.
  function refresh(): void {
    for (const river of rivers) {
      river.shown = river.lines.map((line) => line.map(([x, y]) => toImage(x, y)));
    }
    place();
  }

  viewer.addHandler("update-viewport", place);
  viewer.addHandler("resize", place);

  fetch(FLOW_INDEX, { cache: "no-cache" })
    .then((response) => response.json())
    .then((loaded: FlowLine[]) => {
      const byName = new Map<string, [number, number][][]>();
      for (const line of loaded) {
        if (line.name) {
          byName.set(line.name, [...(byName.get(line.name) ?? []), line.points]);
        }
      }
      // Longest first, so the main rivers win when two labels would meet.
      const length = (lines: [number, number][][]) =>
        lines.reduce(
          (sum, line) =>
            sum +
            line.slice(1).reduce((part, [x, y], index) => {
              const [px = x, py = y] = line[index] ?? [];
              return part + Math.hypot(x - px, y - py);
            }, 0),
          0,
        );
      rivers = [...byName]
        .sort(([, a], [, b]) => length(b) - length(a))
        .map(([name, lines]) => {
          const element = document.createElement("div");
          element.className = "label river";
          element.textContent = name;
          element.hidden = true;
          layer.append(element);
          return { name, lines, shown: lines, element };
        });
      refresh();
    })
    .catch((error: unknown) => {
      console.error("River names failed to load", error);
    });

  return { refresh };
}
