# Pakistan used-car price tracker

What drives used-car asking prices in Pakistan, and how do those prices change
over time? This project collects original observations for educational analysis.
The scraper is implemented; cleaning, analysis, exports, and the dashboard are
planned phases. No market findings or deployed dashboard are available yet.

## Current status

- Phase 1: Python 3.10 scaffolding and backend quality gates complete.
- Phase 2: public-page HTTP client, PakWheels adapter, real HTML fixture tests,
  source staging, and the scrape CLI implemented.
- Next: Phase 3 cleaning and normalization, then Phase 4 normalized storage and
  scheduling, Phase 5 analysis, Phase 6 exports, and Phases 7–8 dashboard.

## Setup

Python 3.10 is required. Find it before installing anything:

```powershell
py -3.10 --version
py -3.10 -m venv .venv
.venv/Scripts/python.exe --version
make setup
```

If Make is not on Windows PATH, use the existing MSYS2 installation:

```powershell
& 'C:/msys64/usr/bin/make.exe' setup
& 'C:/msys64/usr/bin/make.exe' check
```

On Linux, use `python3.10 -m venv .venv`, then `make setup`. CI sets up Python 3.10
and runs the same Makefile. All Python tools use the venv's interpreter. The lock
file pins build, runtime, and quality dependencies.

## Collect a bounded batch

In PowerShell:

```powershell
$env:TRACKER_CONTACT_EMAIL = "your-contact@example.com"
.venv/Scripts/tracker.exe scrape --source pakwheels --limit-pages 3
```

On Linux, after setting `TRACKER_CONTACT_EMAIL`, use `.venv/bin/tracker` instead.
`--contact-email` is also accepted. See `tracker scrape --help` for all options.

The scraper discovers the ten most numerous models among the site's displayed
model links and allocates a total page budget round-robin. Three pages currently
sample three different models; use at least ten to sample all ten models. The
scope discovery request is additional to the model-search page budget.

New listings receive a detail fetch. Later runs reuse successful details and take
current prices from search pages. An optional `--max-new-details 5` caps initial
detail requests while still storing all search-page summaries; those remaining
details can be collected on later runs. Featured listings may be overrepresented
in small batches, so this is not a representative market sample.

Local outputs (all ignored by Git):

- `data/tracker.sqlite3`: `raw_vehicles` and `raw_observations` staging tables.
- `raw/cache/v2/`: URL-hashed, same-day vehicle-only HTML cache.

Staging preserves raw source strings. It does not yet normalize prices or vehicle
attributes. Numeric prices come from structured offers or numeric HTML attributes;
display-only or call-for-price listings have a null numeric price. Daily staging
observations keep the latest value on reruns; final normalized snapshots and
inactivity detection are Phase 4 work.

Missing or malformed details retain the list summary and produce a nonzero exit
status with an error count. Access challenges or server failures stop collection.
Completed pages remain saved; a page interrupted before its commit is not saved.
Same-day cached results do not represent a new live observation of the website.

## Quality gates

```powershell
make check
make test
```

The check target runs Ruff lint/format checks, strict mypy on `src/`, and pytest
with an 85% backend coverage floor. Default tests block socket connections and use
captured HTML or HTTPX mock transports. See [fixture documentation](tests/fixtures/README.md)
for capture provenance, deliberate refreshes, and the opt-in live smoke test.

## Data flow and limitations

Public HTML → typed source records → SQLite staging → normalization → normalized
listings and daily snapshots → analysis → aggregate JSON → static React dashboard.
Stages after raw staging remain to be implemented.

Asking prices are not transaction prices. A disappeared listing will be treated as
a proxy for removal or sale, never proof of a sale. One-platform sampling and a
limited set of models create selection bias. The collection window is currently
too short for monthly seasonality, model coefficients, or conclusions about market
trends. At least 18 months of weekly points are required for the planned seasonal
decomposition.

The project uses public pages for personal educational analysis, respects robots
rules, limits requests to at most one every two seconds plus jitter, and stops at
access challenges. The user directed continuation after reviewing the site's terms;
this is not permission from the site. Seller contact details, exact addresses,
descriptions, and photos are unnecessary and omitted from retained markup and
records. No raw database is published. Future exports will contain aggregate data
and hashed identifiers only.

See [the implementation plan](docs/PLAN.md) and [recorded decisions](docs/DECISIONS.md)
for the phase order, data model, testing targets, and future dashboard design.
