const TARGET_TICKS = 4;
const NICE_STEPS = [1, 2, 5, 10];

/** SVG path through the points (xs[i], ys[i]). */
export const linePath = (xs: number[], ys: number[]): string =>
  xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${(ys[i] ?? 0).toFixed(1)}`).join(" ");

/** Evenly spaced round values (1, 2 or 5 times a power of ten) that cover [bottom, top]. */
export function niceTicks(bottom: number, top: number): { values: number[]; step: number } {
  const raw = (top - bottom) / TARGET_TICKS;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = (NICE_STEPS.find((n) => n * magnitude >= raw) ?? 10) * magnitude;
  const first = Math.ceil(bottom / step);
  const count = Math.floor(top / step) - first + 1;
  return { values: Array.from({ length: Math.max(count, 0) }, (_, i) => (first + i) * step), step };
}
