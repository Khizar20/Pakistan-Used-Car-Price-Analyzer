"""Weekly matched-cohort price indexes and listing-clustered time-dummy indexes."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from tracker.analysis.common import (
    Result,
    design,
    design_spec,
    fit_linear,
    model_rows,
    prepare,
)

KEYS = ["week", "make", "model", "model_year"]
ATTRIBUTES = ["mileage_km", "engine_cc", "transmission", "city"]


class IndexPoint(BaseModel):
    week: str
    value: float
    lower: float | None = None
    upper: float | None = None


class IndexSeries(Result):
    points: list[IndexPoint] = Field(default_factory=list)


class CohortPoint(BaseModel):
    week: str
    make: str
    model: str
    model_year: int
    median_price_pkr: float
    listings: int


class IndexResult(Result):
    raw: IndexSeries = Field(default_factory=IndexSeries)
    quality_adjusted: IndexSeries = Field(default_factory=IndexSeries)
    per_make: dict[str, IndexSeries] = Field(default_factory=dict)
    cohorts: list[CohortPoint] = Field(default_factory=list)


def _chain(cohorts: pd.DataFrame) -> IndexSeries:
    weeks = sorted(cohorts.week.unique())
    if len(weeks) < 2:
        return IndexSeries(reason="At least two supported weeks are required")
    points = [IndexPoint(week=weeks[0], value=100)]
    previous = cohorts.loc[cohorts.week.eq(weeks[0])].set_index(KEYS[1:])
    for week in weeks[1:]:
        if (pd.Timestamp(week) - pd.Timestamp(points[-1].week)).days != 7:
            return IndexSeries(reason="Cannot chain across missing calendar weeks")
        current = cohorts.loc[cohorts.week.eq(week)].set_index(KEYS[1:])
        matched = previous[["median_price", "listings"]].join(
            current[["median_price"]],
            how="inner",
            lsuffix="_previous",
            rsuffix="_current",
        )
        if matched.empty:
            return IndexSeries(
                reason="No shared supported cohorts between adjacent weeks"
            )
        ratio = float(
            (
                (matched.median_price_current / matched.median_price_previous)
                * matched.listings
            ).sum()
            / matched.listings.sum()
        )
        points.append(IndexPoint(week=week, value=points[-1].value * ratio))
        previous = current
    return IndexSeries(status="ok", points=points)


def _adjusted(data: pd.DataFrame) -> IndexSeries:
    if not set(ATTRIBUTES) <= set(data.columns):
        return IndexSeries(reason="Missing attributes for quality adjustment")
    rows = model_rows(data)
    if rows.week.nunique() < 2 or rows.listing_id.nunique() < 10:
        return IndexSeries(reason="Too few complete listings or weeks for adjustment")
    spec = design_spec(rows, ["make_model", "transmission", "city", "week"])
    matrix = design(rows, spec)
    if len(rows) < max(30, 5 * matrix.shape[1]):
        return IndexSeries(
            reason="Too few observations for quality-adjustment predictors"
        )
    try:
        fit = fit_linear(
            matrix,
            np.log(rows.price_pkr.to_numpy(dtype=float)),
            rows.listing_id.tolist(),
        )
    except ValueError as exc:
        return IndexSeries(reason=str(exc))
    bounds = fit.conf_int()
    points = [
        IndexPoint(week=spec.categories["week"][0], value=100, lower=100, upper=100)
    ]
    for week in spec.categories["week"][1:]:
        index = spec.names.index(f"week={week}")
        if np.max(np.abs(bounds[index])) > 50:
            return IndexSeries(reason="Time-dummy uncertainty is unstable")
        points.append(
            IndexPoint(
                week=week,
                value=float(100 * np.exp(fit.params[index])),
                lower=float(100 * np.exp(bounds[index, 0])),
                upper=float(100 * np.exp(bounds[index, 1])),
            )
        )
    return IndexSeries(status="ok", points=points)


def price_index(frame: pd.DataFrame, *, minimum_cohort: int = 5) -> IndexResult:
    """Median per cohort/week, then previous-volume-weighted matched price links."""
    if minimum_cohort < 2:
        raise ValueError("Cohort size must be at least two")
    data, reason = prepare(frame, ["listing_id", "observed_at", "price_pkr", *KEYS[1:]])
    if reason:
        return IndexResult(reason=reason)
    data = data.loc[data._valid_price].dropna(subset=KEYS[1:]).copy()
    data["week"] = (
        data.observed_at - pd.to_timedelta(data.observed_at.dt.weekday, unit="D")
    ).dt.strftime("%Y-%m-%d")
    # Frequent observation does not give one car extra cohort weight.
    data = data.drop_duplicates(["listing_id", "week"], keep="last")
    cohorts = (
        data.groupby(KEYS, observed=True)
        .agg(median_price=("price_pkr", "median"), listings=("listing_id", "nunique"))
        .reset_index()
    )
    cohorts = cohorts.loc[cohorts.listings.ge(minimum_cohort)]
    raw = _chain(cohorts)
    supported = data.merge(cohorts[KEYS], on=KEYS, how="inner")
    adjusted = (
        _adjusted(supported) if raw.status == "ok" else IndexSeries(reason=raw.reason)
    )
    points = [
        CohortPoint.model_validate(
            {
                "week": row["week"],
                "make": row["make"],
                "model": row["model"],
                "model_year": row["model_year"],
                "median_price_pkr": row["median_price"],
                "listings": row["listings"],
            }
        )
        for row in cohorts.to_dict(orient="records")
    ]
    return IndexResult(
        status=raw.status,
        reason=raw.reason,
        raw=raw,
        quality_adjusted=adjusted,
        per_make={
            str(make): _chain(group)
            for make, group in cohorts.groupby("make", observed=True)
        },
        cohorts=points,
    )
