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
