import { render, screen, fireEvent } from "@testing-library/react";
import { expect, it } from "vitest";
import { Chart, Empty } from "../src/components/Chart";
import { FairPrice } from "../src/components/FairPrice";
import { Drops, Fair, Market, Seasons, Drivers, About } from "../src/pages";
import { validate } from "../src/lib/data";
import type { FairModel } from "../src/lib/fairPrice";
import meta from "./fixtures/meta.json";
import index from "./fixtures/index.json";
import drops from "./fixtures/drops.json";
import seasonality from "./fixtures/seasonality.json";
import drivers from "./fixtures/drivers.json";
import fairprice from "./fixtures/fairprice.json";
import models from "./fixtures/models.json";
import listings_sample from "./fixtures/listings_sample.json";
const populated = {
  meta: validate("meta", meta),
  index: validate("index", index),
  drops: validate("drops", drops),
  seasonality: validate("seasonality", seasonality),
  drivers: validate("drivers", drivers),
  fairprice: validate("fairprice", fairprice),
  models: validate("models", models),
  listings_sample: validate("listings_sample", listings_sample),
};

it("exposes a chart summary, toggle and exact confidence bounds", async () => {
  render(
    <Chart
      title="Weekly index"
      description="Base 100"
      unit="Index"
      rows={[{ label: "Week one", value: 100, lower: 98, upper: 102 }]}
    />,
  );
  expect(
    await screen.findByRole("img", {}, { timeout: 5000 }),
  ).toHaveAccessibleName(/Weekly index/);
  fireEvent.click(screen.getByRole("button", { name: "Show data table" }));
  expect(screen.getByRole("table")).toHaveAccessibleName(
    "Weekly index — Index",
  );
  expect(screen.getByText("98")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Hide data table" }));
  expect(screen.queryByRole("table")).toBeNull();
});
it("renders an empty chart as an explanation without invented points", () => {
  render(
    <Chart
      title="No data"
      description="No supported observations"
      unit="PKR"
      rows={[]}
    />,
  );
  expect(screen.getByText("More observations are needed")).toBeVisible();
  expect(screen.queryByRole("img")).toBeNull();
});
it("makes an unavailable model explicit", () => {
  render(
    <Fair
      bundle={{
        ...populated,
        fairprice: {
          ...populated.fairprice,
          data: {
            status: "insufficient_data",
            reason: "Sparse categories",
            model: null,
          },
        },
      }}
      full={false}
    />,
  );
  expect(
    screen.getByText("Fair Price Check is not available yet"),
  ).toBeVisible();
  expect(screen.queryByRole("button", { name: "Check price" })).toBeNull();
});
it("filters and sorts drops, and restores the sample with reset", () => {
  render(<Drops bundle={populated} full={false} />);
  fireEvent.change(screen.getByLabelText("City"), {
    target: { value: "Karachi" },
  });
  expect(screen.getByRole("table")).toBeVisible();
  fireEvent.change(screen.getByLabelText("Sort by"), {
    target: { value: "largest" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
  expect(screen.getByLabelText("City")).toHaveValue("All cities");
});
it("validates the form, updates estimates and keeps model choices dependent on make", () => {
  render(
    <FairPrice
      model={populated.fairprice.data.model as FairModel}
      full={false}
    />,
  );
  expect(screen.getByLabelText("Model")).toHaveValue("Civic");
  fireEvent.change(screen.getByLabelText("Make"), {
    target: { value: "Toyota" },
  });
  expect(screen.getByLabelText("Model")).toHaveValue("Corolla");
  fireEvent.change(screen.getByLabelText("Mileage (km)"), {
    target: { value: "-1" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Check price" }));
  expect(screen.getByText(/mileage km must be between/)).toBeVisible();
  fireEvent.change(screen.getByLabelText("Mileage (km)"), {
    target: { value: "50000" },
  });
  expect(screen.queryByText("Check your inputs")).toBeNull();
  fireEvent.change(screen.getByLabelText("Asking price (PKR, optional)"), {
    target: { value: "1" },
  });
  expect(screen.getByText("Below the estimated market level")).toBeVisible();
});
it("renders all supported page bodies and model filtering", () => {
  const view = render(<Market bundle={populated} full={false} />);
  fireEvent.change(screen.getByLabelText("Model"), {
    target: { value: "Toyota / Corolla" },
  });
  expect(
    screen.getByRole("button", { name: "Quality-adjusted" }),
  ).toBeDisabled();
  view.rerender(<Seasons bundle={populated} full={false} />);
  expect(screen.getByText("Not enough history for seasonality")).toBeVisible();
  view.rerender(<Drivers bundle={populated} full={false} />);
  expect(screen.getByText("Held-out predictive performance")).toBeVisible();
  view.rerender(<About bundle={populated} full={false} />);
  expect(screen.getByRole("link", { name: /GitHub/ })).toHaveAttribute(
    "rel",
    "noreferrer",
  );
  view.rerender(
    <Empty title="Unavailable" detail="Collect more observations" />,
  );
  expect(screen.getByText("Collect more observations")).toBeVisible();
});
