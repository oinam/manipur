export interface View {
  pyramid: string;
  matrix: [number, number, number, number];
  x_offset: number;
  y_offset: number;
}

export const DEFAULT_VIEW = "0";

// Each step turns the scene clockwise on screen.
export const VIEW_ORDER = Array.from({ length: 24 }, (_, step) => String(step * 15));

// Links shared while the map had four named views.
export const FORMER_VIEWS: Record<string, string> = { nw: "0", sw: "90", se: "180", ne: "270" };

export function convertPoint(x: number, y: number, from: View, to: View): [number, number] {
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
