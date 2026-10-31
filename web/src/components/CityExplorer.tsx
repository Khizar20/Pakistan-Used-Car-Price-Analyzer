import { useState } from "react";
import type { ModelsExport } from "../types/contracts";
import { date, money } from "../lib/format";
import photoCatalog from "../data/carPhotos.json";

const photos: Record<string, { path: string; year: number | null }> =
  photoCatalog;

type Props = { data: ModelsExport["data"]; full: boolean };
export function CityExplorer({ data, full }: Props) {
  const rows = data.city_prices;
  const cars = [
    ...new Set(rows.map((row) => `${row.make} / ${row.model}`)),
  ].sort();
  const cities = [
    ...new Set([
      "Karachi",
      "Lahore",
      "Islamabad",
      "Rawalpindi",
      ...rows.flatMap((row) => (row.city ? [row.city] : [])),
    ]),
  ].sort();
  const supported = rows.find(
    (row) =>
      row.city === "Karachi" &&
      row.status === "ok" &&
      row.model_year === null &&
      row.transmission === null &&
      photos[`${row.make} / ${row.model}`],
  );
  const [car, setCar] = useState(
    supported ? `${supported.make} / ${supported.model}` : (cars[0] ?? ""),
  );
  const [city, setCity] = useState(
    cities.includes("Karachi") ? "Karachi" : (cities[0] ?? ""),
  );
  const [year, setYear] = useState("All years");
  const [transmission, setTransmission] = useState("All transmissions");
  const sameCar = rows.filter((row) => `${row.make} / ${row.model}` === car);
  const years = [
    ...new Set(
      sameCar.flatMap((row) =>
        row.model_year ? [String(row.model_year)] : [],
      ),
    ),
  ]
    .sort()
    .reverse();
  const transmissions = [
    ...new Set(
      sameCar.flatMap((row) => (row.transmission ? [row.transmission] : [])),
    ),
  ].sort();
  const comparisons = sameCar.filter(
    (row) =>
      row.model_year === (year === "All years" ? null : Number(year)) &&
      row.transmission ===
        (transmission === "All transmissions" ? null : transmission),
  );
  const selected = comparisons.find((row) => row.city === city);
  const photo = photos[car];
  const [failedPhoto, setFailedPhoto] = useState("");
  return (
    <section className="city-explorer" aria-labelledby="city-price-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Shop with local context</p>
          <h2 id="city-price-title">What does this car cost in your city?</h2>
        </div>
      </div>
      <p>
        Compare observed asking prices for the same model, year and
        transmission. Counts matter: a city median needs at least{" "}
        {data.minimum_city_sample} usable listings.
      </p>
      <div className="filters city-filters">
        <label>
          Car model
          <select
            value={car}
            onChange={(event) => {
              setCar(event.target.value);
              setYear("All years");
              setTransmission("All transmissions");
            }}
          >
            <option value="" disabled>
              Choose a car
            </option>
            {cars.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Buying city
          <select
            value={city}
            onChange={(event) => setCity(event.target.value)}
          >
            <option value="" disabled>
              Choose a city
            </option>
            {cities.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Year
          <select
            value={year}
            onChange={(event) => setYear(event.target.value)}
          >
            <option>All years</option>
            {years.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Gearbox
          <select
            value={transmission}
            onChange={(event) => setTransmission(event.target.value)}
          >
            <option>All transmissions</option>
            {transmissions.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <button
          onClick={() => {
            setYear("All years");
            setTransmission("All transmissions");
          }}
        >
          Clear car refinements
        </button>
      </div>
      <div className="local-price" aria-live="polite">
        {photo && failedPhoto !== photo.path && (
          <figure className="car-reference">
            <img
              src={`${import.meta.env.BASE_URL}${photo.path}`}
              alt={`${car.replace(" / ", " ")} example listing`}
              width="320"
              height="240"
              loading="lazy"
              onError={() => setFailedPhoto(photo.path)}
            />
            <figcaption>
              Example {photo.year ?? ""} listing photo, via PakWheels with
              permission. Year, trim and condition may differ.
            </figcaption>
          </figure>
        )}
        <p className="eyebrow">
          {car || "Selected car"} · {city || "Selected city"}
        </p>
        <h3>
          {selected?.status === "ok"
            ? money(selected.median_price_pkr, full)
            : "Not enough comparable listings yet"}
        </h3>
        {selected ? (
          <>
            <p>
              {selected.priced_listing_count} usable prices from{" "}
              {selected.listing_count} observed listings · Last seen{" "}
              {date(selected.observed_through)}
            </p>
            {selected.status === "ok" && (
              <p>
                Middle 50%:{" "}
                <strong>
                  {money(selected.lower_quartile_pkr, full)} –{" "}
                  {money(selected.upper_quartile_pkr, full)}
                </strong>
                {selected.median_mileage_km != null && (
                  <>
                    {" "}
                    · Median mileage{" "}
                    {Math.round(selected.median_mileage_km).toLocaleString()} km
                  </>
                )}
              </p>
            )}
          </>
        ) : (
          <p>
            There are fewer than {data.minimum_city_sample} comparable usable
            prices for these choices. Broaden the year or transmission, or try
            another city.
          </p>
        )}
      </div>
      <div className="table-wrap">
        <table className="responsive-table">
          <caption>
            Compare {car || "this car"} across cities · {year} · {transmission}
          </caption>
          <thead>
            <tr>
              <th scope="col">City</th>
              <th scope="col">Usable listings</th>
              <th scope="col">Median asking price</th>
              <th scope="col">Middle 50%</th>
              <th scope="col">Last observed</th>
            </tr>
          </thead>
          <tbody>
            {comparisons.map((row) => (
              <tr
                key={row.city ?? "all"}
                className={row.city === city ? "selected-city" : ""}
              >
                <th scope="row">{row.city ?? "All locations"}</th>
                <td data-label="Usable listings">{row.priced_listing_count}</td>
                <td data-label="Median asking price">
                  {row.status === "ok"
                    ? money(row.median_price_pkr, full)
                    : "Small sample"}
                </td>
                <td data-label="Middle 50%">
                  {row.status === "ok"
                    ? `${money(row.lower_quartile_pkr, full)} – ${money(row.upper_quartile_pkr, full)}`
                    : "Not available"}
                </td>
                <td data-label="Last observed">{date(row.observed_through)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="caption">
        Comparisons use each active, nonduplicate car’s latest observation
        within seven days of the latest collection. “All years” mixes ages;
        refine the year for a closer comparison. Trim, condition and mileage can
        still differ. Year and gearbox options appear when a cohort has enough
        usable prices somewhere; individual cities may still have small samples.
        These are sample asking prices, not completed-sale values.
      </p>
    </section>
  );
}
