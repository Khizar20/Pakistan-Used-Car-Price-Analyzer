import type {
  MetaExport,
  IndexExport,
  DropsExport,
  SeasonalityExport,
  DriversExport,
  FairPriceExport,
  ModelsExport,
  SampleExport,
} from "../types/contracts";
import * as validators from "../generated/validators";

export type Bundle = {
  meta: MetaExport;
  index: IndexExport;
  drops: DropsExport;
  seasonality: SeasonalityExport;
  drivers: DriversExport;
  fairprice: FairPriceExport;
  models: ModelsExport;
  listings_sample: SampleExport;
};
export const keys = [
  "meta",
  "index",
  "drops",
  "seasonality",
  "drivers",
  "fairprice",
  "models",
  "listings_sample",
] as const;
export function validate<K extends keyof Bundle>(
  key: K,
  value: unknown,
): Bundle[K] {
  if (!validators[key](value))
    throw new Error(
      "The data format could not be verified. Please retry the latest update.",
    );
  if (key === "fairprice") {
    const model = (value as FairPriceExport).data.model;
    if (
      model &&
      (["make_model", "transmission", "city"].some(
        (field) => !model.spec.categories[field]?.length,
      ) ||
        ["model_year", "mileage_km", "engine_cc"].some(
          (field) =>
            !model.ranges[field] ||
            model.ranges[field][0] > model.ranges[field][1],
        ) ||
        !Number.isFinite(Number(model.defaults.engine_cc)))
    ) {
      throw new Error(
        "The price model is incomplete. Please retry the latest update.",
      );
    }
  }
  return value as Bundle[K];
}
export function coherent(bundle: Bundle): Bundle {
  const { bundle_id, generated_at, schema_version } = bundle.meta;
  if (
    keys.some(
      (key) =>
        bundle[key].bundle_id !== bundle_id ||
        bundle[key].generated_at !== generated_at ||
        bundle[key].schema_version !== schema_version,
    )
  ) {
    throw new Error(
      "The data is being refreshed. Please retry to load one complete update.",
    );
  }
  return bundle;
}
let cached: Promise<Bundle> | undefined;
export function clearCache() {
  cached = undefined;
}
export function loadBundle(): Promise<Bundle> {
  cached ??= Promise.all(
    keys.map(async (key) => {
      const response = await fetch(
        `${import.meta.env.BASE_URL}data/${key}.json`,
        { cache: "no-store" },
      );
      if (!response.ok)
        throw new Error(
          "The market data could not be loaded. Check your connection and retry.",
        );
      return [key, validate(key, await response.json())] as const;
    }),
  )
    .then((pairs) => coherent(Object.fromEntries(pairs) as Bundle))
    .catch((error: unknown) => {
      clearCache();
      throw error;
    });
  return cached;
}
