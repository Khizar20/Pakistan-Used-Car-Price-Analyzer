"""Consecutive-observation drops and censored Kaplan-Meier event statistics."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from importlib import import_module
from typing import Protocol, cast

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from tracker.analysis.common import Result, prepare


class DropEvent(BaseModel):
    listing_id: str
    observed_at: str
    old_price_pkr: float
    new_price_pkr: float
    drop_pkr: float
    drop_percent: float
    days_listed: float


class SurvivalPoint(BaseModel):
    days: float
    survival: float
    lower: float
    upper: float


class SurvivalCurve(Result):
    outcome: str
    dimension: str
    segment: str
    listings: int
    events: int
    median_days: float | None = None
    points: list[SurvivalPoint] = Field(default_factory=list)


class DropResult(Result):
    observed_listings: int = 0
    eligible_listings: int = 0
    drop_share: float | None = None
    median_drop_pkr: float | None = None
    median_drop_percent: float | None = None
    days_to_first_drop: list[float] = Field(default_factory=list)
    events: list[DropEvent] = Field(default_factory=list)
    survival: list[SurvivalCurve] = Field(default_factory=list)


class KaplanMeier(Protocol):
    survival_function_: pd.DataFrame
    confidence_interval_: pd.DataFrame
    median_survival_time_: float

    def fit(
        self, durations: Sequence[float], event_observed: Sequence[bool]
    ) -> object: ...


def _curve(
    subjects: pd.DataFrame, outcome: str, dimension: str, segment: str, minimum: int
) -> SurvivalCurve:
    durations = subjects[f"{outcome}_days"].astype(float).tolist()
    events = subjects[f"{outcome}_event"].astype(bool).tolist()
    metadata = dict(
        outcome=outcome,
        dimension=dimension,
        segment=segment,
        listings=len(subjects),
        events=sum(events),
    )
    if len(subjects) < minimum or max(durations, default=0) <= 0:
        return SurvivalCurve.model_validate(
            {**metadata, "reason": "Too few listings or no positive follow-up time"}
        )
    factory = cast(
        Callable[[], KaplanMeier], import_module("lifelines").KaplanMeierFitter
    )
    fit = factory()
    fit.fit(durations, event_observed=events)
    values = fit.survival_function_.to_numpy(dtype=float).ravel()
    times = fit.survival_function_.index.to_numpy(dtype=float)
    bounds = fit.confidence_interval_.to_numpy(dtype=float)
    median = float(fit.median_survival_time_)
    return SurvivalCurve(
        outcome=outcome,
        dimension=dimension,
        segment=segment,
        listings=len(subjects),
        events=sum(events),
        status="ok",
        median_days=median if np.isfinite(median) else None,
        points=[
            SurvivalPoint(
                days=float(day),
                survival=float(value),
                lower=float(bound[0]),
                upper=float(bound[1]),
            )
            for day, value, bound in zip(times, values, bounds, strict=True)
        ],
    )


def _days(time: pd.Timestamp, origin: pd.Timestamp) -> float:
    return float((time - origin).total_seconds() / 86400)


def _segment(value: object) -> str:
    return value if isinstance(value, str) and value else "unknown"


def price_drops(
    frame: pd.DataFrame,
    *,
    minimum_listings: int = 5,
    minimum_segment: int = 5,
    fair_tolerance: float = 0.10,
) -> DropResult:
    """Compare adjacent snapshots; unknown prices never become zero or bridge gaps."""
    if minimum_listings < 2 or minimum_segment < 2 or not 0 <= fair_tolerance < 1:
        raise ValueError("Use minimum sizes >= 2 and fair tolerance in [0, 1)")
    data, reason = prepare(
        frame, ["listing_id", "observed_at", "price_pkr", "is_active"]
    )
    if reason:
        return DropResult(reason=reason)
    events: list[DropEvent] = []
    subjects: list[dict[str, object]] = []
    eligible: set[str] = set()
    first_drop_days: list[float] = []
    for listing_id, group in data.groupby("listing_id", sort=True):
        group = group.sort_values("observed_at", kind="stable")
        origin = group.observed_at.iloc[0]
        pairs = group._valid_price & group._valid_price.shift(1, fill_value=False)
        old_prices = group.price_pkr.shift(1)
        dropped = pairs & group.price_pkr.lt(old_prices)
        if pairs.any():
            eligible.add(str(listing_id))
        listing_events = []
        for index in group.index[dropped]:
            current, old = (
                float(group.at[index, "price_pkr"]),
                float(old_prices.at[index]),
            )
            event = DropEvent(
                listing_id=str(listing_id),
                observed_at=group.at[index, "observed_at"].isoformat(),
                old_price_pkr=old,
                new_price_pkr=current,
                drop_pkr=old - current,
                drop_percent=100 * (old - current) / old,
                days_listed=(group.at[index, "observed_at"] - origin).total_seconds()
                / 86400,
            )
            listing_events.append(event)
            events.append(event)
        if listing_events:
            first_drop_days.append(listing_events[0].days_listed)
        inactive = group.loc[group.is_active.eq(False)]
        valid = group.loc[group._valid_price]
        first = group.iloc[0]
        bucket = "unknown"
        fair = pd.to_numeric(
            pd.Series([first.get("fair_price_pkr")]), errors="coerce"
        ).iloc[0]
        if first._valid_price and np.isfinite(fair) and fair > 0:
            ratio = float(first.price_pkr / fair)
            bucket = (
                "overpriced"
                if ratio > 1 + fair_tolerance
                else "underpriced"
                if ratio < 1 - fair_tolerance
                else "fair"
            )
        subjects.append(
            {
                "bucket": bucket,
                "seller_type": _segment(first.get("seller_type")),
                "city": _segment(first.get("city")),
                "drop_eligible": bool(first._valid_price and pairs.any()),
                "drop_event": bool(listing_events),
                "drop_days": listing_events[0].days_listed
                if listing_events
                else _days(valid.observed_at.iloc[-1], origin)
                if not valid.empty
                else 0,
                "disappearance_event": not inactive.empty,
                "disappearance_days": _days(
                    inactive.observed_at.iloc[0]
                    if not inactive.empty
                    else group.observed_at.iloc[-1],
                    origin,
                ),
            }
        )
    subject_frame = pd.DataFrame(subjects)
    curves: list[SurvivalCurve] = []
    for outcome in ("drop", "disappearance"):
        subset = (
            subject_frame.loc[subject_frame.drop_eligible]
            if outcome == "drop"
            else subject_frame
        )
        curves.append(_curve(subset, outcome, "all", "all", minimum_segment))
        for dimension in ("bucket", "seller_type", "city"):
            for label, segment in subset.groupby(dimension, sort=True):
                curves.append(
                    _curve(segment, outcome, dimension, str(label), minimum_segment)
                )
    sufficient = len(eligible) >= minimum_listings
    return DropResult(
        status="ok" if sufficient else "insufficient_data",
        reason=None
        if sufficient
        else "Too few listings with consecutive usable price observations",
        observed_listings=len(subjects),
        eligible_listings=len(eligible),
        drop_share=len({event.listing_id for event in events}) / len(eligible)
        if sufficient
        else None,
        median_drop_pkr=float(np.median([event.drop_pkr for event in events]))
        if events and sufficient
        else None,
        median_drop_percent=float(np.median([event.drop_percent for event in events]))
        if events and sufficient
        else None,
        days_to_first_drop=sorted(first_drop_days),
        events=events,
        survival=curves,
    )
