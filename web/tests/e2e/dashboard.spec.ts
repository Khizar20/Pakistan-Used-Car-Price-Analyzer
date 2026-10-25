import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
const pages = ["market", "drops", "seasons", "drivers", "fair", "about"];

async function fixture(page: import("@playwright/test").Page) {
  await page.route("**/data/*.json", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: readFileSync(
        resolve("tests/fixtures", route.request().url().split("/").at(-1)!),
        "utf8",
      ),
    }),
  );
}
for (const theme of ["light", "dark"] as const)
  for (const width of [1280, 360])
    for (const dataset of ["real", "supported"]) {
      test(`visual and accessibility ${theme} ${width} ${dataset}`, async ({
        page,
      }) => {
        test.setTimeout(90000);
        if (dataset === "supported") await fixture(page);
        await page.setViewportSize({ width, height: 900 });
        await page.emulateMedia({
          colorScheme: theme,
          reducedMotion: "reduce",
        });
        for (const route of pages) {
          await page.goto(`/#${route}`);
          await expect(page.locator(`nav a[href="#${route}"]`)).toHaveAttribute(
            "aria-current",
            "page",
          );
          await expect(page.locator("main h1")).toBeVisible();
          await expect(page.getByRole("status")).toHaveCount(0);
          for (const chart of await page.locator(".chart-host").all()) {
            await chart.scrollIntoViewIfNeeded();
            await expect(
              chart.getByRole("button", { name: "Load chart", exact: true }),
            ).toHaveCount(0);
            await expect(chart.getByRole("status")).toHaveCount(0);
          }
          await page.evaluate(() => window.scrollTo(0, 0));
          await page.evaluate(() => document.fonts.ready);
          expect(
            await page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
          ).toBe(true);
          expect((await new AxeBuilder({ page }).analyze()).violations).toEqual(
            [],
          );
          await expect(page).toHaveScreenshot(
            `${route}-${dataset === "supported" ? "supported-" : ""}${theme}-${width}.png`,
            {
              fullPage: true,
              animations: "disabled",
            },
          );
        }
      });
    }
test("real data has truthful unavailable states, keyboard navigation and persistent theme", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("A trend needs more observations")).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();
  await page.getByRole("link", { name: "Fair price", exact: true }).click();
  await expect(
    page.getByText("Fair Price Check is not available yet"),
  ).toBeVisible();
  await expect(page.locator("main")).toBeFocused();
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await page.reload();
  await expect(page.locator(".app")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("link", { name: "Seasons", exact: true }).click();
  await expect(page.getByText(/more supported weeks needed/)).toBeVisible();
});
test("populated data supports chart tables, filters, models and fair-price inputs", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("/");
  await page.locator(".chart-host").first().scrollIntoViewIfNeeded();
  await expect(
    page.getByRole("button", { name: "Show data table" }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Show data table" }).first().click();
  await expect(page.getByRole("table")).toBeVisible();
  await page
    .getByRole("combobox", { name: "Model", exact: true })
    .selectOption("Toyota / Corolla");
  await expect(
    page.getByRole("button", { name: "Quality-adjusted" }),
  ).toBeDisabled();
  await page.getByRole("link", { name: "Price drops", exact: true }).click();
  await page
    .getByRole("combobox", { name: "City", exact: true })
    .selectOption("Karachi");
  await page
    .getByRole("combobox", { name: "Sort by", exact: true })
    .selectOption("largest");
  await page.getByRole("button", { name: "Reset filters" }).click();
  await expect(
    page.getByRole("combobox", { name: "City", exact: true }),
  ).toHaveValue("All cities");
  await page.getByRole("link", { name: "Fair price", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Make", exact: true })
    .selectOption("Toyota");
  await expect(
    page.getByRole("combobox", { name: "Model", exact: true }),
  ).toHaveValue("Corolla");
  await page.getByLabel("Mileage (km)").fill("-1");
  await page.getByRole("button", { name: "Check price" }).click();
  await expect(page.locator("#fair-error")).toContainText("must be between");
  await page.getByLabel("Mileage (km)").fill("50000");
  await page.getByLabel("Asking price (PKR, optional)").fill("1");
  await expect(
    page.getByText("Below the estimated market level"),
  ).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});
test("network and mixed-update errors are actionable and retry recovers", async ({
  page,
}) => {
  let broken = true;
  await page.route("**/data/meta.json", async (route) => {
    if (broken) await route.fulfill({ status: 503, body: "Unavailable" });
    else await route.continue();
  });
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("could not be loaded");
  broken = false;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("A trend needs more observations")).toBeVisible();
});

test("keyboard-only navigation opens the fair-price page", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("A trend needs more observations")).toBeVisible();
  for (let index = 0; index < 7; index++) await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Fair price", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(
    page.getByText("Fair Price Check is not available yet"),
  ).toBeVisible();
  await expect(page.locator("main")).toBeFocused();
});
test("theme follows the system until chosen and survives blocked storage", async ({
  page,
}) => {
  await page.addInitScript(() =>
    Object.defineProperty(window, "localStorage", {
      get() {
        throw new DOMException("Storage blocked");
      },
    }),
  );
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await expect(page.getByText("A trend needs more observations")).toBeVisible();
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator(".app")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await page.emulateMedia({ colorScheme: "light" });
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator(".app")).toHaveAttribute("data-theme", "light");
});
test("mixed bundles fail visibly and unknown hash routes remain safe", async ({
  page,
}) => {
  await page.route("**/data/meta.json", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      json: { ...(await response.json()), bundle_id: "a".repeat(64) },
    });
  });
  await page.goto("/#__proto__");
  await expect(page.getByRole("alert")).toContainText("being refreshed");
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await page.unroute("**/data/meta.json");
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("A trend needs more observations")).toBeVisible();
  await expect(page).toHaveTitle(/Market/);
});

test("a failed chart download keeps the rest of the dashboard usable", async ({
  page,
}) => {
  await fixture(page);
  await page.route("**/assets/ChartImplementation-*.js", (route) =>
    route.abort(),
  );
  await page.goto("/");
  await page.locator(".chart-host").first().scrollIntoViewIfNeeded();
  await expect(page.getByRole("alert")).toContainText(
    "This chart could not load",
  );
  await expect(page.getByRole("button", { name: "Reload page" })).toBeVisible();
  await page.getByRole("link", { name: "About the data", exact: true }).click();
  await expect(
    page.getByText("Useful evidence, with clear limits"),
  ).toBeVisible();
});

test("deferred charts preserve keyboard focus and expose their data", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("/#drivers");
  const host = page.getByRole("group", {
    name: "Held-out residuals",
    exact: true,
  });
  await host.getByRole("button", { name: "Load chart", exact: true }).focus();
  await expect(host).toBeFocused();
  const toggle = host.getByRole("button", { name: "Show data table" });
  await expect(toggle).toBeEnabled();
  await page.keyboard.press("Tab");
  await expect(toggle).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(host.getByRole("table")).toBeVisible();
});
