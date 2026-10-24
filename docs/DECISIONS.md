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
`price_pkr` is filled only from the site's numeric structured offer, never guessed
from a title. Display-only and call-for-price listings retain `price_text` with a
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
