import { expect, it } from "vitest";
import { cpuSlowdown } from "../scripts/cpu-profile.mjs";

it.each([
  [100, 1],
  [400, 1],
  [800, 2],
  [1600, 4],
  [2000, 5],
  [10000, 20],
])(
  "calibrates benchmark %s to the same mobile target",
  (benchmark, expected) => {
    expect(cpuSlowdown(benchmark)).toBe(expected);
  },
);
it.each([0, -1, NaN, Infinity])(
  "rejects an invalid benchmark %s",
  (benchmark) => {
    expect(() => cpuSlowdown(benchmark)).toThrow("positive CPU benchmark");
  },
);
