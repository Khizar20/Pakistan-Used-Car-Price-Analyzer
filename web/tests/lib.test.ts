import { beforeEach, describe, expect, it, vi } from "vitest";
import { money, percent, date, observedDays } from "../src/lib/format";
import { headline } from "../src/lib/headline";
import { cohortIndex } from "../src/lib/cohorts";
import { fairPrice, verdict } from "../src/lib/fairPrice";
import {
  coherent,
  validate,
  loadBundle,
  clearCache,
  keys,
} from "../src/lib/data";
import type { Bundle } from "../src/lib/data";
import type { Car } from "../src/lib/fairPrice";
import references from "./fixtures/fair-reference.json";
import meta from "./fixtures/meta.json";
import index from "./fixtures/index.json";
import drops from "./fixtures/drops.json";
import seasonality from "./fixtures/seasonality.json";
import drivers from "./fixtures/drivers.json";
import fairprice from "./fixtures/fairprice.json";
import models from "./fixtures/models.json";
import listings_sample from "./fixtures/listings_sample.json";

export const populated: Bundle = {
  meta: validate("meta", meta),
  index: validate("index", index),
  drops: validate("drops", drops),
  seasonality: validate("seasonality", seasonality),
  drivers: validate("drivers", drivers),
  fairprice: validate("fairprice", fairprice),
  models: validate("models", models),
  listings_sample: validate("listings_sample", listings_sample),
};
const model = validate("fairprice", fairprice).data.model!;
const car = references.references[0].car;
describe("formats and truthful headlines", () => {
  it("formats all money ranges and missing values", () => {
    expect(money(3500000)).toBe("PKR 35 lakh");
    expect(money(12500000)).toBe("PKR 1.25 crore");
    expect(money(3500000, true)).toBe("PKR 3,500,000");
    expect(money(0)).toBe("PKR 0");
    expect(money(null)).toBe("Not available");
    expect(money(NaN)).toBe("Not available");
    expect(percent(null)).toBe("Not available");
    expect(percent(Infinity)).toBe("Not available");
    expect(percent(1.25)).toBe("1.3%");
    expect(date(null)).toBe("Not available");
    expect(date("bad")).toBe("Not available");
    expect(date("2026-10-25")).toContain("2026");
    expect(observedDays("2026-10-24", "2026-10-25")).toBe(2);
    expect(observedDays(null, null)).toBe(0);
    expect(observedDays("bad", "bad")).toBe(0);
    expect(observedDays("2026-10-25", "2026-10-24")).toBe(0);
  });
  it("distinguishes rising, falling, flat and unavailable", () => {
    const points = [
      { week: "a", value: 100 },
      { week: "b", value: 98 },
    ];
    expect(headline(points, true)).toContain("fell 2.0%");
    expect(
      headline([{ ...points[0] }, { ...points[1], value: 102 }], true),
    ).toContain("rose 2.0%");
    expect(headline([points[0], points[0]], true)).toContain("steady");
    expect(headline([], false)).toContain("more observations");
    expect(headline([{ week: "a", value: 0 }, points[0]], true)).toContain(
      "more observations",
    );
  });
});
describe("cohort chains", () => {
  const row = {
    make: "Honda",
    model: "Civic",
    model_year: 2020,
    listings: 5,
    median_price_pkr: 100,
    week: "2025-01-06",
  };
  it("recovers a weighted matched link and refuses missing support", () => {
    expect(
      cohortIndex(
        [row, { ...row, week: "2025-01-13", median_price_pkr: 90 }],
        "Honda / Civic",
      )[1].value,
    ).toBe(90);
    expect(cohortIndex([], "Honda / Civic")).toEqual([]);
    expect(
      cohortIndex([row, { ...row, week: "2025-01-20" }], "Honda / Civic"),
    ).toEqual([]);
    expect(
      cohortIndex(
        [row, { ...row, week: "2025-01-13", model_year: 2019 }],
        "Honda / Civic",
      ),
    ).toEqual([]);
    expect(
      cohortIndex(
        [
          { ...row, median_price_pkr: 0 },
          { ...row, week: "2025-01-13" },
        ],
        "Honda / Civic",
      ),
    ).toEqual([]);
  });
});
describe("Python/browser Fair Price parity", () => {
  it.each(references.references.map((row, i) => [i, row] as const))(
    "matches reference %i",
    (_i, row) => {
      const actual = fairPrice(row.car, model);
      expect(actual.estimate / row.estimate_pkr).toBeCloseTo(1, 10);
      expect(actual.lower / row.lower_pkr).toBeCloseTo(1, 10);
      expect(actual.upper / row.upper_pkr).toBeCloseTo(1, 10);
    },
  );
  it("rejects unsupported inputs and unstable models", () => {
    expect(() => fairPrice({ ...car, mileage_km: -1 }, model)).toThrow(
      "between",
    );
    expect(() => fairPrice({ ...car, city: "Unknown" }, model)).toThrow(
      "supported",
    );
    expect(() => fairPrice({ ...car, model_year: NaN }, model)).toThrow(
      "between",
    );
    expect(() =>
      fairPrice(car, { ...model, spec: { ...model.spec, terms: ["missing"] } }),
    ).toThrow("cannot evaluate");
    expect(() =>
      fairPrice(car, {
        ...model,
        coefficients: { ...model.coefficients, intercept: 1000 },
      }),
    ).toThrow("outside");
    expect(verdict(50, 100)).toContain("Below");
    expect(verdict(150, 100)).toContain("Above");
    expect(verdict(100, 100)).toContain("Near");
    expect(
      fairPrice({ ...car, engine_cc: model.defaults.engine_cc } as Car, model)
        .estimate,
    ).toBeGreaterThan(0);
  });
});
describe("schema validation and snapshot loading", () => {
  beforeEach(clearCache);
  it("validates every schema and checks bundle coherence", () => {
    for (const key of keys)
      expect(validate(key, populated[key])).toEqual(populated[key]);
    expect(() => validate("meta", { ...meta, schema_version: "2.0" })).toThrow(
      "format",
    );
    expect(() =>
      validate("meta", { ...meta, generated_at: "not a date" }),
    ).toThrow("format");
    expect(coherent(populated)).toBe(populated);
    expect(() =>
      validate("fairprice", {
        ...fairprice,
        data: {
          ...fairprice.data,
          model: {
            ...fairprice.data.model,
            spec: { ...fairprice.data.model.spec, categories: {} },
          },
        },
      }),
    ).toThrow("incomplete");
    expect(() =>
      validate("fairprice", {
        ...fairprice,
        data: {
          ...fairprice.data,
          model: { ...fairprice.data.model, ranges: {} },
        },
      }),
    ).toThrow("incomplete");
    expect(() =>
      validate("fairprice", {
        ...fairprice,
        data: {
          ...fairprice.data,
          model: { ...fairprice.data.model, defaults: {} },
        },
      }),
    ).toThrow("incomplete");
    expect(
      validate("fairprice", {
        ...fairprice,
        data: {
          status: "insufficient_data",
          reason: "Not enough cars",
          model: null,
        },
      }).data.model,
    ).toBeNull();
    expect(() =>
      coherent({
        ...populated,
        meta: { ...meta, bundle_id: "a".repeat(64) },
      } as Bundle),
    ).toThrow("refreshed");
  });
  it("caches a verified load and retries after HTTP/JSON/mixed failures", async () => {
    const fetcher = vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        json: async () =>
          populated[keys.find((key) => url.endsWith(`${key}.json`))!],
      }),
    );
    vi.stubGlobal("fetch", fetcher);
    const first = loadBundle();
    expect(loadBundle()).toBe(first);
    expect(await first).toEqual(populated);
    expect(fetcher).toHaveBeenCalledTimes(8);
    clearCache();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false })),
    );
    await expect(loadBundle()).rejects.toThrow("connection");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, json: async () => ({}) })),
    );
    await expect(loadBundle()).rejects.toThrow("format");
    vi.stubGlobal("fetch", fetcher);
    expect(await loadBundle()).toEqual(populated);
  });
});
