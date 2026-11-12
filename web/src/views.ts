// Where a view's image sits on the ground: image pixels = matrix × ground meters + offset.
export interface Frame {
  matrix: [number, number, number, number];
  x_offset: number;
  y_offset: number;
}

export interface View extends Frame {
  pyramid: string;
  // Added to image pixels to give a link's pixels, which stay in the original Imphal canvas.
  hash_shift?: [number, number];
}

// The frame a link without a view names, and the one search and flow lines are written in.
// The site no longer shows it; links to it open in the nearest view it does show.
export const DEFAULT_VIEW = "0";

// Every view a shared link may name: the 24 the site had in 15 degree steps.
export const LINK_VIEWS = Array.from({ length: 24 }, (_, step) => String(step * 15));

// Links shared while the map had four named views.
export const FORMER_VIEWS: Record<string, string> = { nw: "0", sw: "90", se: "180", ne: "270" };

// The view whose screen-up is true north; the site opens in it.
export const NORTH_UP_VIEW = "315";

// The views the site shows, in turning order: each step turns the scene clockwise.
export function viewOrder(views: Record<string, View>): string[] {
  return Object.keys(views).sort((a, b) => Number(a) - Number(b));
}

// The shown view closest in angle to a link's view, north up when two are as close.
export function nearestView(name: string, shown: string[]): string {
  const apart = (other: string) => {
    const turn = Math.abs(Number(other) - Number(name)) % 360;
    return Math.min(turn, 360 - turn);
  };
  const closest = Math.min(...shown.map(apart));
  const ties = shown.filter((other) => apart(other) === closest);
  return ties.includes(NORTH_UP_VIEW) ? NORTH_UP_VIEW : (ties[0] ?? NORTH_UP_VIEW);
}

export function northAngle(view: View): number {
  const [a, b] = view.matrix;
  return (Math.atan2(b, a) * 180) / Math.PI;
}

export function convertPoint(x: number, y: number, from: Frame, to: Frame): [number, number] {
  const [a, b, d, e] = from.matrix;
  const screenX = x - from.x_offset;
  const screenY = y - from.y_offset;
  const determinant = a * e - b * d;
  const groundX = (e * screenX - b * screenY) / determinant;
  const groundY = (a * screenY - d * screenX) / determinant;
  const [toA, toB, toD, toE] = to.matrix;
  return [
    Math.round(toA * groundX + toB * groundY + to.x_offset),
    Math.round(toD * groundX + toE * groundY + to.y_offset),
  ];
}
