"""City medians count current comparable cars, not snapshots or sparse cohorts."""

import pandas as pd
import pytest

from tests.analysis.synthetic import market
from tracker.analysis.cities import city_prices


def test_city_medians_filter_year_transmission_and_preserve_quartiles():
    frame = market(12, 2)
    frame["make"], frame["model"], frame["model_year"] = "Honda", "Civic", 2020
    frame["transmission"] = "automatic"
    frame["city"] = [
        "Karachi" if int(key) < 6 else "Lahore" for key in frame.listing_id
    ]
    frame["price_pkr"] = [1000000 + int(key) * 100000 for key in frame.listing_id]
    original = frame.copy(deep=True)
    rows = city_prices(frame)
    selected = next(
        row
        for row in rows
        if row.city == "Karachi"
        and row.model_year == 2020
        and row.transmission == "automatic"
    )
    assert selected.listing_count == selected.priced_listing_count == 6
    assert selected.median_price_pkr == 1250000
    assert selected.lower_quartile_pkr == 1125000
    assert selected.upper_quartile_pkr == 1375000
    assert selected.status == "ok"
    pd.testing.assert_frame_equal(frame, original)


def test_sparse_flagged_duplicates_inactive_and_missing_are_not_estimates():
    frame = market(8, 2)
    frame["make"], frame["model"], frame["city"] = "Honda", "Civic", "Karachi"
    frame.loc[frame.listing_id.eq("0"), "duplicate_of"] = "other"
    frame.loc[frame.listing_id.eq("1"), "is_active"] = False
    for index in frame.index[frame.listing_id.eq("2")]:
        frame.at[index, "quality_flag"] = ["placeholder_price"]
    frame.loc[frame.listing_id.eq("3"), "price_pkr"] = None
    rows = city_prices(frame)
    selected = next(
        row
        for row in rows
        if row.city == "Karachi" and row.model_year is None and row.transmission is None
    )
    assert selected.listing_count == 6 and selected.priced_listing_count == 4
    assert selected.status == "insufficient_data" and selected.median_price_pkr is None
    assert selected.lower_quartile_pkr is selected.upper_quartile_pkr is None
    assert city_prices(pd.DataFrame()) == []
    frame["city"] = None
    assert all(row.city is None for row in city_prices(frame))


@pytest.mark.parametrize("column", ["city", "transmission", "model_year", "make"])
def test_missing_schema_returns_no_comparisons(column):
    assert city_prices(market(8, 1).drop(columns=column)) == []


def test_stale_listings_are_excluded_and_mileage_is_optional():
    frame = market(12, 1).drop(columns="mileage_km")
    frame["make"], frame["model"], frame["city"] = "Honda", "Civic", "Karachi"
    frame.loc[frame.listing_id.eq("0"), "observed_at"] -= pd.Timedelta(days=8)
    row = next(
        row
        for row in city_prices(frame)
        if row.city == "Karachi" and row.model_year is None and row.transmission is None
    )
    assert row.listing_count == 11 and row.median_mileage_km is None
