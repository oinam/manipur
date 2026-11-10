import OpenSeadragon from "openseadragon";

import { TILE_BASE } from "./tiles";

interface FlowLine {
  width: number;
  points: [number, number][];
}

interface Segment {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  start: number;
  length: number;
  normalX: number;
  normalY: number;
  width: number;
}

const FLOW_INDEX = `${TILE_BASE}flow.json`;
const MIN_IMAGE_ZOOM = 0.5;
const FRAME_MS = 125;
const GLINT = "#8db9cd";
const SHORE_MAP_PX = 3;
const MIN_WATER_BLUE_OVER_RED = 55;
const SHIMMER_CELL_X = 26;
const SHIMMER_CELL_Y = 13;
const SHIMMER_PERIOD_S = 3.2;
const FLOW_SPACING = 22;
const FLOW_SPEED = 14;
const FLOW_LANES = [-0.55, 0, 0.55];
const REBUILD_DELAY_MS = 200;
const MOTION_KEY = "water-motion";

function prefersMotion(): boolean {
  try {
    const saved = localStorage.getItem(MOTION_KEY);
    if (saved) {
      return saved === "on";
    }
  } catch {
    // Storage can be blocked; fall through to the system setting.
  }
  return !matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function saveMotion(enabled: boolean): void {
  try {
    localStorage.setItem(MOTION_KEY, enabled ? "on" : "off");
  } catch {
    // The choice just lasts for this visit.
  }
}

function context2d(canvas: HTMLCanvasElement): CanvasRenderingContext2D {
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Canvas 2D is unavailable");
  }
  return context;
}

function cellHash(x: number, y: number): number {
  let hash = Math.imul(x, 374761393) ^ Math.imul(y, 668265263);
  hash = Math.imul(hash ^ (hash >>> 13), 1274126177);
  return (hash ^ (hash >>> 16)) >>> 0;
}

function toSegments(lines: FlowLine[]): Segment[] {
  const segments: Segment[] = [];
  for (const line of lines) {
    let start = 0;
    for (const [index, [x1, y1]] of line.points.entries()) {
      const previous = line.points[index - 1];
      if (!previous) {
        continue;
      }
      const [x0, y0] = previous;
      const length = Math.hypot(x1 - x0, y1 - y0);
      if (length > 0) {
        segments.push({
          x0,
          y0,
          x1,
          y1,
          start,
          length,
          normalX: -(y1 - y0) / length,
          normalY: (x1 - x0) / length,
          width: line.width,
        });
        start += length;
      }
    }
  }
  return segments;
}

export function startWater(
  viewer: OpenSeadragon.Viewer,
  toggle: HTMLInputElement,
  toImage: (x: number, y: number) => [number, number],
): { refresh: () => void } {
  const source = (viewer.drawer as unknown as { canvas: HTMLCanvasElement }).canvas;
  const canvas = document.createElement("canvas");
  canvas.className = "water";
  source.after(canvas);
  const context = context2d(canvas);
  const mask = document.createElement("canvas");
  const sourceContext = context2d(source);

  let lines: FlowLine[] = [];
  let segments: Segment[] = [];
  let ready = false;
  let moving = false;
  let lastFrame = 0;
  let rebuildTimer = 0;
  let enabled = prefersMotion();
  toggle.checked = enabled;

  function imageZoom(): number {
    return viewer.viewport.viewportToImageZoom(viewer.viewport.getZoom(true));
  }

  function clear(): void {
    context.clearRect(0, 0, canvas.width, canvas.height);
  }

  function rebuildMask(): void {
    canvas.width = source.width;
    canvas.height = source.height;
    const zoom = imageZoom();
    ready = zoom >= MIN_IMAGE_ZOOM;
    if (!ready) {
      return;
    }
    const pixels = sourceContext.getImageData(0, 0, source.width, source.height).data;
    const step = Math.max(1, Math.round(source.width / source.clientWidth));
    const width = Math.floor(source.width / step);
    const height = Math.floor(source.height / step);
    const water = new Uint8Array(width * height);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const offset = (y * step * source.width + x * step) * 4;
        water[y * width + x] =
          (pixels[offset + 2] ?? 0) - (pixels[offset] ?? 0) >= MIN_WATER_BLUE_OVER_RED ? 1 : 0;
      }
    }
    // Windows are water-colored too; only open water survives this inset.
    const inset = Math.ceil(SHORE_MAP_PX * zoom);
    mask.width = width;
    mask.height = height;
    const maskContext = context2d(mask);
    const output = maskContext.createImageData(width, height);
    for (let y = inset; y < height - inset; y++) {
      for (let x = inset; x < width - inset; x++) {
        const index = y * width + x;
        if (
          water[index] &&
          water[index - inset] &&
          water[index + inset] &&
          water[index - inset * width] &&
          water[index + inset * width]
        ) {
          output.data[index * 4 + 3] = 255;
        }
      }
    }
    maskContext.putImageData(output, 0, 0);
  }

  function scheduleRebuild(): void {
    window.clearTimeout(rebuildTimer);
    rebuildTimer = window.setTimeout(() => {
      if (!moving) {
        rebuildMask();
      }
    }, REBUILD_DELAY_MS);
  }

  function drawShimmer(
    seconds: number,
    scale: number,
    originX: number,
    originY: number,
    left: number,
    top: number,
    right: number,
    bottom: number,
  ): void {
    const firstRow = Math.floor(top / SHIMMER_CELL_Y);
    const lastRow = Math.ceil(bottom / SHIMMER_CELL_Y);
    const firstColumn = Math.floor(left / SHIMMER_CELL_X);
    const lastColumn = Math.ceil(right / SHIMMER_CELL_X);
    for (let row = firstRow; row <= lastRow; row++) {
      for (let column = firstColumn; column <= lastColumn; column++) {
        const hash = cellHash(column, row);
        const phase = (seconds / SHIMMER_PERIOD_S + (hash & 255) / 255) % 1;
        if (phase < 0.35) {
          const x = column * SHIMMER_CELL_X + ((hash >>> 8) % SHIMMER_CELL_X);
          const y = row * SHIMMER_CELL_Y + ((hash >>> 16) % SHIMMER_CELL_Y);
          const length = 3 + ((hash >>> 24) % 3);
          context.fillRect(originX + x * scale, originY + y * scale, length * scale, scale);
        }
      }
    }
  }

  function drawFlow(
    seconds: number,
    scale: number,
    originX: number,
    originY: number,
    left: number,
    top: number,
    right: number,
    bottom: number,
  ): void {
    for (const segment of segments) {
      const reach = segment.width + FLOW_SPACING;
      if (
        Math.max(segment.x0, segment.x1) < left - reach ||
        Math.min(segment.x0, segment.x1) > right + reach ||
        Math.max(segment.y0, segment.y1) < top - reach ||
        Math.min(segment.y0, segment.y1) > bottom + reach
      ) {
        continue;
      }
      FLOW_LANES.forEach((lane, laneIndex) => {
        const shift = (seconds * FLOW_SPEED + laneIndex * 7) % FLOW_SPACING;
        const first = Math.ceil((segment.start - shift) / FLOW_SPACING);
        for (
          let dash = first;
          dash * FLOW_SPACING + shift < segment.start + segment.length;
          dash++
        ) {
          const along = (dash * FLOW_SPACING + shift - segment.start) / segment.length;
          const offset = lane * segment.width;
          const x = Math.round(
            segment.x0 + (segment.x1 - segment.x0) * along + segment.normalX * offset,
          );
          const y = Math.round(
            segment.y0 + (segment.y1 - segment.y0) * along + segment.normalY * offset * 0.5,
          );
          context.fillRect(originX + x * scale, originY + y * scale, 5 * scale, scale);
        }
      });
    }
  }

  function draw(now: number): void {
    requestAnimationFrame(draw);
    if (!enabled || moving || !ready || now - lastFrame < FRAME_MS) {
      return;
    }
    lastFrame = now;
    const zoom = imageZoom();
    const density = source.width / source.clientWidth;
    const scale = zoom * density;
    const origin = viewer.viewport.imageToViewerElementCoordinates(new OpenSeadragon.Point(0, 0));
    const originX = origin.x * density;
    const originY = origin.y * density;
    const left = -originX / scale;
    const top = -originY / scale;
    const right = left + canvas.width / scale;
    const bottom = top + canvas.height / scale;
    const seconds = now / 1000;

    clear();
    context.globalCompositeOperation = "source-over";
    context.fillStyle = GLINT;
    drawShimmer(seconds, scale, originX, originY, left, top, right, bottom);
    drawFlow(seconds, scale, originX, originY, left, top, right, bottom);
    context.globalCompositeOperation = "destination-in";
    context.imageSmoothingEnabled = false;
    context.drawImage(mask, 0, 0, canvas.width, canvas.height);
    context.globalCompositeOperation = "source-over";
  }

  toggle.addEventListener("change", () => {
    enabled = toggle.checked;
    saveMotion(enabled);
    if (!enabled) {
      clear();
    }
  });

  viewer.addHandler("animation-start", () => {
    moving = true;
    clear();
  });
  viewer.addHandler("animation-finish", () => {
    moving = false;
    scheduleRebuild();
  });
  viewer.addHandler("resize", scheduleRebuild);
  viewer.world.addHandler("add-item", scheduleRebuild);
  viewer.addHandler("tile-loaded", scheduleRebuild);

  function refresh(): void {
    segments = toSegments(
      lines.map((line) => ({
        width: line.width,
        points: line.points.map(([x, y]) => toImage(x, y)),
      })),
    );
    clear();
    scheduleRebuild();
  }

  fetch(FLOW_INDEX, { cache: "no-cache" })
    .then((response) => response.json())
    .then((loaded: FlowLine[]) => {
      lines = loaded;
      refresh();
    })
    .catch((error: unknown) => {
      console.error("Water flow lines failed to load", error);
    });

  scheduleRebuild();
  requestAnimationFrame(draw);
  return { refresh };
}
