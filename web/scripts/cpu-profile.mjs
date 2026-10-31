// 1600 reference desktop benchmark / Lighthouse's default 4x = 400 mobile target.
export function cpuSlowdown(benchmark) {
  if (!Number.isFinite(benchmark) || benchmark <= 0)
    throw new Error("Lighthouse must provide a positive CPU benchmark index");
  return Math.round(Math.max(1, Math.min(20, benchmark / 400)) * 100) / 100;
}
