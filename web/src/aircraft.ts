import OpenSeadragon from "openseadragon";

import { toUtm } from "./utm";
import type { View } from "./views";

export interface Aircraft {
  callsign: string;
  lon: number;
  lat: number;
  altitude: number; // meters above the field
  track: number; // degrees clockwise from north
}

export interface Snapshot {
  time: number; // milliseconds since the epoch
  aircraft: Aircraft[];
}

// Two snapshots around the moment being shown; planes move between them.
export interface Feed {
  load(time: number): Promise<[Snapshot, Snapshot] | null>;
  label: string;
}

type Point = [number, number];

const DELAY_MS = 120_000;
const RELOAD_MS = 5_000;
const LIFT = Math.sqrt(3); // screen pixels per meter of height, as the buildings use
const SCALE = 2; // style C: twice real size
const SHADOW = "rgba(31, 42, 46, 0.43)";
const EDGE = "#1f2a2e";
const LIT = "#e6dccb";
const SHADE = "#8f8a94";
const ENGINE = "#4b4d57";
const FIN = "#b5533c";
const TEXT = "#e8dfb8";

// An A320-sized airliner in meters: (forward, right), with the fuselage 4 m tall.
const FUSELAGE: Point[] = [
  [18.8, 0],
  [16.5, 2],
  [-13, 2],
  [-18.6, 0.5],
  [-18.6, -0.5],
  [-13, -2],
  [16.5, -2],
];
const WING: Point[] = [
  [3, 2],
  [-6.5, 17.9],
  [-8.6, 17.9],
  [-4.5, 2],
];
const TAILPLANE: Point[] = [
  [-13.5, 1.5],
  [-17, 6.2],
  [-18.4, 6.2],
  [-17.4, 1.5],
];
const NACELLE: Point[] = [
  [3.2, 4.7],
  [3.2, 6.7],
  [-1.2, 6.7],
  [-1.2, 4.7],
];
const FIN_SHAPE: Point[] = [
  [-12, 4],
  [-18.6, 4],
  [-18.9, 11.8],
  [-16, 11.8],
]; // (forward, up) along the centerline

function mirror(points: Point[]): Point[] {
  return points.map(([forward, right]) => [forward, -right]);
}

function lerpAngle(from: number, to: number, amount: number): number {
  const turn = ((((to - from) % 360) + 540) % 360) - 180;
  return from + turn * amount;
}

function between(first: Snapshot, second: Snapshot, time: number): Aircraft[] {
  const span = second.time - first.time;
  const amount = span > 0 ? Math.min(1, Math.max(0, (time - first.time) / span)) : 0;
  const next = new Map(second.aircraft.map((plane) => [plane.callsign, plane]));
  return first.aircraft.flatMap((plane) => {
    const later = next.get(plane.callsign);
    if (!later) {
      return [];
    }
    return [
      {
        callsign: plane.callsign,
        lon: plane.lon + (later.lon - plane.lon) * amount,
        lat: plane.lat + (later.lat - plane.lat) * amount,
        altitude: plane.altitude + (later.altitude - plane.altitude) * amount,
        track: lerpAngle(plane.track, later.track, amount),
      },
    ];
  });
}

export function startAircraft(
  viewer: OpenSeadragon.Viewer,
  currentView: () => View,
  feed: Feed,
): void {
  const source = (viewer.drawer as unknown as { canvas: HTMLCanvasElement }).canvas;
  const canvas = document.createElement("canvas");
  canvas.className = "aircraft";
  source.after(canvas);
  const context = canvas.getContext("2d");
  if (!context) {
    return;
  }
  const draw2d = context;
  let pair: [Snapshot, Snapshot] | null = null;

  function reload(): void {
    feed
      .load(Date.now() - DELAY_MS)
      .then((loaded) => {
        pair = loaded;
      })
      .catch((error: unknown) => {
        console.error("Aircraft failed to load", error);
      });
  }

  // Ground meters to the current view's image pixels, lifted by height.
  function imagePoint(x: number, y: number, height: number): Point {
    const view = currentView();
    const [a, b, d, e] = view.matrix;
    return [a * x + b * y + view.x_offset, d * x + e * y + view.y_offset - height * LIFT];
  }

  function drawPlane(plane: Aircraft, toScreen: (point: Point) => Point, density: number): void {
    const [x, y] = toUtm(plane.lon, plane.lat);
    const heading = (plane.track * Math.PI) / 180;
    const sin = Math.sin(heading);
    const cos = Math.cos(heading);
    const place = (forward: number, right: number, up: number, shadow = false): Point => {
      const f = forward * SCALE;
      const r = right * SCALE;
      const height = shadow ? 0 : plane.altitude + up * SCALE;
      return toScreen(imagePoint(x + f * sin + r * cos, y + f * cos - r * sin, height));
    };
    const polygon = (points: Point[], up: number, fill: string, shadow = false): void => {
      draw2d.beginPath();
      for (const [forward, right] of points) {
        const [screenX, screenY] = place(forward, right, up, shadow);
        draw2d.lineTo(screenX, screenY);
      }
      draw2d.closePath();
      draw2d.fillStyle = fill;
      draw2d.fill();
      if (!shadow) {
        draw2d.stroke();
      }
    };

    for (const part of [FUSELAGE, WING, mirror(WING), TAILPLANE, mirror(TAILPLANE)]) {
      polygon(part, 0, SHADOW, true);
    }

    // The side nearer the viewer is the one lower on screen; it is drawn last.
    const near = place(0, 2, 0)[1] > place(0, -2, 0)[1] ? 1 : -1;
    const side = (points: Point[]): Point[] => (near > 0 ? points : mirror(points));
    const far = (points: Point[]): Point[] => (near > 0 ? mirror(points) : points);
    draw2d.strokeStyle = EDGE;
    draw2d.lineWidth = 1;
    polygon(far(TAILPLANE), 3.4, SHADE);
    polygon(far(NACELLE), 0.2, ENGINE);
    polygon(far(WING), 1.2, SHADE);
    const wall = FUSELAGE.filter(([, right]) => right * near >= 0).sort(([a], [b]) => b - a);
    draw2d.beginPath();
    for (const [forward, right] of wall) {
      draw2d.lineTo(...place(forward, right, 0));
    }
    for (const [forward, right] of [...wall].reverse()) {
      draw2d.lineTo(...place(forward, right, 4));
    }
    draw2d.closePath();
    draw2d.fillStyle = SHADE;
    draw2d.fill();
    draw2d.stroke();
    polygon(FUSELAGE, 4, LIT);
    draw2d.beginPath();
    for (const [forward, up] of FIN_SHAPE) {
      draw2d.lineTo(...place(forward, 0, up));
    }
    draw2d.closePath();
    draw2d.fillStyle = FIN;
    draw2d.fill();
    draw2d.stroke();
    polygon(side(NACELLE), 0.2, ENGINE);
    polygon(side(WING), 1.2, SHADE);
    polygon(side(TAILPLANE), 3.4, SHADE);

    // The label sits above the fin, outlined so it reads over roofs and fields.
    const [labelX, labelY] = place(0, 0, 18);
    const text = `${plane.callsign} · ${feed.label}`;
    draw2d.lineWidth = 3 * density;
    draw2d.lineJoin = "round";
    draw2d.strokeText(text, labelX, labelY);
    draw2d.fillStyle = TEXT;
    draw2d.fillText(text, labelX, labelY);
  }

  function draw(): void {
    requestAnimationFrame(draw);
    if (canvas.width !== source.width || canvas.height !== source.height) {
      canvas.width = source.width;
      canvas.height = source.height;
    }
    draw2d.clearRect(0, 0, canvas.width, canvas.height);
    if (!pair) {
      return;
    }
    const density = source.width / source.clientWidth;
    const zoom = viewer.viewport.viewportToImageZoom(viewer.viewport.getZoom(true)) * density;
    const origin = viewer.viewport.imageToViewerElementCoordinates(new OpenSeadragon.Point(0, 0));
    const toScreen = ([x, y]: Point): Point => [
      origin.x * density + x * zoom,
      origin.y * density + y * zoom,
    ];
    draw2d.font = `600 ${String(Math.round(12 * density))}px system-ui, sans-serif`;
    draw2d.textAlign = "center";
    for (const plane of between(pair[0], pair[1], Date.now() - DELAY_MS)) {
      drawPlane(plane, toScreen, density);
    }
  }

  reload();
  window.setInterval(reload, RELOAD_MS);
  requestAnimationFrame(draw);
}
