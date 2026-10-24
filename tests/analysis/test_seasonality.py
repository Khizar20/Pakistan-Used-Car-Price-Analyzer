"""Honest short-history states and recovery of a known annual component."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tracker.analysis.seasonality import decompose_weekly, seasonality


def daily() -> pd.DataFrame:
    rows = []
    for day in range(28):
        stamp = pd.Timestamp("2025-01-06", tz="UTC") + pd.Timedelta(days=day)
        for item in range(day % 7 + 1):
            rows.append(
                dict(
                    listing_id=f"{day}-{item}",
                    observed_at=stamp,
                    price_pkr=1000000,
                    posted_at=stamp,
                )
            )
    return pd.DataFrame(rows)


def test_weekday_counts_use_observed_exposure_and_posting_metadata() -> None:
    result = seasonality(daily())
    assert result.status == "ok" and result.volume_basis == "posting_metadata"
    assert [point.listings_per_observed_day for point in result.weekdays] == list(
        range(1, 8)
    )
    assert result.seasonal.status == "insufficient_data"
    assert result.seasonal.weeks_remaining == 75
    proxy = seasonality(daily().drop(columns="posted_at"))
    assert proxy.volume_basis == "first_observed"


def test_known_seasonal_signal_reconstructs_and_is_deterministic() -> None:
    weeks = np.arange(104)
    series = pd.Series(
        100 + 0.2 * weeks + 5 * np.sin(2 * np.pi * weeks / 52),
        index=pd.date_range("2023-01-02", periods=104, freq="7D", tz="UTC"),
    )
    result = decompose_weekly(series)
    assert result.status == "ok" and len(result.month_components) == 12
    np.testing.assert_allclose(
        [point.trend + point.seasonal + point.residual for point in result.points],
        series,
        atol=1e-8,
    )
    assert (
        np.corrcoef(
            [point.seasonal for point in result.points], np.sin(2 * np.pi * weeks / 52)
        )[0, 1]
        > 0.95
    )
    assert decompose_weekly(series).model_dump() == result.model_dump()


@pytest.mark.parametrize(
    "mode", ["short", "gap", "nan", "constant", "duplicate", "bad_date"]
)
def test_bad_weekly_series_never_fakes_a_pattern(mode: str) -> None:
    series = pd.Series(
        np.arange(90, dtype=float),
        index=pd.date_range("2023-01-02", periods=90, freq="7D"),
    )
    if mode == "short":
        series = series.iloc[:78]
    elif mode == "gap":
        series = series.drop(series.index[20])
    elif mode == "nan":
        series.iloc[20] = np.nan
    elif mode == "constant":
        series[:] = 100
    elif mode == "duplicate":
        series.index = [series.index[0]] * 90
    else:
        series.index = ["bad"] * 90
    assert decompose_weekly(series).status == "insufficient_data"


def test_empty_missing_and_sparse_weekdays_are_insufficient() -> None:
    for frame in (
        pd.DataFrame(),
        daily().iloc[:0],
        daily().iloc[:1],
        daily().drop(columns="observed_at"),
    ):
        assert seasonality(frame).status == "insufficient_data"


def test_price_change_rates_and_karachi_calendar() -> None:
    frame = daily()
    extra = frame.iloc[[0]].copy()
    extra["observed_at"] += pd.Timedelta(days=1)
    extra["price_pkr"] = 900000
    result = seasonality(pd.concat([frame, extra]))
    assert result.weekdays[1].price_changes == 1
    assert result.weekdays[1].change_rate == 1
    frame["posted_at"] = None
    assert seasonality(frame).volume_basis == "first_observed"
