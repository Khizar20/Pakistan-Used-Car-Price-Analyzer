import { useRef, useState } from "react";
import type { FairModel } from "../lib/fairPrice";
import { fairPrice, verdict } from "../lib/fairPrice";
import { money, percent } from "../lib/format";
import { DepreciationCurve } from "./Chart";

export function FairPrice({
  model,
  full,
}: {
  model: FairModel;
  full: boolean;
}) {
  const pairs = model.spec.categories.make_model.map((value) =>
    value.split(" / "),
  );
  const makes = [...new Set(pairs.map((pair) => pair[0]))];
  const [make, setMake] = useState(makes[0]);
  const [carModel, setCarModel] = useState(pairs[0][1]);
  const [year, setYear] = useState(String(model.ranges.model_year[1]));
  const [mileage, setMileage] = useState(
    String(
      Math.round((model.ranges.mileage_km[0] + model.ranges.mileage_km[1]) / 2),
    ),
  );
  const [transmission, setTransmission] = useState(
    model.spec.categories.transmission[0],
  );
  const [city, setCity] = useState(model.spec.categories.city[0]);
  const [asking, setAsking] = useState("");
  const [showErrors, setShowErrors] = useState(false);
  const estimateRef = useRef<HTMLElement>(null);
  let result: ReturnType<typeof fairPrice> | undefined;
  let error = "";
  try {
    if (!year || !mileage)
      throw new Error("Enter the model year and mileage to check this car.");
    if (!Number.isInteger(Number(year)) || !Number.isInteger(Number(mileage)))
      throw new Error("Year and mileage must be whole numbers.");
    if (asking && (!Number.isFinite(Number(asking)) || Number(asking) <= 0))
      throw new Error("Enter an asking price greater than zero.");
    result = fairPrice(
      {
        make,
        model: carModel,
        model_year: Number(year),
        mileage_km: Number(mileage),
        transmission,
        city,
      },
      model,
    );
  } catch (caught) {
    error = caught instanceof Error ? caught.message : "Check the car details.";
  }
  const curve = Array.from(
    { length: model.ranges.model_year[1] - model.ranges.model_year[0] + 1 },
    (_, index) => {
      const value = model.ranges.model_year[0] + index;
      return {
        label: String(value),
        value: fairPrice(
          {
            make,
            model: carModel,
            model_year: value,
            mileage_km: Math.min(
              model.ranges.mileage_km[1],
              Math.max(
                model.ranges.mileage_km[0],
                Number(mileage) || model.ranges.mileage_km[0],
              ),
            ),
            transmission,
            city,
          },
          model,
        ).estimate,
      };
    },
  );
  return (
    <div className="fair-layout">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setShowErrors(true);
          if (result) estimateRef.current?.focus();
        }}
        noValidate
      >
        <h2>Your car</h2>
        <p>
          Choose the details you know. Estimates update as you make changes.
        </p>
        <div className="form-grid">
          <label>
            Make
            <select
              value={make}
              onChange={(event) => {
                setMake(event.target.value);
                setCarModel(
                  pairs.find((pair) => pair[0] === event.target.value)![1],
                );
              }}
            >
              {makes.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label>
            Model
            <select
              value={carModel}
              onChange={(event) => setCarModel(event.target.value)}
            >
              {pairs
                .filter((pair) => pair[0] === make)
                .map((pair) => (
                  <option key={pair[1]}>{pair[1]}</option>
                ))}
            </select>
          </label>
          <div className="field">
            <label htmlFor="fair-year">Model year</label>
            <input
              id="fair-year"
              type="number"
              min={model.ranges.model_year[0]}
              max={model.ranges.model_year[1]}
              value={year}
              onChange={(event) => {
                setYear(event.target.value);
                setShowErrors(true);
              }}
              aria-describedby="year-hint fair-error"
              aria-invalid={
                showErrors &&
                (!year ||
                  !Number.isInteger(Number(year)) ||
                  Number(year) < model.ranges.model_year[0] ||
                  Number(year) > model.ranges.model_year[1])
              }
            />
            <small id="year-hint">{model.ranges.model_year.join("–")}</small>
          </div>
          <div className="field">
            <label htmlFor="fair-mileage">Mileage (km)</label>
            <input
              id="fair-mileage"
              type="number"
              min={model.ranges.mileage_km[0]}
              max={model.ranges.mileage_km[1]}
              value={mileage}
              onChange={(event) => {
                setMileage(event.target.value);
                setShowErrors(true);
              }}
              aria-describedby="mileage-hint fair-error"
              aria-invalid={
                showErrors &&
                (!mileage ||
                  !Number.isInteger(Number(mileage)) ||
                  Number(mileage) < model.ranges.mileage_km[0] ||
                  Number(mileage) > model.ranges.mileage_km[1])
              }
            />
            <small id="mileage-hint">
              {model.ranges.mileage_km
                .map((value) => value.toLocaleString())
                .join("–")}{" "}
              km
            </small>
          </div>
          <label>
            Transmission
            <select
              value={transmission}
              onChange={(event) => setTransmission(event.target.value)}
            >
              {model.spec.categories.transmission.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label>
            City
            <select
              value={city}
              onChange={(event) => setCity(event.target.value)}
            >
              {model.spec.categories.city.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
        </div>
        <label>
          Asking price (PKR, optional)
          <input
            type="number"
            min="1"
            aria-describedby="fair-error"
            aria-invalid={showErrors && !!asking && Number(asking) <= 0}
            value={asking}
            placeholder="For example, 3500000"
            onChange={(event) => {
              setAsking(event.target.value);
              setShowErrors(true);
            }}
          />
        </label>
        <div id="fair-error" aria-live="polite" className="form-error">
          {showErrors && error}
        </div>
        <button className="primary" type="submit">
          Check price
        </button>
        <details>
          <summary>Assumptions used in this estimate</summary>
          <p>
            Engine size defaults to{" "}
            {Number(model.defaults.engine_cc).toLocaleString()} cc. Optional
            predictors use the exported model defaults. This estimate describes
            asking prices within the training ranges.
          </p>
          <ul>
            {Object.entries(model.defaults)
              .filter(
                ([key]) =>
                  !["make_model", "transmission", "city", "engine_cc"].includes(
                    key,
                  ),
              )
              .map(([key, value]) => (
                <li key={key}>
                  {key.replaceAll("_", " ")}: {String(value)}
                </li>
              ))}
          </ul>
        </details>
      </form>
      <section
        className="estimate"
        aria-label="Price estimate"
        ref={estimateRef}
        tabIndex={-1}
      >
        <p className="eyebrow">Estimated asking price</p>
        <div className="estimate-value" aria-live="polite">
          {result ? money(result.estimate, full) : "Check your inputs"}
        </div>
        {result && (
          <>
            <p className="range">
              Approximate range
              <br />
              <strong>
                {money(result.lower, full)} – {money(result.upper, full)}
              </strong>
            </p>
            {asking && (
              <p
                className={
                  Number(asking) > result.estimate * 1.1
                    ? "verdict negative"
                    : "verdict"
                }
              >
                {verdict(Number(asking), result.estimate)}
              </p>
            )}
            <p className="caption">
              Typical prediction error: {percent(model.typical_error_percent)}.
              This estimates typical asking prices with an approximate range.
              Actual sale prices can differ.
            </p>
          </>
        )}
        <DepreciationCurve
          full={full}
          title="Year and estimated price"
          description="Other selected details stay fixed. The gold point marks your selected year."
          rows={curve}
          unit="PKR"
          marker={result ? { label: year, value: result.estimate } : undefined}
        />
      </section>
    </div>
  );
}
