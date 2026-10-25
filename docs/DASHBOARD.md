# Dashboard design handoff

Phase 7 completes the design brief before the Phase 8 frontend build. The audience
is a Pakistan used-car buyer who needs a quick market overview and a defensible
asking-price comparison. Follow the motorway-sign direction in PLAN.md: restrained
green, clear typography, thin rules, generous whitespace and no decorative cards.
The canonical palette is `web/design/tokens.json`; contrast tests cover normal
text, muted text and semantic green/red against both theme backgrounds.

## Navigation and hierarchy

Desktop uses a fixed-width left rail with Market, Price drops, Seasons, Drivers,
Fair price and About the data. Mobile uses a wrapping horizontal navigation with
visible page names, 44px minimum touch targets and no hidden menu dependency.
A skip link targets the main content. Hash routes support static hosting and
direct links without server rewrites. Route changes update the title and focus.

The shared header gives the source, observation date and theme switch. An optional
full-number switch applies consistently to all money displays. Use self-hosted
Schibsted Grotesk, tabular numbers and system sans fallback. Main headings use
sentence case. Green/red meanings always have text labels and numerical signs.

## Six pages

| Page | Primary task | Supporting information |
| --- | --- | --- |
| Market | Understand the measured direction or why it is unavailable | Raw/adjusted switch, supported make filters, current model counts and medians |
| Price drops | Inspect observed changes | Eligible counts, survival segment selection, city filter, sorting and reset |
| Seasons | Distinguish observed weekday effects from unavailable annual patterns | Exposure counts, volume basis and weeks still required |
| Drivers | Compare associations and predictive errors | Coefficient intervals, mileage/age curves, SHAP and model/baseline metrics |
| Fair price | Enter a car and compare its asking price | Dependent make/model controls, year/km bounds, city/transmission levels, typical error and approximate range |
| About the data | Assess whether the findings are applicable | Counts, dates, methods, selection and asking-price caveats, repository link |

The first headline is a sentence computed from the selected supported index. It
never falls back to a fabricated trend. Model/make filtering must accurately
describe the exported population; model medians are descriptive, not an index.
Unsupported model-specific adjusted indexes cannot be implied by a control.

## State and interaction rules

All eight files are schema-validated and checked for matching bundle identity,
version and timestamp before rendering. Loading has a stable layout and status
text. Failed or mixed refreshes expose Retry. Empty charts explain what is missing
and retain a route to the methods. Current real data has one day of observations:
Market should say that a trend needs more observations, and Fair price should
explain model unavailability rather than show an invented estimate.

Charts have a text summary and a Show data table control. Tables use labelled
headers and become labelled rows on narrow screens. Form controls have explicit
labels, inline errors and bounded numeric inputs. When a valid model exists,
estimates update on valid input; a Check price action validates incomplete input.
An asking price is optional and produces a below/near/above comparison only when
provided. Optional model predictors use disclosed defaults. Unknown categories and
out-of-range numbers fail visibly. Unavailable models do not display a working
calculator or fabricated defaults.

Only the selected Fair price point may animate, under 250ms, and reduced motion
disables it. Theme follows the system until explicitly selected, persists locally
when storage is available, and remains usable if storage is blocked. All content
is local static data, with no external analytics or runtime font requests.

## Acceptance for the implementation phase

Use strict React/TypeScript, generated-contract runtime validation and the planned
component/pure-function tests. Validate all six routes in light/dark and at 360px,
keyboard navigation, focus, loading/retry, populated and insufficient states, chart
tables, dependent form inputs and Python/browser prediction parity. Add axe checks,
visual regression snapshots, a gzip JS budget of 250KB and Lighthouse performance,
accessibility and best-practices targets of 95. Test data must stay distinct from
the production exports; no demo observations may appear as real market findings.

Phase 7 is complete when this handoff and canonical tokens agree with the brief,
contrast tests pass, and the repository quality gate passes. This document does
not claim that Phase 8 browser behavior is already implemented or verified.
