"""Known event shares, exact survival probabilities, censoring and missing prices."""

from __future__ import annotations

import pandas as pd
import pytest

from tracker.analysis.drops import price_drops


def population() -> pd.DataFrame:
    rows = []
    for listing in range(10):
        base = 1200000 if listing < 5 else 1000000
        for day in (0, 2, 4):
            inactive = day == 4 and listing in (0, 1)
            rows.append(
                dict(
                    listing_id=str(listing),
                    observed_at=pd.Timestamp("2025-01-01", tz="UTC")
                    + pd.Timedelta(days=day),
                    price_pkr=None
                    if inactive
                    else base * (0.9 if listing in (0, 5) and day >= 2 else 1),
                    is_active=not inactive,
                    fair_price_pkr=1000000,
                    seller_type="dealer" if listing < 5 else "individual",
                    city="Lahore" if listing < 5 else "Karachi",
                )
            )
    return pd.DataFrame(rows)


def test_known_drop_probability_sizes_and_censored_survival() -> None:
    frame = population()
    result = price_drops(frame)
    assert result.status == "ok" and result.eligible_listings == 10
    assert result.drop_share == 0.2
    assert result.median_drop_pkr == pytest.approx(110000)
    assert result.median_drop_percent == pytest.approx(10)
    assert result.days_to_first_drop == [2, 2]
    overall = next(
        curve
        for curve in result.survival
        if curve.outcome == "drop" and curve.dimension == "all"
    )
    assert next(
        point.survival for point in overall.points if point.days == 2
    ) == pytest.approx(0.8)
    assert overall.events == 2 and overall.median_days is None
    disappearance = next(
        curve
        for curve in result.survival
        if curve.outcome == "disappearance" and curve.dimension == "all"
    )
    assert disappearance.events == 2
    assert {
        curve.segment for curve in result.survival if curve.dimension == "bucket"
    } == {"overpriced", "fair"}
    assert price_drops(frame).model_dump() == result.model_dump()


def test_unknown_price_does_not_create_drop_or_bridge_a_gap() -> None:
    frame = population()
    frame.loc[
        frame.listing_id.eq("0") & frame.observed_at.dt.day.eq(3), "price_pkr"
    ] = None
    result = price_drops(frame)
    assert all(event.listing_id != "0" for event in result.events)
    assert result.drop_share == pytest.approx(1 / 9)
    frame["price_pkr"] = None
    assert price_drops(frame).status == "insufficient_data"


def test_no_drops_still_produces_censored_curves_and_unknown_buckets() -> None:
    frame = population().drop(columns=["fair_price_pkr", "seller_type", "city"])
    frame["price_pkr"] = 1000000
    result = price_drops(frame)
    assert result.drop_share == 0 and result.median_drop_pkr is None
    assert result.days_to_first_drop == []
    assert all(
        curve.segment == "unknown"
        for curve in result.survival
        if curve.dimension == "bucket"
    )


@pytest.mark.parametrize("mode", ["empty", "missing", "single"])
def test_sparse_input_has_no_misleading_statistic(mode: str) -> None:
    frame = population()
    frame = (
        frame.iloc[:0]
        if mode == "empty"
        else frame.drop(columns="is_active")
        if mode == "missing"
        else frame.iloc[:1]
    )
    result = price_drops(frame)
    assert result.status == "insufficient_data" and result.drop_share is None


def test_underpriced_bucket_small_segments_and_validation() -> None:
    frame = population()
    frame["fair_price_pkr"] = 2000000
    result = price_drops(frame, minimum_segment=6)
    assert any(curve.segment == "underpriced" for curve in result.survival)
    assert any(curve.status == "insufficient_data" for curve in result.survival)
    for kwargs in (
        {"minimum_listings": 1},
        {"minimum_segment": 1},
        {"fair_tolerance": 1},
    ):
        with pytest.raises(ValueError):
            price_drops(frame, **kwargs)
