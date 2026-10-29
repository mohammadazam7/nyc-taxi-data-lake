/** Atlas design tokens: the one place colours, type and motion are defined. */
export const atlas = {
  color: {
    void: "#0a0d14",
    panel: "#111622",
    raised: "#151b29",
    line: "#232b3d",
    ink: "#e8ecf4",
    muted: "#8b95a8",
    dim: "#5d677a",
    demand: "#f7b733",
    heat: "#fc4a1a",
    system: "#4fa3ff",
    health: "#36d39a",
    violet: "#8b5cf6",
    rose: "#e86fa8",
  },
  font: {
    sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
  },
  motion: { ease: "power3.out", enter: 0.9, stagger: 0.035 },
} as const;

/** Low to high demand: deep blue through electric blue to amber and heat. */
export const demandRamp: readonly (readonly [number, number, number])[] = [
  [24, 40, 74],
  [53, 99, 178],
  [79, 163, 255],
  [247, 183, 51],
  [252, 74, 26],
];

export function rampColor(t: number): [number, number, number] {
  const stops = demandRamp;
  const x = Math.max(0, Math.min(1, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const f = x - i;
  const a = stops[i]!;
  const b = stops[i + 1]!;
  return [0, 1, 2].map((j) => (a[j]! + (b[j]! - a[j]!) * f) / 255) as [number, number, number];
}
