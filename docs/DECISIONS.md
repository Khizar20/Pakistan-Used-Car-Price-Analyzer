# Architecture decisions

## 2026-10-24: Python 3.10 is the project runtime

The implementation brief overrides the plan's Python 3.11+ statement. The project
uses the already-installed Python 3.10, advertises Python 3.10 or newer in package
metadata, targets `py310` in Ruff, checks against Python 3.10 in mypy and CI, and
avoids features introduced in Python 3.11.

## 2026-10-24: Phase 1 CLI commands are explicit stubs

The required Make targets invoke `tracker scrape`, `tracker analyze`, and
`tracker export`, while their implementations belong to later phases. Phase 1
exposes these commands in help and makes each return a clear message with a nonzero
exit status. This keeps the command contract visible without pretending later-phase
work exists.

## 2026-10-24: The Makefile supports Windows and CI paths

The default `PYTHON` points to `.venv/Scripts/python.exe` on Windows and
`.venv/bin/python` elsewhere. CI passes `PYTHON310=python` after GitHub Actions has
installed Python 3.10. Every executable Python tool runs through `PYTHON`.

## 2026-10-24: Continue public-page collection at the user's direction

After reviewing the site's terms, the user explicitly instructed continuation for
the educational project. This supersedes the earlier instruction to stop solely
because of those terms; it does not represent permission from the site. The
implementation retains robots checks, a descriptive contact User-Agent, rate
limiting, and stops at access challenges. Vehicle attributes and city-level
location are sufficient; seller contact information is unnecessary.

## 2026-10-24: Use HTTPX's built-in mock transport in offline tests

The polite-client tests use `httpx.MockTransport` instead of adding a separate HTTP
mocking library. It exercises the real HTTPX request/response path without sockets,
with injected clock, sleep, random jitter, and date providers.

## 2026-10-24: Preserve raw attribute strings until Phase 3

The source record keeps mileage, engine capacity, and displayed price as strings.
`price_pkr` is filled from the site's numeric structured offer or observed numeric
`data-price` attribute, never guessed from a title. Display-only and call-for-price listings retain `price_text` with a
null numeric price. Full currency parsing and normalization belong to Phase 3.
Unknown seller type remains null rather than inferring it from featured status.

## 2026-10-24: Minimized real HTML and observed model scope

BeautifulSoup's typed parser is used for the observed server-rendered markup; no
browser automation is needed. Caches retain only the vehicle markup needed by the
adapter. Fixture identifiers are replaced and descriptions/contact UI removed.
The initial ten models are ranked from the site's displayed approximate counts in
"View Cars by Model". A global page budget is allocated round-robin across these
model links, rather than fetching the budget for every model. The discovery page
does not count toward this budget. Scope discovery fails visibly if markup changes.

## 2026-10-24: Phase 2 writes raw staging tables, not Phase 4's schema

Phase 2 requires local persistence before Phase 3 cleaning and Phase 4 normalized
storage exist. `raw_vehicles` holds the latest validated source attributes and a
successful-detail-fetch flag; `raw_observations` holds the latest observation per
listing per UTC day. Whole pages are committed atomically. Source attributes are
stored without full URLs; a URL hash is retained, and the current search-page URL
is used when rehydrating a record. These tables preserve source strings for later
cleaning and are not the final listings/snapshots schema. Inactivity detection,
scheduled runs, and normalized migrations remain Phase 4 work.

## 2026-10-24: Detail budgets and partial results are explicit

The scrape command normally fetches details for every previously unseen listing.
An optional `--max-new-details` budget saves remaining summaries without claiming
their details were fetched. Missing or malformed detail pages retain summaries and
are retried on a later run; the command reports partial success with exit status 1.
Access blocks and server failures stop the run. Completed pages remain committed,
while an interrupted current page is rolled back. Successful known listings reuse
detail attributes and always take the current price (including null) from the list.

## 2026-10-24: Version the minimized cache after a live-markup regression

A live model-search run revealed empty JSON offers with valid numeric `data-price`
attributes. The sanitizer now retains this vehicle field, with real model-search
fixtures and a regression test. New runs use `raw/cache/v2` to avoid reusing older
same-day minimized pages that discarded the attribute.

## 2026-10-24: Pin the build backend in the installation lock

The earlier `pip freeze` output omitted setuptools and wheel, even though editable
installation disables build isolation. Both build requirements are now pinned in
the installation lock, with a regression test comparing the lock against package
metadata so a fresh setup does not rely on build tools left in a developer's venv.

## 2026-10-24: Recover verified detail pages with absent primary JSON

A real detail page omitted primary structured data while retaining JSON for
recommended cars. The parser may recover visible attributes only when a validated
canonical listing URL, heading, and matching visible "Ad Ref #" establish primary
identity. Unavailable fields remain null and are merged with that listing's search
summary. Recommended cars' offers and event metadata are never used as fallbacks.

## 2026-10-24: Phase 3 price quality policy

Currency parsing uses exact decimal arithmetic, accepts common lakh/lac/crore
spellings and Western/Indian comma grouping, and rejects negative values,
fractional rupees, ambiguous prose, or values beyond signed SQLite integers.
Prices are retained and flagged, not deleted. Defaults are a PKR 100,000 floor,
the three placeholder values specified in the plan, and strictly greater than
five raw MADs within an exact make/model/year cohort of at least five usable
prices. Missing/junk prices do not define the cohort distribution. Small or
incomplete cohorts skip the statistical check. When MAD is zero, any nonmedian
price is flagged; a constant cohort is unflagged. These are configurable quality
rules, not fair-value estimates. Source values remain available in raw staging.

## 2026-10-24: Conservative attribute normalization

Known make/model spellings use explicit, make-scoped alias maps rather than fuzzy
matching. Unknown make/model/city labels retain a normalized title-case label;
unknown closed categories (transmission, fuel, assembly) become null and are
flagged by the batch cleaner. CVT, DCT and AGS map to automatic for the intended
automatic-versus-manual analysis. Nationality alone does not establish assembly.
Mileage accepts whole kilometres only. Engine size accepts cc or explicitly
labelled litres, converted exactly to whole cc. Unsupported units and negative
or fractional output values become null. Free labels preserve their spelling
after Unicode and whitespace normalization; raw inputs are never overwritten.

## 2026-10-24: Reposts are conservative candidates, not deletions

Candidate keys require known make, model, model year, exact mileage, city and seller
type. Missing keys are not wildcards; absent seller type therefore prevents a
match. Usable prices must differ by no more than 5% of the smaller value. Known
variant/transmission/engine/fuel/assembly/body conflicts veto a match. Stable roots
are chosen by lexicographic `source:listing_id`, since source records lack original
posting dates. Compare with roots only to avoid transitive chains. `duplicate_of`
uses this qualified identity and `possible_duplicate` is a quality flag. Retain
every row and expose the heuristic's uncertainty; it is not proof of a repost.

## 2026-10-24: Phase 3 batch contract and source-price precedence

`clean_batch` accepts raw records, validated clean records, or its own complete
ordered DataFrame schema. Every row is validated with `CleanListing`; integers,
booleans, and strings use explicit nullable pandas dtypes. Features and the plural
set of quality labels are immutable tuples under the plan's `quality_flag` column
name. Statistical and duplicate flags are recomputed, so cleaning is idempotent
and a changed policy does not accumulate stale price flags. Raw source records
are never mutated; cleaned rows retain source identity and URL hashes only.

Valid structured prices take precedence; display text is parsed when the structured
value is absent or unusable. Conflicts and unusable structured values are visible
flags. Invalid attributes become null with flags; missing required cohort fields
are flagged as well. Free variant/body/color labels use lowercase normalized text.
The golden fixture is independently authored and compares the complete typed frame.
Pandas stubs are pinned for strict mypy. The Makefile additionally enforces 95%
aggregate cleaning coverage. Normalized storage integration remains Phase 4 work.

## 2026-10-24: Versioned SQLite schema for Phase 4

Migration `001_initial.sql` creates normalized listings, daily snapshots and run
bookkeeping without rewriting raw staging. SQLite `user_version` records the
migration level; newer or inconsistent normalized schemas fail visibly. The SQL
migration is packaged with the Python distribution. Timestamp mappings preserve
explicit UTC offsets. Database constraints enforce source identity, one snapshot
per listing/UTC date, foreign keys, nonnegative counts and one running scrape.
Quality flags are stored on listings and snapshots so historical price-quality
context is retained. No historical normalized runs are invented from raw staging.

## 2026-10-24: Daily snapshots and scoped disappearance semantics

Normalized snapshots keep the first observation per listing per UTC day; same-day
reruns may refresh listing attributes but never overwrite that day's snapshot.
Run publication (listings, snapshots, activity state and successful run closure)
is one transaction. Raw staging remains recoverable per-page progress. A run left
running after a crash must be explicitly recovered before another run starts.

Absences count only on distinct successful UTC days for the same source and exact
ordered search-page scope. Failures and partial runs do not advance absence
counters; a sighting resets them and reactivates a listing. A sighting under a
different scope protects the listing from the old scope's absence counts. Three
eligible missing runs mark a listing inactive and create a null-price inactive
snapshot; an absent price is not carried forward as if freshly observed. Bounded
page windows cannot prove a sale or removal: inactivity means disappearance from
the tracked window and may simply mean that an ad moved beyond that window.

## 2026-10-24: Read-only status and consistent backups

Status opens existing databases read-only and does not create files or migrate
them. It can also report the legacy staging-only state. Backups use SQLite's
online backup API, include committed WAL data, verify integrity, and exclusively
create a new destination rather than overwriting a file. A failed copy removes
only its newly created incomplete destination. Database journal sidecars and
default backups are ignored by Git along with the database itself.

## 2026-10-24: Audit and publish complete scrape results

The collector reports its exact ordered page scope and committed raw-page progress
to the normalized run record. Once collection finishes, the entire run is cleaned
as one batch and published atomically. Detail failures yield a partial run that
retains summaries without advancing absences; other failures retain raw progress
but publish no normalized rows. Counters describe logical page reads, including
cache hits and discovery, not individual HTTP attempts. `--model-path` pins observed
model paths for reproducible scope. Recovery is explicit after a killed process.

Status, backup, migration and interrupted-run recovery are CLI operations. Scheduling
is documentation-only: no task, cron entry, notification, Git commit or live scrape
is installed automatically. The Makefile enforces 90% aggregate storage coverage.

## 2026-10-25: Pure analysis contracts and model encoding

Analysis functions consume observation DataFrames and return validated result
objects with explicit `ok` or `insufficient_data` status. Invalid observation
identities/times fail visibly; missing or flagged prices remain in longitudinal
inputs but are excluded from price estimation. Repost candidates are excluded.
Numeric regression terms are model year minus 2000, log(1 + mileage), and engine
litres; category levels and their baseline are explicit and deterministic.
Regression requires full column rank and finite uncertainty. HC3 errors are used
for cross-sectional models and listing-clustered errors for repeated observations.
Typed protocols isolate untyped third-party APIs without weakening strict mypy.
SHAP and its new runtime dependencies are pinned for Python 3.10 reproducibility.

## 2026-10-25: Weekly indexes require connected support

Use the latest valid observation per listing/week, then a median in each exact
make/model/year cohort with at least five listings. The chain link is the weighted
mean of matched cohort price ratios, using previous-week listing counts as weights.
Missing calendar weeks or no common supported cohorts break the index instead of
being interpolated. Per-make series apply the same rule. Quality adjustment fits
log prices on the common attributes and week dummies with listing-clustered errors,
normalizing the first week to 100. Unsupported adjustment returns its own status
while a supported raw index remains available. Effects are associations, not causes.

## 2026-10-25: Observed drops, censoring and unknown fair-value buckets

Drop shares use listings with at least one adjacent pair of usable prices. Unknown
or flagged observations break price comparisons. Drop sizes are event-weighted
medians; shares count each listing once. Event times are the first detection, not
the unobserved exact moment of change. Survival starts at the first observation
in the input window; drop risk requires an initially usable price and is censored
at the last usable price. Disappearance uses the first inactive observation and
otherwise censors at last observation, preserving the bounded-scope caveat.
Kaplan-Meier curves use lifelines with confidence intervals and minimum segment
sizes. Unreached median survival is null, never infinity in JSON. Pricing buckets
require a supplied positive `fair_price_pkr`; without one they are unknown, not
invented from the listing's own asking price or an in-sample prediction.

## 2026-10-25: Exposure-aware local weekdays and gated seasonality

Weekday volume uses Asia/Karachi dates and divides by actually observed days of
each weekday, requiring at least two of every weekday. Price-change rates divide
by adjacent usable comparisons, not all listings. Without complete posting-date
metadata, volume is explicitly first-observed counts, not true posting volume.
Metadata trends describe only observed listings and remain selection-biased.
STL with period 52 activates after 79 finite contiguous weekly points, covering at
least 18 months; gaps are not interpolated. Monthly summaries of the weekly
seasonal component are exploratory associations in the input series' units, not
reliable causal monthly effects. Short histories return weeks needed and a reason.

## 2026-10-25: Validated price models and a portable prediction contract

Driver models use one latest observation per listing, complete usable attributes,
HC3 linear uncertainty, and deterministic grouped cross-validation. Each fold
learns its encoding, coefficients, boosting model and median-by-model baseline
only from training listings. Report held-out PKR MAE, percentage MAPE and R squared.
Optional predictors require complete coverage; rare categorical levels, deficient
rank and insufficient observations yield explicit insufficient-data results.
Tree SHAP values explain log-price predictions; dependence curves average over
observed cars. These describe associations within the selected sample.

The Fair Price contract includes transformations, category baselines, coefficients,
numeric ranges, explicit defaults and residual log standard deviation. Predictions
reject unknown categories and numeric extrapolation. The reported range uses
1.96 residual standard deviations and assumes approximately Gaussian log errors;
it is not a calibrated guarantee. The point estimate is a conditional median,
without a retransformation correction. Twenty reference cars test exact formula
parity. No historical fair-value buckets are inferred from in-sample predictions.

## 2026-10-25: Read-only analysis and private result bundles

Analysis opens existing schema-version-1 SQLite databases in URI read-only mode
and reads committed success/partial observations in a consistent transaction.
It does not initialize or migrate storage. Decode and validate JSON list fields
before passing observations to pure analysis functions. The attribute-history
limitation is explicit: current listing attributes join historical price snapshots.
For seasonal decomposition prefer the supported adjusted index, then matched
cohorts; do not substitute an unsupported changing-composition raw median series.

Write all four typed results and provenance together to one finite JSON file in a
new private directory; refuse any existing output directory. Insufficient data is
a valid result, not a CLI failure. Report it without creating findings. Bundles
include internal IDs, are ignored by Git and are separate from the Phase 6 public
export contract. Make enforces at least 90% coverage over the analysis package.

## 2026-10-25: Versioned public contracts and generated frontend declarations

Each of eight public files has a version-1.0.0 envelope, generation timestamp and
common content digest so consumers can detect mixed bundles. Public driver
coefficients use `term`, and prediction encodings use `terms`; internal identity
fields are excluded from contracts. Residual/sample identities must be SHA-256
hex digests. Samples are capped at 100 rows and diagnostics at 200. Public numeric
values must be finite and each serialized data file must stay below 500,000 bytes.

Generate JSON Schema draft 2020-12 and TypeScript declarations directly from the
Pydantic serialization schemas. A deliberately small schema translator supports
the constructs emitted by these contracts and refuses unsupported constructs.
Tests validate schemas with pinned jsonschema tooling and compare generated
artifacts byte-for-byte with committed files. TypeScript carries structural types;
runtime constraints such as numeric ranges remain in JSON Schema.
