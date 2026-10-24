"""Exposure-aware weekdays and a gated exploratory weekly seasonal decomposition."""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import Protocol, cast

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from tracker.analysis.common import FloatArray, Result, prepare

MINIMUM_WEEKS = 79


class SeasonalPoint(BaseModel):
    week: str
    observed: float
    trend: float
    seasonal: float
    residual: float


class Decomposition(Result):
    weeks_available: int = 0
    weeks_required: int = MINIMUM_WEEKS
    weeks_remaining: int = MINIMUM_WEEKS
    period_weeks: int = 52
    points: list[SeasonalPoint] = Field(default_factory=list)
    month_components: dict[str, float] = Field(default_factory=dict)


class WeekdayPoint(BaseModel):
    weekday: int
    observed_days: int
    new_listings: int
    listings_per_observed_day: float
    comparable_pairs: int
    price_changes: int
    change_rate: float | None


class VolumePoint(BaseModel):
    date: str
    listings: int


class SeasonalityResult(Result):
    volume_basis: str = "first_observed"
    weekdays: list[WeekdayPoint] = Field(default_factory=list)
    volume_trend: list[VolumePoint] = Field(default_factory=list)
    seasonal: Decomposition = Field(default_factory=Decomposition)
    caveat: str = (
        "First-observed counts are not actual posting volume; "
        "collection is a selected page window."
    )


class SeasonalFit(Protocol):
    trend: FloatArray
    seasonal: FloatArray
    resid: FloatArray


class SeasonalModel(Protocol):
    def fit(self) -> SeasonalFit: ...


def decompose_weekly(series: pd.Series[float]) -> Decomposition:
    """Activate only with 79 contiguous weekly values (at least 18 months)."""
    available = len(series)
    metadata = {
        "weeks_available": available,
        "weeks_remaining": max(0, MINIMUM_WEEKS - available),
    }
    if available < MINIMUM_WEEKS:
        return Decomposition.model_validate(
            {
                **metadata,
                "reason": "At least 18 months of continuous weekly data are required",
            }
        )
    values = pd.to_numeric(series, errors="coerce")
    dates = pd.DatetimeIndex(pd.to_datetime(series.index, utc=True, errors="coerce"))
    if (
        pd.isna(dates).any()
        or dates.duplicated().any()
        or not np.isfinite(values.to_numpy(dtype=float)).all()
    ):
        return Decomposition.model_validate(
            {**metadata, "reason": "Weekly data contain missing or invalid values"}
        )
    ordered = pd.Series(values.to_numpy(dtype=float), index=dates).sort_index()
    if not (ordered.index.to_series().diff().dropna() == pd.Timedelta(weeks=1)).all():
        return Decomposition.model_validate(
            {
                **metadata,
                "reason": "Weekly points must be contiguous; gaps are not interpolated",
            }
        )
    if np.ptp(ordered.to_numpy()) < 1e-12:
        return Decomposition.model_validate(
            {
                **metadata,
                "reason": "Constant series contain no estimable seasonal pattern",
            }
        )
    factory = cast(
        Callable[..., SeasonalModel], import_module("statsmodels.tsa.seasonal").STL
    )
    fit = factory(ordered.to_numpy(), period=52, robust=True).fit()
    components = pd.Series(fit.seasonal, index=ordered.index)
    monthly = components.groupby(pd.DatetimeIndex(components.index).month).mean()
    return Decomposition(
        status="ok",
        weeks_available=available,
        weeks_remaining=0,
        points=[
            SeasonalPoint(
                week=stamp.date().isoformat(),
                observed=float(value),
                trend=float(trend),
                seasonal=float(seasonal),
                residual=float(residual),
            )
            for stamp, value, trend, seasonal, residual in zip(
                ordered.index, ordered, fit.trend, fit.seasonal, fit.resid, strict=True
            )
        ],
        month_components={str(month): float(value) for month, value in monthly.items()},
    )


def seasonality(
    frame: pd.DataFrame, *, weekly_series: pd.Series[float] | None = None
) -> SeasonalityResult:
    data, reason = prepare(frame, ["listing_id", "observed_at", "price_pkr"])
    if reason:
        return SeasonalityResult(reason=reason)
    local = data.observed_at.dt.tz_convert("Asia/Karachi")
    data["day"] = local.dt.normalize()
    observed_days = pd.DatetimeIndex(data.day.unique()).sort_values()
    first = data.drop_duplicates("listing_id", keep="first").copy()
    basis = "first_observed"
    if "posted_at" in first:
        posted = pd.to_datetime(first.posted_at, utc=True, errors="coerce")
        if posted.notna().all():
            first["day"] = posted.dt.tz_convert("Asia/Karachi").dt.normalize()
            first = first.loc[
                first.day.between(observed_days.min(), observed_days.max())
            ]
            basis = "posting_metadata"
    volumes = first.groupby("day").size()
    trend = [
        VolumePoint(date=str(stamp), listings=int(count))
        for stamp, count in zip(
            pd.DatetimeIndex(volumes.index).strftime("%Y-%m-%d"),
            volumes.to_numpy(),
            strict=True,
        )
    ]
    data["comparable"] = False
    data["changed"] = False
    for _, group in data.groupby("listing_id"):
        comparable = group._valid_price & group._valid_price.shift(1, fill_value=False)
        data.loc[group.index, "comparable"] = comparable
        data.loc[group.index, "changed"] = comparable & group.price_pkr.ne(
            group.price_pkr.shift(1)
        )
    exposure = pd.Series(observed_days.weekday).value_counts()
    points = []
    enough = len(observed_days) >= 14 and all(
        int(exposure.get(day, 0)) >= 2 for day in range(7)
    )
    if enough:
        for day in range(7):
            days = int(exposure[day])
            weekdays = np.asarray(pd.DatetimeIndex(volumes.index).weekday, dtype=int)
            count = int(np.asarray(volumes, dtype=int)[weekdays == day].sum())
            subset = data.loc[data.day.dt.weekday.eq(day)]
            pairs, changes = int(subset.comparable.sum()), int(subset.changed.sum())
            points.append(
                WeekdayPoint(
                    weekday=day,
                    observed_days=days,
                    new_listings=count,
                    listings_per_observed_day=count / days,
                    comparable_pairs=pairs,
                    price_changes=changes,
                    change_rate=changes / pairs if pairs else None,
                )
            )
    if weekly_series is None:
        valid = data.loc[data._valid_price].set_index("observed_at")
        weekly_series = (
            valid.price_pkr.resample("W-MON", label="left", closed="left")
            .median()
            .dropna()
        )
    return SeasonalityResult(
        status="ok" if enough else "insufficient_data",
        reason=None if enough else "Need at least two observed days of every weekday",
        volume_basis=basis,
        weekdays=points,
        volume_trend=trend,
        seasonal=decompose_weekly(weekly_series),
    )
