import { useState } from "react";
import type { Bundle } from "./lib/data";
import { date, money, observedDays, percent } from "./lib/format";
import { headline } from "./lib/headline";
import { cohortIndex } from "./lib/cohorts";
import {
  BarWithCI,
  DepreciationCurve,
  Empty,
  LineChart,
  SurvivalChart,
  ScatterChart,
} from "./components/Chart";
import { FairPrice } from "./components/FairPrice";

type Props = { bundle: Bundle; full: boolean };
export function Market({ bundle, full }: Props) {
  const [mode, setMode] = useState<"quality_adjusted" | "raw">(
    "quality_adjusted",
  );
  const [model, setModel] = useState("All models");
  const index = bundle.index.data;
  const series = index[mode];
  const models = bundle.models.data.models;
  const points =
    model === "All models"
      ? (series?.points ?? [])
      : cohortIndex(index.cohorts ?? [], model);
  const supported =
    model === "All models" ? series?.status === "ok" : points.length > 1;
  const meta = bundle.meta.data;
  return (
    <>
      <p className="eyebrow">The asking-price market</p>
      <h1 className="headline">{headline(points, supported)}</h1>
      <p className="lede">
        An independent view of Pakistan’s used-car asking prices. See what
        changed, what might explain it, and how much the data can tell us.
      </p>
      <div className="facts">
        <div>
          <strong>{meta.listing_count.toLocaleString()}</strong>
          <span>Listings observed</span>
        </div>
        <div>
          <strong>{observedDays(meta.date_start, meta.date_end)}</strong>
          <span>Calendar days in window</span>
        </div>
        <div>
          <strong>{date(meta.date_end)}</strong>
          <span>Latest observation</span>
        </div>
      </div>
      <div className="section-heading">
        <h2>Price movement</h2>
        <label className="inline-label">
          Model
          <select
            value={model}
            onChange={(event) => {
              setModel(event.target.value);
              if (event.target.value !== "All models") setMode("raw");
            }}
          >
            <option>All models</option>
            {models.map((row) => (
              <option key={`${row.make}/${row.model}`}>
                {row.make} / {row.model}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="segmented" aria-label="Price index method">
        <button
          aria-pressed={mode === "quality_adjusted"}
          disabled={model !== "All models"}
          onClick={() => setMode("quality_adjusted")}
        >
          Quality-adjusted
        </button>
        <button aria-pressed={mode === "raw"} onClick={() => setMode("raw")}>
          Matched cohorts
        </button>
      </div>
      {supported ? (
        <LineChart
          title="Weekly price index"
          description="First supported week = 100. Values below 100 indicate lower asking prices than the starting week."
          unit="Index"
          rows={points.map((point) => ({
            label: point.week,
            value: point.value,
            lower: point.lower,
            upper: point.upper,
          }))}
        />
      ) : (
        <Empty
          title="A trend needs more observations"
          detail={
            model === "All models"
              ? (series?.reason ??
                "At least two supported weeks are needed to compare asking prices.")
              : "This model needs supported, overlapping cohorts in at least two consecutive weeks."
          }
        />
      )}
      <p className="caption">
        Quality adjustment accounts for vehicle attributes. Matched cohorts
        compare the same make, model and year groups. Model views use the
        exported cohort medians. <a href="#about">Read the method</a>.
      </p>
      <div className="section-heading">
        <h2>Models in the current sample</h2>
        <a href="#fair">Check a car’s price</a>
      </div>
      <div className="model-list">
        {models.map((row) => (
          <div className="model-row" key={`${row.make}/${row.model}`}>
            <div>
              <h3>
                {row.make} {row.model}
              </h3>
              <span>
                {row.listing_count} active listings · {row.priced_listing_count}{" "}
                usable prices
              </span>
            </div>
            <div>
              <strong>{money(row.median_price_pkr, full)}</strong>
              <span>Median asking price</span>
            </div>
          </div>
        ))}
      </div>
      {!models.length && (
        <Empty
          title="No current model summaries"
          detail="Current active listings need usable make and model attributes."
        />
      )}
      <p className="caption">
        These medians describe the current active, nonduplicate sample. They do
        not establish a market trend.
      </p>
    </>
  );
}

export function Drops({ bundle, full }: Props) {
  const drops = bundle.drops.data;
  const [city, setCity] = useState("All cities");
  const [sort, setSort] = useState("recent");
  const [dimension, setDimension] = useState("all");
  const rows = bundle.listings_sample.data.rows;
  const filtered = rows
    .filter((row) => city === "All cities" || row.city === city)
    .toSorted((a, b) =>
      sort === "largest"
        ? b.drop_percent - a.drop_percent
        : b.observed_at.localeCompare(a.observed_at),
    );
  const curves = drops.survival.filter(
    (curve) => curve.outcome === "drop" && curve.dimension === dimension,
  );
  return (
    <>
      <PageTitle
        eyebrow="Price changes"
        title="How asking prices move down"
        detail="Observed changes on the same listing, with unknown prices excluded from comparisons."
      />
      <div className="facts">
        <div>
          <strong>
            {percent(drops.drop_share == null ? null : drops.drop_share * 100)}
          </strong>
          <span>Listings with a price drop</span>
        </div>
        <div>
          <strong>{money(drops.median_drop_pkr, full)}</strong>
          <span>Median observed drop</span>
        </div>
        <div>
          <strong>{drops.eligible_listings}</strong>
          <span>Listings with comparable prices</span>
        </div>
      </div>
      {drops.status !== "ok" && (
        <Empty
          title="Too little comparable follow-up"
          detail={drops.reason ?? "More repeat observations are required."}
        />
      )}
      <label className="inline-label">
        Survival grouping
        <select
          value={dimension}
          onChange={(event) => setDimension(event.target.value)}
        >
          <option value="all">All listings</option>
          <option value="bucket">Initial price vs fair value</option>
          <option value="seller_type">Seller type</option>
          <option value="city">City</option>
        </select>
      </label>
      {curves
        .filter((curve) => curve.status === "ok")
        .map((curve) => (
          <SurvivalChart
            key={curve.segment}
            title={`Still without a price drop: ${curve.segment}`}
            description={`${curve.listings} listings; ${curve.events} first-drop events. Active observations are censored.`}
            rows={(curve.points ?? []).map((point) => ({
              label: `${point.days} days`,
              value: point.survival * 100,
              lower: point.lower * 100,
              upper: point.upper * 100,
            }))}
            unit="Percent"
          />
        ))}
      {!curves.some((curve) => curve.status === "ok") && (
        <p className="caption">
          Survival curves need enough eligible listings and positive follow-up.
          Fair-value buckets remain unknown without an independent reference.
        </p>
      )}
      <div className="section-heading">
        <h2>Recent observed drops</h2>
        <span className="caption">
          {rows.length} of {bundle.listings_sample.data.total_events} events
          shown
        </span>
      </div>
      <div className="filters">
        <label>
          City
          <select
            value={city}
            onChange={(event) => setCity(event.target.value)}
          >
            <option>All cities</option>
            {[
              ...new Set(
                rows
                  .map((row) => row.city)
                  .filter((value): value is string => value != null),
              ),
            ]
              .sort()
              .map((value) => (
                <option key={value}>{value}</option>
              ))}
          </select>
        </label>
        <label>
          Sort by
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value)}
          >
            <option value="recent">Most recent</option>
            <option value="largest">Largest percentage drop</option>
          </select>
        </label>
        <button
          onClick={() => {
            setCity("All cities");
            setSort("recent");
          }}
        >
          Reset filters
        </button>
      </div>
      {filtered.length ? (
        <div className="table-wrap">
          <table className="responsive-table">
            <caption>Recent observed asking-price reductions</caption>
            <thead>
              <tr>
                {[
                  "Car",
                  "City",
                  "Previous",
                  "Current",
                  "Drop",
                  "Days observed",
                ].map((label) => (
                  <th scope="col" key={label}>
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((row, index) => (
                <tr key={`${row.listing_hash}/${row.observed_at}/${index}`}>
                  <th scope="row">
                    {row.make} {row.model} {row.model_year}
                  </th>
                  <td data-label="City">{row.city ?? "Unknown"}</td>
                  <td data-label="Previous">
                    {money(row.old_price_pkr, full)}
                  </td>
                  <td data-label="Current">{money(row.new_price_pkr, full)}</td>
                  <td data-label="Drop" className="positive">
                    −{percent(row.drop_percent)}
                  </td>
                  <td data-label="Days observed">
                    {row.days_listed.toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty
          title={
            rows.length
              ? "No drops match this city"
              : "No usable price drops observed yet"
          }
          detail={
            rows.length
              ? "Choose another city or reset the filters."
              : "Repeat observations will reveal comparable asking-price changes."
          }
        />
      )}
      <p className="caption">
        Time starts at first observation, not posting. A listing’s disappearance
        is not proof of a sale.
      </p>
      {drops.survival
        .filter(
          (curve) =>
            curve.outcome === "disappearance" &&
            curve.dimension === dimension &&
            curve.status === "ok",
        )
        .map((curve) => (
          <SurvivalChart
            key={curve.segment}
            title={`Still observed in scope: ${curve.segment}`}
            description="Absence from the collection window can mean removal, movement outside the window or a sale; the outcome is unknown."
            unit="Percent"
            rows={(curve.points ?? []).map((point) => ({
              label: `${point.days} days`,
              value: point.survival * 100,
              lower: point.lower * 100,
              upper: point.upper * 100,
            }))}
          />
        ))}
    </>
  );
}

export function Seasons({ bundle }: Props) {
  const data = bundle.seasonality.data;
  const seasonal = data.seasonal;
  return (
    <>
      <PageTitle
        eyebrow="Time and timing"
        title="Patterns need time to emerge"
        detail="Weekday effects can become visible sooner. Annual patterns need a much longer observation window."
      />
      <BarWithCI
        title="Newly observed listings by weekday"
        description={
          data.caveat ??
          "Counts describe first observation in the selected collection window."
        }
        rows={(data.weekdays ?? []).map((row) => ({
          label: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][row.weekday],
          value: row.listings_per_observed_day,
        }))}
        unit="Listings per observed day"
      />
      {data.status !== "ok" && <p className="caption">{data.reason}</p>}
      <BarWithCI
        title="Price changes by weekday"
        description="Changes divided by comparable price pairs on actually observed days."
        rows={(data.weekdays ?? [])
          .filter((row) => row.change_rate != null)
          .map((row) => ({
            label: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][
              row.weekday
            ],
            value: row.change_rate! * 100,
          }))}
        unit="Percent"
      />
      <LineChart
        title="Observed listing volume"
        description={
          data.volume_basis === "posting_metadata"
            ? "Posting dates of the listings in this sample."
            : "First-observed dates are a collection proxy, not actual posting dates."
        }
        rows={(data.volume_trend ?? []).map((point) => ({
          label: point.date,
          value: point.listings,
        }))}
        unit="Listings"
      />
      {seasonal?.status === "ok" ? (
        <LineChart
          title="Exploratory seasonal component"
          description="A 52-week decomposition of the supported price index. This is an exploratory association, not a stable annual forecast."
          rows={(seasonal.points ?? []).map((point) => ({
            label: point.week,
            value: point.seasonal,
          }))}
          unit="Index units"
        />
      ) : (
        <div className="season-gate">
          <span className="eyebrow">Monthly view</span>
          <h2>Not enough history for seasonality</h2>
          <p>
            {seasonal?.reason ??
              "At least 79 contiguous supported weekly observations are required."}
          </p>
          <p>
            <strong>
              {seasonal?.weeks_remaining ?? 79} more supported weeks needed
            </strong>{" "}
            · {seasonal?.weeks_available ?? 0} available
          </p>
        </div>
      )}
    </>
  );
}

export function Drivers({ bundle, full }: Props) {
  const data = bundle.drivers.data;
  return (
    <>
      <PageTitle
        eyebrow="Behind the price"
        title="What is associated with asking prices?"
        detail="Compare vehicle attributes while holding included factors fixed. Associations do not establish causes."
      />
      {data.status !== "ok" ? (
        <Empty
          title="The model needs better-supported data"
          detail={
            data.reason ??
            "More complete listings and supported categories are needed."
          }
        />
      ) : (
        <>
          <BarWithCI
            title="Estimated price effects"
            description="Percentage effects with 95% confidence intervals. A numeric term is one unit of its specified transformation; categories are relative to the exported baseline."
            unit="Percent"
            rows={data.coefficients
              .filter((term) => term.effect_percent != null)
              .map((term) => ({
                label: term.term.replaceAll("_", " "),
                value: term.effect_percent!,
                lower: term.lower_percent,
                upper: term.upper_percent,
              }))}
          />
          <div className="table-wrap">
            <table>
              <caption>Held-out predictive performance</caption>
              <thead>
                <tr>
                  <th scope="col">Model</th>
                  <th scope="col">Mean absolute error</th>
                  <th scope="col">Percentage error</th>
                  <th scope="col">R squared</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["Linear", data.linear_metrics],
                  ["Gradient boosting", data.boosting_metrics],
                  ["Median baseline", data.baseline_metrics],
                ].map(([label, raw]) => {
                  const metric = raw as typeof data.linear_metrics;
                  return (
                    <tr key={String(label)}>
                      <th scope="row">{String(label)}</th>
                      <td>{money(metric?.mae_pkr, full)}</td>
                      <td>{percent(metric?.mape_percent)}</td>
                      <td>
                        {metric?.r_squared?.toFixed(3) ?? "Not available"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {Object.entries(data.dependence).map(([key, points]) => (
            <DepreciationCurve
              full={full}
              key={key}
              title={`Price and ${key.replaceAll("_", " ")}`}
              description="Average model predictions as one attribute changes. Correlated attributes can make some combinations unrealistic."
              rows={points.map((point) => ({
                label: point.x.toLocaleString("en-PK", {
                  maximumFractionDigits: 1,
                }),
                value: point.price_pkr,
              }))}
              unit="PKR"
            />
          ))}
          <BarWithCI
            title="Nonlinear model importance"
            description="Mean absolute SHAP effects explain the fitted model in log-price units; they are not causal percentage effects."
            unit="Log-price effect"
            rows={data.shap_effects.map((effect) => ({
              label: effect.feature.replaceAll("_", " "),
              value: effect.mean_absolute_log_effect,
            }))}
          />
          <ScatterChart
            full={full}
            title="Held-out residuals"
            description={`${data.diagnostics.length} of ${data.diagnostics_total} cars. Each point is actual minus predicted asking price; the observation label is fitted PKR.`}
            rows={data.diagnostics
              .toSorted((a, b) => a.fitted_pkr - b.fitted_pkr)
              .map((row) => ({
                label: row.fitted_pkr.toFixed(0),
                value: row.residual_pkr,
              }))}
            unit="Residual PKR"
          />
        </>
      )}
      <p className="caption">
        Numeric transforms: year minus 2000, log(1 + mileage in km), and engine
        litres. Five folds group by listing. Optional predictors omitted:{" "}
        {data.omitted_predictors.join(", ") || "none reported"}.{" "}
        <a href="#about">Methods and limitations</a>.
      </p>
    </>
  );
}

export function Fair({ bundle, full }: Props) {
  const data = bundle.fairprice.data;
  return (
    <>
      <PageTitle
        eyebrow="A second opinion"
        title="Is the asking price in range?"
        detail="Compare a car with the observed market model. A useful starting point for your research, not a valuation guarantee."
      />
      {data.status === "ok" && data.model ? (
        <FairPrice model={data.model} full={full} />
      ) : (
        <Empty
          title="Fair Price Check is not available yet"
          detail={`${data.reason ?? "There is not enough supported model data."} A reliable check needs sufficient complete listings in every included category.`}
        />
      )}
    </>
  );
}

export function About({ bundle }: Props) {
  const meta = bundle.meta.data;
  return (
    <>
      <PageTitle
        eyebrow="About the data"
        title="Useful evidence, with clear limits"
        detail="Original observations from public PakWheels used-car listings, collected for personal and educational analysis."
      />
      <dl className="about-facts">
        <div>
          <dt>Observation window</dt>
          <dd>
            {date(meta.date_start)} – {date(meta.date_end)}
          </dd>
        </div>
        <div>
          <dt>Observed listings</dt>
          <dd>{meta.listing_count.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Price snapshots</dt>
          <dd>{meta.observation_count.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Represented collection runs</dt>
          <dd>{meta.run_count}</dd>
        </div>
        <div>
          <dt>Export generated</dt>
          <dd>{date(bundle.meta.generated_at)}</dd>
        </div>
      </dl>
      <h2>What is measured</h2>
      <p>
        These are asking prices, not transaction prices. The collection follows
        a bounded page window; featured cars and selected models may be
        overrepresented. Repeated snapshots allow comparisons on the same
        listing.
      </p>
      <h2>How the comparisons work</h2>
      <p>
        Matched cohorts compare make, model and year groups with at least five
        usable listings. The quality-adjusted index also accounts for mileage,
        engine size, transmission and city. Supported indexes start at 100.
        Model-specific views derive the same chain links from exported cohorts.
      </p>
      <p>
        Survival curves measure time from first observation to a detected price
        drop or disappearance, with censored follow-up. Disappearance can have
        several explanations and does not prove a sale.
      </p>
      <p>
        The price model uses log-linear regression with robust uncertainty and a
        nonlinear comparison model. Grouped validation holds each car out of its
        training fold. Numeric transforms are year minus 2000, log(1 + mileage),
        and engine litres. The first sorted category is its baseline. Fair Price
        Check evaluates the exported coefficients locally in your browser and
        rejects unsupported inputs.
      </p>
      <h2>Limits to keep in mind</h2>
      <ul className="caveats">
        {meta.caveats.map((caveat) => (
          <li key={caveat}>{caveat}</li>
        ))}
      </ul>
      <h2>Privacy and reproducibility</h2>
      <p>
        No seller names, phone numbers, exact addresses or listing links appear
        in these exports. Public listing hashes are database-local pseudonyms.
        The dashboard makes no analytics or external font requests.
      </p>
      <p>
        <a
          href="https://github.com/Khizar20/Pakistan-Used-Car-Price-Analyzer"
          target="_blank"
          rel="noreferrer"
        >
          View the source and methods on GitHub{" "}
          <span aria-hidden="true">↗</span>
        </a>
      </p>
    </>
  );
}
function PageTitle({
  eyebrow,
  title,
  detail,
}: {
  eyebrow: string;
  title: string;
  detail: string;
}) {
  return (
    <>
      <p className="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <p className="lede">{detail}</p>
    </>
  );
}
