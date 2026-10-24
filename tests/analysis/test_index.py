"""Known weekly trends, cohort weighting, missing weeks and model sufficiency."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests.analysis.synthetic import market
from tracker.analysis.index import price_index


def test_indexes_recover_known_trend_and_are_deterministic() -> None:
    frame = market(240, 5, noise=0)
    before = frame.copy(deep=True)
    result = price_index(frame)
    assert result.status == "ok"
    expected = 100 * np.exp(-0.01 * np.arange(5))
    np.testing.assert_allclose(
        [point.value for point in result.raw.points], expected, rtol=1e-10
    )
    assert result.quality_adjusted.status == "ok", result.quality_adjusted.reason
    np.testing.assert_allclose(
        [point.value for point in result.quality_adjusted.points], expected, rtol=1e-8
    )
    assert all(point.listings >= 5 for point in result.cohorts)
    assert price_index(frame).model_dump() == result.model_dump()
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize(
    "mode", ["empty", "missing", "single", "sparse", "gap", "disconnected", "flagged"]
)
def test_insufficient_data_is_explicit(mode: str) -> None:
    frame = market(40, 3)
    if mode == "empty":
        frame = frame.iloc[:0]
    elif mode == "missing":
        frame = frame.drop(columns="model")
    elif mode == "single":
        frame = frame.iloc[:1]
    elif mode == "sparse":
        frame["model"] = frame.listing_id
    elif mode == "gap":
        frame = frame.loc[frame.observed_at.ne(frame.observed_at.unique()[1])]
    elif mode == "disconnected":
        frame.loc[frame.observed_at.eq(frame.observed_at.max()), "model"] = "Other"
    else:
        frame["quality_flag"] = [["price_outlier_mad"] for _ in range(len(frame))]
    result = price_index(frame, minimum_cohort=2)
    assert result.status == "insufficient_data"
    assert result.reason


def test_raw_flat_prices_are_valid_but_unidentified_adjustment_is_not() -> None:
    frame = market(40, 2)
    frame["model_year"] = 2020
    frame["price_pkr"] = 3500000
    result = price_index(frame)
    assert [point.value for point in result.raw.points] == [100, 100]
    assert result.quality_adjusted.status == "insufficient_data"
    missing = price_index(frame.drop(columns="engine_cc"))
    assert missing.raw.status == "ok"
    assert missing.quality_adjusted.status == "insufficient_data"


def test_repeated_within_week_snapshots_do_not_inflate_cohort_counts() -> None:
    frame = market(20, 2)
    frame["model_year"] = 2020
    extra = frame.copy()
    extra["observed_at"] += pd.Timedelta(days=1)
    result = price_index(pd.concat([frame, extra]))
    assert sum(point.listings for point in result.cohorts) == len(frame)
    assert price_index(frame, minimum_cohort=100).status == "insufficient_data"
    with pytest.raises(ValueError):
        price_index(frame, minimum_cohort=1)
