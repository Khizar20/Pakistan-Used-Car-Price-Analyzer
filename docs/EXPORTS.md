# Public data contract, version 1.0.0

Run `.venv/Scripts/tracker.exe export` on Windows, or `.venv/bin/tracker export`
on Linux. The command reads a single consistent observation snapshot from the
existing normalized SQLite database, then recomputes analysis and public projections.
It never migrates or writes to the source database. It does not reuse private reports.

Options are `--database`, `--output` (default `web/public/data`) and
`--types-directory` (default `web/src/types`). Existing generated files are replaced;
unrelated files are retained. No website build or deployment occurs in this phase.

## Files and populations

Each JSON file contains `schema_version`, `generated_at`, `bundle_id` and `data`.
Unavailable results use `status: insufficient_data`, an explicit reason, null
unavailable estimates and empty unavailable series. Zero events are distinguishable
from no comparable follow-up. Empty databases also produce all eight valid files.

| File | Public data |
| --- | --- |
| `meta.json` | UTC generation time, UTC observation date range, counts, analysis basis and caveats |
| `index.json` | Raw matched-cohort and quality-adjusted weekly indexes, intervals, cohorts and per-make series |
| `drops.json` | Eligible counts, drop share, event-size and time-to-first-drop distributions, segmented survival curves |
| `seasonality.json` | Weekday exposures, volume trends and the gated monthly/weekly decomposition status |
| `drivers.json` | Coefficients and intervals, held-out metrics, SHAP, dependence curves and capped hashed residual diagnostics |
| `fairprice.json` | Available model, coefficients, transformations, levels, numeric ranges, defaults and residual uncertainty |
| `models.json` | Latest active nonduplicate make/model counts, usable-price counts and median usable prices |
| `listings_sample.json` | At most 100 most recently observed drop events, with hashed identities and vehicle/city attributes |

Metadata counts all distinct observed listings, including inactive cars and candidates
for reposts. `run_count` counts published success/partial runs represented in those
observations, not failed attempts or published runs with no observations. Model-list
counts use one latest observation per active, nonduplicate car with make/model
attributes; price summaries additionally apply quality flags. They therefore need
not equal the all-history metadata population. A model with no usable prices has
a null median. Driver fitting uses complete latest priced observations as described
in [Methods](METHODS.md), including the latest-attribute history limitation.

Drop distributions contain observed events, not fabricated values for missing
follow-up. The sample can show a factual event even when there are too few cars
for an aggregate drop share. Sample rows sort by observation time descending, then
hash descending; repeated cars can have multiple events. `total_events` reports
the uncapped count. Driver diagnostics sort by hash and retain the first 200;
`diagnostics_total` reports the full count. Aggregate metrics use the full eligible
population. No full listing history or per-listing URL is exported.

## Privacy boundary

Public records are constructed from explicit fields, never by dumping source rows.
Seller names, contact details, precise addresses, source URLs, source identifiers
and internal listing IDs are excluded. Only city-level location is included.
An additional recursive scan rejects identifying field patterns and contact-like
text in labels, category keys, reasons and other public strings. Numbers remain
numeric so large PKR amounts are not mistaken for phone strings. Legitimate dates
and 64-character digest values are supported. If a label contains a contact pattern,
the export fails before replacing files; it does not silently redact a model level
and change the meaning of the coefficients.

Listing pseudonyms are SHA-256 of `public-listing:v1:` plus the database internal
listing identifier. They are stable within that database and differ from raw IDs;
they are not resistant to enumeration or proof of anonymity. Rebuilding the database
can change their mapping. Keep the full database and private analysis bundles local.
Pattern scans cannot semantically detect every personal name embedded in a mislabeled
vehicle attribute; source normalization, explicit fields and review remain necessary.

## Prediction evaluation

Coefficients use `term`, and the encoding uses an explicit ordered `spec.terms`
list. JSON object property order has no statistical meaning. Apply transforms for
year minus 2000, log(1 + km) and engine cc divided by 1000. Include intercept 1.
Construct make/model as `make + " / " + model`. For each categorical predictor,
the first level is the baseline, and subsequent terms are `column=level` indicators.
Use observed-mode defaults only for omitted optional inputs; median engine size
is the default when engine size is omitted. Reject unknown levels, missing required
inputs and numeric values outside the training ranges.

Evaluate the weighted sum in `spec.terms` order and exponentiate it. This estimates
the conditional median asking price. The approximate residual range is
`exp(sum ± interval_multiplier * residual_std_log)`, with multiplier 1.96.
`typical_error_percent` is held-out MAPE. The range is not a calibrated guarantee.
Python tests independently evaluate 20 cars from the published contract, including
a sorted-JSON round trip. Browser implementation and browser parity tests belong
to the later frontend phase.

## Schemas, declarations and refresh safety

Eight `*.schema.json` files and `contracts.ts` are generated from Pydantic serialization
schemas by the export command. These use JSON Schema draft 2020-12. TypeScript
declarations express shape; JSON Schema retains runtime bounds, patterns and formats.
Edit Python contracts and regenerate rather than hand-editing either artifact type.
Tests reject schema drift and validate every fixture/supported/empty export against
both Pydantic and the JSON Schemas. Generated declarations have also been checked
with TypeScript 5.7.3 using `tsc --noEmit --strict --target ES2020`.

The common `bundle_id` is SHA-256 of the eight public `data` bodies encoded with
Python `json.dumps(..., sort_keys=True, allow_nan=False)` and UTF-8. Generation time
is outside this digest. The writer rechecks it before writing. Consumers should
compare version, generation time and bundle ID across every file and retry a refresh
if they disagree. They do not need to reproduce Python's JSON number serialization.

Every data file must be strictly smaller than 500,000 UTF-8 bytes. The writer
validates the complete bundle and generated contracts before staging files. It
replaces individual files atomically, writes metadata last and restores previous
files on caught write errors. Abrupt termination or power loss can leave a mixed
bundle; common IDs allow consumers to refuse it. Directory-wide atomic replacement
across the data and types paths is not promised. Run one exporter at a time.
An oversized aggregate fails explicitly instead of silently truncating analysis;
further aggregation or a versioned contract change is then needed.

## Reproduction and publication

`make check` enforces at least 90% export coverage and runs offline schema,
fixture snapshot, privacy, size, prediction and write-recovery tests. The golden
snapshot uses two simulated fixture days and a frozen generation timestamp.
Source database preservation and repeated exports are integration-tested.

The committed local sample currently has 90 listings on one observation day, so
longitudinal/seasonal results are insufficient and driver category support is sparse.
Inspect generated diffs and caveats before committing refreshes. Do not commit
SQLite databases, private bundles or raw HTML. Public exports alone do not complete
the dashboard or establish the project's eventual collection-volume targets.
