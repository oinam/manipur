import OpenSeadragon from "openseadragon";

import { toImage } from "./aircraft";
import type { View } from "./views";

// A few small herds of Sangai, the brow-antlered deer of Keibul Lamjao, wandering the park.
// They are illustrative, not tracked: each deer grazes for a while, then walks to a nearby
// spot inside the park. Drawn at three times real size with a dark edge, the style
// Brajeshwar chose from out/loktak/sangai-options.png, and only when zoomed in enough to
// make out. With Animation off they stand still.

type LonLat = [number, number];

interface Deer {
  stag: boolean;
  lon: number;
  lat: number;
  goal: LonLat;
  grazeUntil: number; // milliseconds; walking once past it
  facingLeft: boolean;
  phase: number; // milliseconds, to stagger the walking steps
}

// Keibul Lamjao National Park, OSM way 666320344, simplified.
const PARK: LonLat[] = [
  [93.8174, 24.468],
  [93.8177, 24.4732],
  [93.8145, 24.4796],
  [93.8228, 24.486],
  [93.8259, 24.4915],
  [93.8294, 24.4954],
  [93.8291, 24.4987],
  [93.8224, 24.5043],
  [93.8228, 24.5075],
  [93.8283, 24.5101],
  [93.8294, 24.5125],
  [93.828, 24.5158],
  [93.8585, 24.5277],
  [93.8672, 24.5148],
  [93.8674, 24.5116],
  [93.8719, 24.5037],
  [93.8714, 24.4992],
  [93.8734, 24.4947],
  [93.8756, 24.4925],
  [93.8783, 24.492],
  [93.8768, 24.49],
  [93.8773, 24.488],
  [93.875, 24.488],
  [93.8681, 24.477],
  [93.8646, 24.4776],
  [93.8609, 24.4833],
  [93.8576, 24.4898],
  [93.8584, 24.4923],
  [93.8603, 24.4937],
  [93.8588, 24.4955],
  [93.859, 24.4971],
  [93.8581, 24.4987],
  [93.856, 24.4979],
  [93.8538, 24.4907],
  [93.8551, 24.4883],
  [93.8555, 24.4833],
  [93.857, 24.4777],
  [93.8559, 24.4691],
  [93.8526, 24.4648],
  [93.8492, 24.4559],
  [93.8512, 24.4511],
  [93.8499, 24.4488],
  [93.8468, 24.4469],
  [93.8455, 24.4452],
  [93.8423, 24.4449],
  [93.8421, 24.4426],
  [93.8401, 24.4416],
  [93.8359, 24.4434],
  [93.8213, 24.4415],
  [93.821, 24.446],
  [93.8169, 24.4515],
  [93.8159, 24.4578],
  [93.8225, 24.4605],
  [93.8234, 24.4652],
];
// Herds gather near the Sangai viewpoint (OSM, 24.473 N 93.8167 E), where visitors watch.
const HERDS: LonLat[] = [
  [93.8205, 24.4735],
  [93.8225, 24.47],
  [93.8212, 24.4772],
  [93.8258, 24.4745],
  [93.8265, 24.4665],
];
// The Keibul Lamjao shortcut centers on the herd nearest the viewpoint.
export const SANGAI_HERD: LonLat = HERDS[0] ?? [93.8205, 24.4735];
const HERD_SIZE = 6;
const HERD_RADIUS_M = 140;
const WANDER_M = 45;
const WALK_MPS = 1.1;
const GRAZE_MS = [8_000, 40_000];
const STEP_MS = 260;
const MIN_IMAGE_ZOOM = 0.45;
const METERS_PER_DEGREE = 111_320;
const COS_LAT = Math.cos((24.48 * Math.PI) / 180);
const SEED = 1891; // fixed, so every visit starts with the same herds

// The 3x sprites from tools/sangai_options.py, facing right, two walking frames each.
const COLORS: Record<string, string> = {
  b: "#a05940",
  d: "#5a3c35",
  w: "#eee6db",
  a: "#e8dfb8",
  o: "#1f2a2e",
};
const STAG = [
  [
    "........a..a",
    ".......a..a.",
    "........aa..",
    ".........bb.",
    "........bbbb",
    "........bd..",
    "wbbbbbbbbd..",
    "wbbbbbbbb...",
    ".wddddddd...",
    ".d.d...d.d..",
    ".d.d...d.d..",
  ],
  [
    "........a..a",
    ".......a..a.",
    "........aa..",
    ".........bb.",
    "........bbbb",
    "........bd..",
    "wbbbbbbbbd..",
    "wbbbbbbbb...",
    ".wddddddd...",
    "..dd....dd..",
    ".d..d..d..d.",
  ],
];
const HIND = [
  [
    "........b.",
    ".......bbb",
    ".......bd.",
    "wbbbbbbbd.",
    "wbbbbbbb..",
    ".wdddddd..",
    ".d.d..d.d.",
    ".d.d..d.d.",
  ],
  [
    "........b.",
    ".......bbb",
    ".......bd.",
    "wbbbbbbbd.",
    "wbbbbbbb..",
    ".wdddddd..",
    "..dd...dd.",
    ".d..d.d..d",
  ],
];

function random(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4_294_967_296;
  };
}

function inside([lon, lat]: LonLat): boolean {
  let within = false;
  for (let index = 0, previous = PARK.length - 1; index < PARK.length; previous = index++) {
    const [x1, y1] = PARK[index] ?? [0, 0];
    const [x2, y2] = PARK[previous] ?? [0, 0];
    if (y1 > lat !== y2 > lat && lon < ((x2 - x1) * (lat - y1)) / (y2 - y1) + x1) {
      within = !within;
    }
  }
  return within;
}

function near(center: LonLat, radiusM: number, roll: () => number): LonLat {
  for (let attempt = 0; attempt < 20; attempt++) {
    const angle = roll() * 2 * Math.PI;
    const distance = Math.sqrt(roll()) * radiusM;
    const spot: LonLat = [
      center[0] + (Math.cos(angle) * distance) / (METERS_PER_DEGREE * COS_LAT),
      center[1] + (Math.sin(angle) * distance) / METERS_PER_DEGREE,
    ];
    if (inside(spot)) {
      return spot;
    }
  }
  return center;
}

// Draws a sprite with a one-pixel dark edge onto its own small canvas.
function spriteCanvas(rows: string[], mirrored: boolean): HTMLCanvasElement {
  const width = (rows[0]?.length ?? 0) + 2;
  const height = rows.length + 2;
  const filled = (x: number, y: number) => (rows[y - 1]?.[x - 1] ?? ".") !== ".";
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    return canvas;
  }
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let cell = rows[y - 1]?.[x - 1] ?? ".";
      if (
        cell === "." &&
        [filled(x - 1, y), filled(x + 1, y), filled(x, y - 1), filled(x, y + 1)].some(Boolean)
      ) {
        cell = "o";
      }
      const color = COLORS[cell];
      if (color) {
        context.fillStyle = color;
        context.fillRect(mirrored ? width - 1 - x : x, y, 1, 1);
      }
    }
  }
  return canvas;
}

function makeHerds(now: number): Deer[] {
  const roll = random(SEED);
  return HERDS.flatMap((center) =>
    Array.from({ length: HERD_SIZE }, (_, index) => {
      const [lon, lat] = near(center, HERD_RADIUS_M, roll);
      return {
        stag: index === 0 || roll() < 0.2,
        lon,
        lat,
        goal: [lon, lat] as LonLat,
        grazeUntil: now + roll() * (GRAZE_MS[1] ?? 0),
        facingLeft: roll() < 0.5,
        phase: roll() * STEP_MS * 2,
      };
    }),
  );
}

export function startSangai(
  viewer: OpenSeadragon.Viewer,
  currentView: () => View,
  animation: HTMLInputElement,
): void {
  const source = (viewer.drawer as unknown as { canvas: HTMLCanvasElement }).canvas;
  const canvas = document.createElement("canvas");
  canvas.className = "sangai";
  source.after(canvas);
  const context = canvas.getContext("2d");
  if (!context) {
    return;
  }
  const draw2d = context;
  const sprites = {
    stag: [false, true].map((mirrored) => STAG.map((rows) => spriteCanvas(rows, mirrored))),
    hind: [false, true].map((mirrored) => HIND.map((rows) => spriteCanvas(rows, mirrored))),
  };
  const roll = random(SEED + 1);
  const herd = makeHerds(Date.now());
  let last = Date.now();

  function move(deer: Deer, now: number, seconds: number): boolean {
    if (now < deer.grazeUntil) {
      return false;
    }
    const dx = (deer.goal[0] - deer.lon) * COS_LAT * METERS_PER_DEGREE;
    const dy = (deer.goal[1] - deer.lat) * METERS_PER_DEGREE;
    const left = Math.hypot(dx, dy);
    const step = WALK_MPS * seconds;
    if (left <= step) {
      deer.lon = deer.goal[0];
      deer.lat = deer.goal[1];
      const [shortest = 0, longest = 0] = GRAZE_MS;
      deer.grazeUntil = now + shortest + roll() * (longest - shortest);
      deer.goal = near([deer.lon, deer.lat], WANDER_M, roll);
      return false;
    }
    deer.lon += (dx / left) * (step / (COS_LAT * METERS_PER_DEGREE));
    deer.lat += (dy / left) * (step / METERS_PER_DEGREE);
    return true;
  }

  function draw(): void {
    requestAnimationFrame(draw);
    const now = Date.now();
    const seconds = Math.min(1, (now - last) / 1000);
    last = now;
    if (canvas.width !== source.width || canvas.height !== source.height) {
      canvas.width = source.width;
      canvas.height = source.height;
    }
    draw2d.clearRect(0, 0, canvas.width, canvas.height);
    const density = source.width / source.clientWidth;
    const imageZoom = viewer.viewport.viewportToImageZoom(viewer.viewport.getZoom(true));
    const moving = animation.checked;
    const view = currentView();
    const scale = imageZoom * density;
    const origin = viewer.viewport.imageToViewerElementCoordinates(new OpenSeadragon.Point(0, 0));
    draw2d.imageSmoothingEnabled = false;
    // Farther deer first, so nearer ones stand in front.
    const placed = herd
      .map((deer) => {
        const walking = moving && move(deer, now, seconds);
        const [x, y] = toImage(view, deer.lon, deer.lat);
        return { deer, walking, x, y };
      })
      .sort((a, b) => a.y - b.y);
    if (imageZoom < MIN_IMAGE_ZOOM) {
      return;
    }
    for (const { deer, walking, x, y } of placed) {
      const screenX = origin.x * density + x * scale;
      const screenY = origin.y * density + y * scale;
      if (
        screenX < -50 ||
        screenY < -50 ||
        screenX > canvas.width + 50 ||
        screenY > canvas.height + 50
      ) {
        continue;
      }
      if (walking) {
        const ahead = toImage(view, deer.goal[0], deer.goal[1]);
        deer.facingLeft = ahead[0] < x;
      }
      const frame = walking ? Math.floor((now + deer.phase) / STEP_MS) % 2 : 0;
      const sprite = sprites[deer.stag ? "stag" : "hind"][deer.facingLeft ? 1 : 0]?.[frame];
      if (sprite) {
        // Feet on the spot: the sprite's bottom middle.
        draw2d.drawImage(
          sprite,
          Math.round(screenX - (sprite.width * scale) / 2),
          Math.round(screenY - sprite.height * scale),
          Math.round(sprite.width * scale),
          Math.round(sprite.height * scale),
        );
      }
    }
  }

  requestAnimationFrame(draw);
}
