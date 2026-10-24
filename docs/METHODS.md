# Analysis methods

Phase 5 analyzes asking-price observations, not completed transactions. Every
analysis is a pure DataFrame function returning a typed result with an `ok` or
`insufficient_data` status and a reason. `tracker analyze` orchestrates them from
a read-only, consistent database snapshot, including published success/partial
runs and excluding failed, interrupted and running runs. Partial runs can lack
attributes and are subject to the same complete-case and quality checks.

## Observation quality and scope

Prices must be finite and positive. Placeholder, floor, MAD outlier, source-price
conflict and suspected-repost flags exclude a price from estimation. Unknown
prices remain in histories so comparisons cannot silently bridge them. Duplicate
listing/timestamp observations and invalid identities or times return an explicit
unavailable result. Repost candidates are excluded from price estimation;
disappearance curves describe observed identifiers, including repost candidates.

Normalized storage keeps historical prices but only the latest listing attributes.
Analysis joins those current attributes to past prices. Mileage, city and other
attributes can change, so this is an approximation, not recovered attribute history.
The daily snapshot is the first observation that UTC day. Collection covers a
bounded, selected page window, can overrepresent featured cars, and may change
scope. Counts and results do not represent the entire Pakistan used-car market.

## Weekly prices

Use the latest usable price per listing per Monday-based UTC week. Within each
exact make/model/year cohort, require at least five distinct listings and compute
the median price. For each adjacent week, match supported cohorts and average
their price ratios weighted by previous-week listing counts. Chain these ratios
from a base of 100. Missing calendar weeks or no overlapping supported cohorts
make the chain unavailable; there is no interpolation. Apply the same method per
make. Changing cohort composition can still influence the raw index.

The quality-adjusted index fits log price on model year minus 2000, log(1 + mileage
in km), engine litres, make/model, transmission, city and week indicators. The
addition of one handles zero mileage. Deterministically sorted categorical levels
use the first level as the baseline. Require at least two weeks, ten distinct cars,
30 observations, five observations per parameter, full rank and finite uncertainty.
Listing-clustered standard errors account for repeated observations. Week effects
become `100 * exp(coefficient)`, with transformed 95% confidence intervals.
The initial week is fixed at 100 by definition. The two indexes can disagree
because cohort matching and regression adjust for composition differently.

## Drops and time to events

Compare only adjacent usable prices for the same listing. A missing or excluded
price breaks comparability. A drop is strictly lower than the preceding price.
The share counts distinct cars with a drop among cars with at least one comparable
pair; require at least five eligible cars. Size summaries are event-weighted
medians in PKR and percent. Time to first drop starts at the first observation
in the supplied window and records first detection, not the exact change time.

Kaplan-Meier curves report first-drop and disappearance survival with Greenwood
confidence intervals. First-drop risk requires an initially usable price and a
comparable pair; cars without a detected drop are censored at their last usable
price. Disappearance uses the first inactive snapshot and otherwise censors at
the last observation. Require at least five subjects per segment and positive
follow-up; an unreached median is null. Reappearance is outside a first-event
curve. This observational design excludes cars with no comparable follow-up from
drop risk and does not correct for delayed observation, informative censoring or
interval censoring. Survival describes the observed window, not time since posting.

Group curves by city, seller type and initial price relative to an independently
supplied positive `fair_price_pkr`. Within ±10% is fair; above is overpriced and
below is underpriced. Without a reference the bucket is unknown. The database
has no independent fair-value reference, so the CLI does not invent these buckets
from asking prices or fit-and-predict on the same observations. Disappearance
means absent from a successfully revisited scope, not a proven sale.

## Weekdays and seasons

Use Asia/Karachi dates. New-listing counts use posting metadata only when it is
complete; otherwise label them first observed. Current normalized storage does
not retain posting dates. Divide volume by actually observed days of each weekday,
requiring at least two observed days of every weekday. Price-change rates divide
changes by comparable adjacent price pairs. Zero-volume dates without any observed
snapshot cannot be distinguished from unobserved collection days and are not added.
Posting-metadata trends also describe only the selected observed listings.

The CLI supplies the quality-adjusted weekly index to STL, falling back to the
matched-cohort index. Without either, decomposition stays unavailable. The pure
seasonality function also accepts a caller-supplied weekly series. STL uses a
52-week period with robust fitting and activates after 79 finite contiguous weekly
points (at least 18 months). Gaps and constant series are refused. Monthly means
of weekly seasonal components are exploratory summaries in the input's units;
this short minimum history does not establish a stable annual pattern.

## Drivers, validation and Fair Price Check

Use one latest observation per listing and complete usable attributes. At least
50 listings and five observations per parameter are required. Categorical levels
need at least five cars. Optional assembly, seller type, fuel type and body type
enter only with complete coverage. Binary equipment features need at least five
positive and five negative examples; unavailable predictors are reported as omitted.
The robust primary model uses the transformations above and HC3 standard errors.
For a category or one unit of a transformed numeric predictor, report
`100 * (exp(coefficient) - 1)` and transformed 95% intervals. These are associations
holding included predictors fixed, subject to omitted-variable and selection bias.

Five shuffled, fixed-seed folds group by listing. Each fold learns its category
encoding, regression, gradient boosting model and make/model median baseline from
training cars. The baseline falls back to the training global median. Unknown
held-out categories or unidentified fits return unavailable results. Report held-out
PKR MAE, percentage MAPE and R squared for all three models. Residual-versus-fitted
points and by-make metrics also use held-out linear predictions. Grouping prevents
the same listing crossing folds; it does not infer unmarked real-world reposts.

The secondary sklearn gradient boosting model predicts log price with fixed seed
731. Tree SHAP explains the final full-data model on up to 200 observations;
mean absolute effects are in log-price units. Age and mileage dependence curves
average predicted prices over up to 200 observed cars, keeping other attributes
fixed; correlated attributes can make these combinations unrealistic.

The portable linear contract includes coefficients, transformations, sorted category
levels, numeric training ranges, explicit optional-input defaults, reference year,
residual log standard deviation and held-out typical percentage error. Prediction
rejects unknown categories and values outside the training ranges. Defaults use
observed category modes and median engine size. The point estimate is the
conditional median `exp(Xβ)`, without retransformation correction. Its range is
`exp(Xβ ± 1.96 * residual_sd)`, assuming approximately Gaussian log residuals;
this is an approximate residual range, not a calibrated coverage guarantee or
a confidence interval for the mean. Twenty reference cars test exact evaluation
parity with the exported formula. Browser parity will be tested in the frontend phase.

Implementation references: [statsmodels robust fitting](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLS.fit.html),
[grouped folds](https://scikit-learn.org/1.6/modules/generated/sklearn.model_selection.GroupKFold.html),
[Kaplan-Meier](https://lifelines.readthedocs.io/en/latest/fitters/univariate/KaplanMeierFitter.html),
and [Tree SHAP](https://shap.readthedocs.io/en/latest/generated/shap.TreeExplainer.html).

## Reproduction and limits

Run `make check` offline. Tests recover known synthetic weekly trends and price
coefficients, verify constructed drops and censoring, isolate listing groups across
folds, check deterministic output and exercise sparse/missing/constant data.
Analysis coverage must be at least 90%. CLI tests use anonymized two-day fixture
observations, validate the complete JSON bundle and verify the source is unchanged.

The local sample currently has 90 listings on one observation day. It supports
no longitudinal or seasonal findings. Model availability also depends on attribute
coverage, category support and rank. Collect more observations before interpreting
real market effects. Private analysis bundles contain internal IDs; they stay in
ignored `data/analysis/`. Public, versioned, anonymized exports belong to Phase 6.
