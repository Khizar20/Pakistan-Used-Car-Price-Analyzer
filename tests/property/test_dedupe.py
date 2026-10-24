"""Candidate groups are stable across input order and repeated cleaning."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tracker.cleaning.dedupe import mark_duplicates
from tracker.cleaning.models import CleanListing


@settings(derandomize=True)
@given(st.lists(st.integers(min_value=100000, max_value=10000000), max_size=20))
def test_duplicate_marking_is_stable_and_points_to_roots(prices: list[int]) -> None:
    rows = [
        CleanListing(
            source="pakwheels",
            source_listing_id=str(index),
            url_hash="0" * 64,
            make="Toyota",
            model="Corolla",
            model_year=2020,
            mileage_km=45000,
            city="Lahore",
            seller_type="individual",
            price_pkr=price,
        )
        for index, price in enumerate(prices)
    ]
    result = mark_duplicates(rows)
    mapping = {row.listing_key: row for row in result}
    assert mapping == {
        row.listing_key: row for row in mark_duplicates(list(reversed(rows)))
    }
    assert mark_duplicates(result) == result
    assert all(
        mapping[row.duplicate_of].duplicate_of is None
        for row in result
        if row.duplicate_of
    )
