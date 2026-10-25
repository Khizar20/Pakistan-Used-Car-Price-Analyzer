import type { FairPriceExport } from "../types/contracts";
export type FairModel = NonNullable<FairPriceExport["data"]["model"]>;
export type Car = {
  make: string;
  model: string;
  model_year: number;
  mileage_km: number;
  transmission: string;
  city: string;
  [key: string]: string | number;
};
export function fairPrice(car: Car, model: FairModel) {
  const values: Record<string, string | number> = {
    ...model.defaults,
    ...car,
    make_model: `${car.make} / ${car.model}`,
  };
  for (const [key, [low, high]] of Object.entries(model.ranges)) {
    const value = values[key];
    if (
      typeof value !== "number" ||
      !Number.isFinite(value) ||
      value < low ||
      value > high
    )
      throw new Error(
        `${key.replaceAll("_", " ")} must be between ${low.toLocaleString()} and ${high.toLocaleString()}.`,
      );
  }
  const terms: Record<string, number> = {
    intercept: 1,
    model_year: car.model_year - 2000,
    log_mileage: Math.log1p(car.mileage_km),
    engine_litres: Number(values.engine_cc) / 1000,
  };
  for (const [key, levels] of Object.entries(model.spec.categories)) {
    const value = String(values[key]);
    if (!levels.includes(value))
      throw new Error(`Choose a supported ${key.replaceAll("_", " ")}.`);
    for (const level of levels.slice(1))
      terms[`${key}=${level}`] = Number(value === level);
  }
  let log = 0;
  for (const term of model.spec.terms) {
    if (
      !Number.isFinite(terms[term]) ||
      !Number.isFinite(model.coefficients[term])
    )
      throw new Error("This model cannot evaluate the selected inputs.");
    log += terms[term] * model.coefficients[term];
  }
  const width = model.interval_multiplier * model.residual_std_log;
  const result = {
    estimate: Math.exp(log),
    lower: Math.exp(log - width),
    upper: Math.exp(log + width),
  };
  if (!Object.values(result).every(Number.isFinite))
    throw new Error("The estimate is outside the supported range.");
  return result;
}
export function verdict(asking: number, estimated: number): string {
  const ratio = asking / estimated;
  return ratio < 0.9
    ? "Below the estimated market level"
    : ratio > 1.1
      ? "Above the estimated market level"
      : "Near the estimated market level";
}
