# Pakistan Used-Car Price Tracker: Implementation Plan

A phase-by-phase build spec for Claude Code or Codex: scraping, analysis, a minimal dashboard, and tests for every module.

## 0. How to hand this to a coding agent

1. Create an empty repo and save this plan as `docs/PLAN.md`.
2. Add a short `AGENTS.md` (Codex) or `CLAUDE.md` (Claude Code) that says: *Read docs/PLAN.md. Build one phase at a time. Write tests before or alongside code. Do not start the next phase until `make check` passes. Commit after every phase.*
3. Prompt the agent: *Implement Phase 1 of docs/PLAN.md.* Then repeat per phase. Smaller steps give better results than one giant prompt.
4. Before Phase 2, tell the agent to open the live site and save real HTML fixtures. Site markup changes, so selectors in this plan are intentionally not specified. The agent must inspect the real pages.

## 1. Project summary

**Question the project answers:** What drives used-car prices in Pakistan, how fast do asking prices fall, and does the market move seasonally?

**Primary data source:** PakWheels used-car listings (richest structured attributes). The scraper is built behind an adapter interface so OLX (phones, cars) can be added later without touching the rest of the pipeline.

**Outputs:**

- A SQLite database of listings and price snapshots collected daily over several weeks.
- An analysis layer producing a price index, price-drop statistics, a seasonality view, and a price-driver model.
- A static, fast, minimal dashboard (React) deployed to GitHub Pages, including a **Fair Price Check** tool that estimates what a car should cost.
- A test suite and CI covering every module.

**Why this stands out:** original longitudinal data (not a Kaggle CSV), an interpretable model, honest limitations, and a polished product-grade UI.

## 2. Ground rules: ethics, legality, honesty

- Read and respect `robots.txt` and each site's terms. Scrape only public listing pages. Do not log in, bypass CAPTCHAs, or evade blocking.
- Rate limit: at most 1 request per 2 seconds per host, with random jitter, exponential backoff on 429/5xx, and a descriptive User-Agent that includes a contact email.
- Never collect or publish personal data: no seller names, phone numbers, or exact addresses. Keep only city-level location and hashed listing IDs in public exports.
- Do not commit raw HTML or the full database if terms discourage redistribution. Commit only aggregated JSON and tiny anonymized fixtures needed for tests.
- The README must state that data is collected for personal, educational analysis, and list all limitations (see section 16).

## 3. Architecture and tech stack

```
 scrape (httpx + selectolax)  ->  raw/ (gitignored HTML cache)
        |
        v
 parse -> clean/normalize -> SQLite (listings, snapshots)
        |
        v
 analysis (pandas, statsmodels, lifelines)  ->  export JSON (versioned schema)
        |
        v
 static dashboard (Vite + React + TypeScript)  ->  GitHub Pages
```

| Layer | Choice | Reason |
| --- | --- | --- |
| Language | Python 3.11+ | Standard for data work |
| HTTP / parsing | httpx, selectolax (BeautifulSoup fallback), Playwright only if a page truly needs JS | Fast, small, testable |
| Storage | SQLite via SQLAlchemy 2.0 | Zero setup, portable |
| Analysis | pandas, numpy, statsmodels, scikit-learn, lifelines | Interpretable stats first |
| Validation | pydantic v2 | Typed records and export schemas |
| CLI | Typer | `tracker scrape`, `tracker analyze`, `tracker export` |
| Tooling | uv or pip-tools, ruff, mypy, pytest, pytest-cov, hypothesis, pre-commit | Quality gates |
| Frontend | Vite, React 18, TypeScript, Recharts (heavily themed), CSS variables, no UI kit | Minimal and fast; full design control |
| Frontend tests | Vitest, React Testing Library, Playwright, axe-core | Unit, e2e, accessibility |
| CI/CD | GitHub Actions, GitHub Pages | Free |

The dashboard is **static**: it reads JSON files produced by the pipeline. No backend to host, and recruiters can open it instantly.

## 4. Repository layout

```
.
├── docs/PLAN.md
├── AGENTS.md / CLAUDE.md
├── Makefile                  # make setup | scrape | analyze | export | test | check
├── pyproject.toml
├── src/tracker/
│   ├── config.py             # settings, paths, rate limits
│   ├── models.py             # pydantic records
│   ├── scraping/
│   │   ├── base.py           # SourceAdapter protocol
│   │   ├── http.py           # polite client: rate limit, retry, cache
│   │   └── pakwheels.py      # list + detail parsers
│   ├── cleaning/
│   │   ├── prices.py         # lakh/crore parsing, outlier rules
│   │   ├── attributes.py     # mileage, engine cc, make/model normalization
│   │   └── dedupe.py
│   ├── storage/
│   │   ├── schema.py         # SQLAlchemy tables
│   │   └── repo.py           # upserts, snapshot logic
│   ├── analysis/
│   │   ├── index.py          # price index
│   │   ├── drops.py          # drop detection, survival
│   │   ├── seasonality.py
│   │   └── drivers.py        # hedonic model + diagnostics
│   ├── export/
│   │   ├── schema.py         # versioned JSON contracts
│   │   └── writer.py
│   └── cli.py
├── tests/
│   ├── fixtures/html/        # saved list and detail pages
│   ├── unit/ integration/ property/
├── web/
│   ├── public/data/          # exported JSON lands here
│   ├── src/ (components, charts, lib, styles)
│   └── tests/ (unit, e2e)
└── .github/workflows/ (ci.yml, pages.yml, optional scrape.yml)
```

## 5. Data model

**listings** (one row per real-world listing, stable over time)

- `id` (internal), `source`, `source_listing_id`, `url_hash`
- `first_seen_at`, `last_seen_at`, `is_active`, `disappeared_at`
- `make`, `model`, `variant`, `model_year`, `mileage_km`, `engine_cc`, `transmission`, `fuel_type`, `body_type`, `assembly` (local or imported), `color`, `city`, `registered_city`, `seller_type` (individual or dealer), `is_featured`, `has_photos_count`
- `features` (JSON list: ABS, airbags, sunroof, etc.)

**snapshots** (one row per listing per scrape day)

- `listing_id`, `observed_at`, `price_pkr`, `is_active`, `scrape_run_id`

**scrape\_runs**

- `id`, `started_at`, `finished_at`, `pages_fetched`, `listings_seen`, `errors`, `status`

**Key rule:** a price change is detected by comparing consecutive snapshots of the same listing. A listing missing for 3 consecutive runs is marked inactive (likely sold or removed). Treat this as a *proxy* for sold, not proof.

Indexes on `(listing_id, observed_at)`, `(make, model, model_year)`, and `source_listing_id`.

## 6. Phase 1: Scaffolding and quality gates

**Build:** repo structure, `pyproject.toml`, Makefile, ruff and mypy (strict on `src/`), pytest with coverage, pre-commit hooks, empty Typer CLI, CI workflow running lint, types, and tests on every push.

**Tests:** a smoke test that imports the package and runs `tracker --help`.

**Done when:** `make check` runs ruff, mypy, and pytest green on a clean clone.

## 7. Phase 2: Scraper

**Build:**

- `http.py`: a polite client with per-host rate limiting, jitter, retries with backoff, timeouts, robots.txt check, and an on-disk HTML cache keyed by URL and date (so reruns during development do not hit the site).
- `base.py`: `SourceAdapter` protocol with `iter_listing_pages(filters)`, `parse_list_page(html)`, `parse_detail_page(html)`.
- `pakwheels.py`: crawl used-car search results for a defined scope (start with the top 10 to 15 models by volume, so data per model is dense enough to analyze), then fetch detail pages for attributes. Only refetch the detail page for listings not seen before; for known listings, read price from the list page.
- Parsers are **pure functions** from HTML string to typed records. No network inside parsers.
- Graceful degradation: a missing field yields `None` plus a logged warning, never a crash. A parser that returns zero listings from a fixture page must raise, so silent breakage is caught.

**Tests:**

- Fixture-based parser tests using saved real pages (list and detail, plus one edge-case page with missing fields). Assert exact extracted values.
- HTTP client tests with `respx` or `pytest-httpx`: retry on 503, respect 429 `Retry-After`, honor rate limit (use a fake clock), blocked by robots.txt, cache hit avoids network.
- Contract test: every adapter satisfies the `SourceAdapter` protocol.
- A **live smoke test** marked `@pytest.mark.live`, excluded from CI by default, that fetches one real page and checks the parser still finds listings. Use it to detect site changes.

**Done when:** `tracker scrape --source pakwheels --limit-pages 3` stores parsed records locally and all tests pass offline.

## 8. Phase 3: Cleaning and normalization

**Build:**

- **Price parsing:** handle formats such as `PKR 35 lakh`, `PKR 1.25 crore`, `Rs 3,500,000`, `Call for price`, and return `None` for non-numeric.
- **Outlier and junk rules:** drop or flag placeholder prices (e.g., 1, 123456, 1234567), prices under a sane floor, and prices more than 5 median absolute deviations from the make/model/year group. Flag rather than delete; keep `quality_flag` so analysis can choose.
- **Attributes:** mileage (`45,000 km`), engine (`1300 cc`), normalize make and model aliases (e.g., spelling variants), standardize transmission, fuel, assembly, and city names.
- **Dedupe:** the same car reposted under a new ID. Heuristic key on make, model, year, mileage, city, seller type, with a fuzzy price tolerance; mark `duplicate_of`.

**Tests:**

- Table-driven unit tests for every parser with many real-world strings, including bad input.
- Property tests (Hypothesis): parsing a formatted price round-trips; cleaning is idempotent (cleaning twice equals cleaning once); output never contains negative prices or mileage.
- Dedupe tests with constructed near-duplicate and near-miss pairs.

**Done when:** cleaning a raw fixture batch yields a typed DataFrame matching an expected golden file.

## 9. Phase 4: Storage and scheduling

**Build:**

- SQLAlchemy schema and Alembic migration (or a versioned `schema.sql`).
- `repo.py`: idempotent `upsert_listing`, `record_snapshot` (skip duplicate same-day snapshot), `mark_inactive_after(n_runs=3)`, and run bookkeeping.
- CLI: `tracker scrape`, `tracker status` (rows, last run, errors), `tracker backup`.
- Scheduling docs: a daily cron or Windows Task Scheduler entry (recommended, because home IPs are less likely to be blocked than cloud runners). Optional GitHub Actions cron workflow, with a note that it may be blocked.

**Tests (in-memory SQLite):**

- Upserting the same listing twice creates one listing and one snapshot per day.
- Price change creates a second snapshot with the new price.
- A listing absent for 3 runs becomes inactive; reappearing reactivates it.
- Interrupted run leaves the DB consistent (transaction rollback test).

**Done when:** two simulated consecutive-day runs from fixtures produce the expected listing and snapshot counts.

## 10. Phase 5: Analysis

Build each as a pure function over a DataFrame, returning typed result objects, so it is testable without a database.

**5a. Price index (`index.py`)**

- Weekly **median price per make/model/year cohort**, then a chain-weighted overall index (base = 100 at first week).
- Better: a **hedonic time-dummy regression**, `log(price) ~ model_year + log(mileage) + engine_cc + make/model + transmission + city + week`, where the week coefficients are the quality-adjusted index. Report both and explain why they differ.

**5b. Price drops (`drops.py`)**

- Among listings seen at least twice: share with at least one drop, median drop size (PKR and %), distribution of days to first drop.
- **Survival analysis** (Kaplan-Meier via lifelines): time from first seen to first price drop and time to disappearance, grouped by price-vs-fair-value bucket (overpriced, fair, underpriced), seller type, and city. Treat still-active listings as censored.
- Insight to surface: how overpriced listings behave compared with fairly priced ones.

**5c. Seasonality (`seasonality.py`)**

- With only a few weeks of data, **monthly seasonality cannot be estimated reliably**. Be honest about this. Implement and show:
  - day-of-week effects on posting volume and price changes (estimable),
  - posting-date volume trends from listing metadata where available,
  - a seasonal decomposition (STL) function that activates automatically once at least 18 months of weekly points exist, otherwise returns `insufficient_data` and the dashboard shows a clear explanation.
- Optionally extend later by logging long-term and merging with public historical series (e.g., State Bank policy rate, PKR/USD, auto-sector news) as external explanatory context.

**5d. Price drivers (`drivers.py`)**

- Primary model: **log-linear regression** with robust standard errors. Report coefficients as percentage effects (e.g., an automatic transmission is associated with X% higher price, holding other factors fixed).
- Secondary model: gradient boosting (LightGBM or sklearn) with SHAP for non-linear effects such as the depreciation curve vs. age and mileage.
- Evaluate with grouped cross-validation (group by listing, never leak the same car across folds). Report MAE, MAPE, and R squared, and compare to a naive median-by-model baseline.
- Residual diagnostics saved as export data (residual vs. fitted, by make).
- Export the **linear model's coefficients** so the dashboard can compute Fair Price Check in the browser without a server.

**Tests:**

- **Synthetic ground truth:** generate fake listings where price follows a known formula plus noise, with a known weekly trend and known drop probability; assert the index recovers the trend, the regression recovers coefficients within tolerance, and drop stats match the generator.
- Edge cases: single listing, all-same prices, empty frames, missing columns, sparse cohorts below the minimum sample size (must return `insufficient_data`, not a misleading number).
- Determinism: fixed seeds give identical results.
- No-leakage test for grouped cross-validation.

**Done when:** `tracker analyze` runs on fixture data and writes all result objects; analysis coverage is at least 90 percent.

## 11. Phase 6: Export contract

**Build:** `tracker export` writes versioned JSON to `web/public/data/`:

| File | Contents |
| --- | --- |
| `meta.json` | schema\_version, generated\_at, date range, run count, listing count, data caveats |
| `index.json` | weekly overall index (raw and hedonic), per-make series |
| `drops.json` | drop shares, size distributions, survival curves, by segment |
| `seasonality.json` | day-of-week effects, status field for monthly seasonality |
| `drivers.json` | coefficients with confidence intervals, partial dependence curves, model metrics |
| `fairprice.json` | coefficients, category levels, valid ranges, residual standard deviation |
| `models.json` | make/model list with listing counts and median prices |
| `listings_sample.json` | anonymized, capped sample for the drops table (no sellers, no phones, no URLs) |

Define every file with pydantic models and also emit JSON Schemas into `web/src/types/` (generate TypeScript types from them so frontend and backend cannot drift).

**Tests:** schema validation of every output; snapshot tests of export from a fixed fixture DB; a test asserting no field matching phone, email, name, or URL patterns appears in public exports; file size budget (each file under 500 KB).

## 12. Phase 7: Dashboard design brief

This brief follows the frontend-design guidance: ground the design in the subject, make a few deliberate choices, and avoid generic template looks.

**Subject and audience:** people in Pakistan deciding whether a used car is fairly priced, plus recruiters evaluating the analysis. Primary job: let someone understand the market in 10 seconds and check a specific car's price in 30.

**Design direction: the motorway sign.** Pakistani motorway signage is deep green with white lettering and strong, legible type. Borrow that clarity: calm, high-legibility, utilitarian, quietly Pakistani without being decorative.

**Color tokens**

| Token | Hex | Use |
| --- | --- | --- |
| Paper | #F3F4F1 | Page background |
| Ink | #14201A | Text |
| Motorway | #0B5D3B | Primary accent, falling prices (good for buyers), key chart line |
| Signal | #B4432F | Rising prices, warnings |
| Chalk | #D8DDD5 | Hairlines, grid, borders |
| Marker | #E3A72F | Single highlight (the current selection) |

Provide a dark theme: background #0F1714, text #E6EBE7, same accents slightly lightened for contrast. Follow the system setting and offer a toggle. All text and chart colors must meet WCAG AA contrast.

**Typography:** one family, **Schibsted Grotesk** (variable), self-hosted with a system sans fallback. Use tabular numerals for all figures (`font-variant-numeric: tabular-nums`). Scale: 14, 16, 20, 28, 44, 72 px. Body line length under 70 characters, left-aligned throughout. Show prices in lakh and crore (e.g., PKR 32.5 lakh) with an option to switch to full numbers.

**Avoid:** all-caps labels, accenting a single headline word, cream and terracotta, black and neon, identical rounded cards with shadows, gradient washes, monospace for labels, arrows on every link, and entrance animations on every section.

**Layout (desktop, left-aligned, generous whitespace, one narrow column of navigation)**

```
+--------+-----------------------------------------------+
| Market | Used cars in Pakistan cost 2.1% less than      |
| Drops  | four weeks ago.                                |
| Seasons|  (one sentence, generated from data)          |
| Drivers|                                               |
| Fair   |  [ price index line, full width, 280px tall ] |
| price  |  Corolla | Civic | Alto | Cultus | All  (tabs) |
| About  |                                               |
|        |  Listings tracked   Last updated   Days of data |
+--------+-----------------------------------------------+
```

The headline is a **sentence written from the data**, not a big-number tile. It is the memorable element. Everything else stays quiet: thin Chalk rules, no card backgrounds, no shadows, small radius (4 px) used consistently.

**The one moment of delight:** on the Fair Price Check page, as the user changes year, mileage, or transmission, the estimated price range updates live and a single Marker-colored dot slides along the depreciation curve to show where that car sits. This is the only motion that is not directly caused by user action; keep it under 250 ms and respect `prefers-reduced-motion`.

**Pages**

1. **Market:** the data-written headline, index chart (toggle raw vs. quality-adjusted), model tabs, a short methodology note.
2. **Price drops:** share of listings that dropped, median drop size, time-to-first-drop survival curves by pricing bucket, and a sortable, filterable table of recent drops (make, model, year, city, old price, new price, change %, days listed).
3. **Seasons:** day-of-week chart now; the monthly view shows a clear, plain explanation of why it is unavailable yet and how many more weeks of data are needed. Never fake a pattern.
4. **Drivers:** a horizontal bar chart of effects in percent (transmission, assembly, city, seller type, each feature) with confidence intervals; depreciation curves for age and mileage; plain-language caption under each chart.
5. **Fair price:** form (make, model, year, mileage, transmission, city) that returns an estimated range and a verdict: below, near, or above the market, with the model's typical error stated.
6. **About the data:** collection method, dates, counts, limitations, ethics note, GitHub link.

**Copy rules:** sentence case, active voice, plain words. Buttons say what they do (Check price, Reset filters). Empty and error states say what happened and what to do next. No apologies, no jargon like hedonic on the surface (explain it as *quality-adjusted* and link to the method in About).

**Quality floor:** responsive down to 360 px (tables become stacked rows), visible keyboard focus, full keyboard navigation, charts have text alternatives and a data-table toggle, reduced motion respected, no layout shift, total JS under 250 KB gzipped, Lighthouse scores at least 95 on performance, accessibility, and best practices.

## 13. Phase 8: Frontend build

**Build order:**

1. Vite + React + TypeScript project, strict TS, ESLint, Prettier, CSS variables for tokens, theme provider.
2. Typed data layer: fetch JSON, validate against generated types (zod or generated validators), loading and error states, in-memory cache.
3. Layout shell and navigation, then pages in the order listed above.
4. Charts as small reusable components (`LineChart`, `BarWithCI`, `SurvivalChart`, `DepreciationCurve`) with a shared theme file; each accepts data and renders an accessible fallback table.
5. Fair Price Check logic as a **pure TypeScript module** (`lib/fairPrice.ts`) that evaluates exported coefficients; it must match the Python model's predictions.
6. Headline sentence generator as a pure function over `index.json` with unit tests for rising, falling, flat, and insufficient-data cases.
7. Number and currency formatting helpers (lakh/crore, percent, dates).

**Tests:**

- **Unit (Vitest):** formatting helpers, headline generator, fair price calculator, data validators.
- **Parity test:** Python exports 20 reference cars with predicted prices; a TypeScript test asserts `fairPrice.ts` reproduces them within 0.5 percent. This is the most important cross-language test.
- **Component (React Testing Library):** each chart renders from fixture data, empty and error states render, filters and sorting in the drops table work, the Fair Price form validates inputs.
- **E2E (Playwright):** load each page, switch model tabs, use Fair Price Check, toggle theme, navigate by keyboard only, mobile viewport pass.
- **Accessibility:** axe-core assertions on every page in both themes.
- **Visual regression:** Playwright screenshots of key pages in light and dark at desktop and mobile widths.

**Done when:** `npm run check` (lint, types, unit, build) is green, e2e passes against the production build, and Lighthouse targets are met.

## 14. Testing strategy summary

| Module | Test types | Target |
| --- | --- | --- |
| HTTP client | Mocked network, fake clock | 95% |
| Parsers | Real HTML fixtures, edge-case pages | 95% |
| Cleaning | Table-driven, property-based, golden files | 95% |
| Storage | In-memory DB, transaction tests | 90% |
| Analysis | Synthetic ground truth, edge cases, determinism | 90% |
| Export | Schema, snapshot, privacy scan, size budget | 90% |
| Frontend logic | Unit and parity tests | 90% |
| Frontend UI | Component, e2e, accessibility, visual regression | Key flows |

Rules for the agent:

- No network in the default test run. Live tests are opt-in with a marker.
- Every bug fix adds a regression test first.
- Use fixed random seeds and a frozen clock for deterministic tests.
- CI fails below 85 percent backend and 80 percent frontend coverage.
- Fixtures are small, anonymized, and documented in `tests/fixtures/README.md`.

## 15. CI/CD and deployment

- `ci.yml`: on push and PR, run ruff, mypy, pytest with coverage (backend), then npm lint, typecheck, Vitest, build, and Playwright (frontend). Cache dependencies.
- `pages.yml`: on merge to main, build `web/` and deploy `web/dist` to GitHub Pages. The committed `web/public/data/` JSON is the data source for the deployed site.
- Optional `scrape.yml`: scheduled run uploads results as an artifact. Document that cloud IPs may be blocked, and that the reliable path is a local scheduled run followed by `tracker export` and a commit of the new JSON.
- Weekly data refresh routine: `tracker scrape` runs daily locally; once a week run `tracker analyze && tracker export`, review the diff, commit, push, and Pages redeploys.

## 16. README and portfolio checklist

The README is what a recruiter reads first. Include:

1. One-line question and a live dashboard link at the top, with a screenshot.
2. **Key findings** (3 to 5 bullets with real numbers, e.g., how much more automatic cars cost, how often listings drop, median days to first drop).
3. How it works: the architecture diagram and the data flow.
4. Methods in plain language: price index, survival analysis, regression, and why each was chosen.
5. **Limitations, stated plainly:** asking prices are not transaction prices; a disappeared listing is only a proxy for sold; selection bias toward listings on one platform; short collection window means monthly seasonality is not yet estimable; scraping scope limited to chosen models.
6. Reproduce it: setup, `make` commands, how to run tests.
7. Ethics and data note.
8. Roadmap: add OLX phones adapter, more months of data, external macro series.

Also write one short blog-style post in `docs/findings.md` explaining the most surprising result. This is what you will talk about in interviews.

## 17. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Site markup changes break parsers | Fixture tests plus live smoke test; parsers raise on zero results |
| Blocking or CAPTCHAs | Slow rate, cache, local IP, stop and reduce scope rather than evade |
| Too little data per model | Limit scope to top models; set minimum sample sizes; show insufficient-data states |
| Misleading conclusions from asking prices | Prominent limitations; frame as asking-price market |
| Terms of service concerns | Public pages only, low volume, no personal data, no raw redistribution |
| Overfitting the model | Grouped cross-validation, baseline comparison, interpretable primary model |

## 18. Definition of done

- [ ] At least 4 weeks of daily snapshots collected, with at least 5,000 distinct listings
- [ ] `make check` green on a clean clone (backend and frontend)
- [ ] Coverage thresholds met; no network needed for tests
- [ ] All six dashboard pages implemented, both themes, mobile responsive
- [ ] Fair Price Check matches the Python model (parity test passing)
- [ ] Lighthouse 95+ on performance, accessibility, best practices
- [ ] No personal data in any committed file (privacy scan passing)
- [ ] README with findings, limitations, screenshot, and live link
- [ ] Deployed to GitHub Pages and linked from your GitHub profile

## 19. Suggested timeline

| Week | Work |
| --- | --- |
| 1 | Phases 1 to 4; **start the daily scrape as early as possible**, because collection time is the bottleneck |
| 2 | Phase 5 on early data using synthetic tests; Phase 6 export |
| 3 | Phases 7 and 8 dashboard on real exported data |
| 4 | Polish, tests, CI, README, findings write-up, deploy |
| 5+ | Keep collecting; re-run analysis and update seasonality status |

## 20. Product extension: daily operation, city comparisons and vehicle imagery

Requested after Phase 8: make daily refresh operational at 09:00 Asia/Karachi,
covering Karachi, Lahore, Islamabad and Rawalpindi. Implement stable collection
scopes, one-worker locking, backup, failed-run reporting and automatic local export.
Activate source collection only with access consistent with current source terms.
Keep the machine-on/logged-on scheduling limitation explicit.

Add current make/model/year/transmission city medians, quartiles, usable counts,
observation freshness and insufficient-sample states. Support comparing a selected
car across cities without implying that different trims/conditions are identical.
Use relevant licensed model-reference images with attribution; listing photos
require appropriate source permission and must not expose private/contact details.
Keep synthetic data separate from production. Version changed public contracts,
regenerate both languages, and run offline, UI, privacy and browser checks before
committing each completed module. Public hosting and longer collection remain
separate outstanding goals.
