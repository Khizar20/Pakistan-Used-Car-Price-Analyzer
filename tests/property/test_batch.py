"""Whole-pipeline idempotence and numeric invariants on adversarial source values."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from pandas.testing import assert_frame_equal

from tracker.cleaning.batch import clean_batch
from tracker.models import RawListing


@settings(derandomize=True, max_examples=40, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.one_of(
                st.text(max_size=25),
                st.sampled_from(["PKR 35 lakh", "Rs 1234567", "Call for price"]),
            ),
            st.one_of(
                st.text(max_size=25), st.sampled_from(["45,000 km", "0 km", "-1 km"])
            ),
        ),
        max_size=8,
    )
)
def test_cleaning_twice_is_identical_and_never_negative(
    values: list[tuple[str, str]],
) -> None:
    rows = [
        RawListing(
            source_listing_id=str(index),
            url=f"https://www.pakwheels.com/used-cars/toyota-corolla-2020-for-sale-in-lahore-{index}",
            make="toyotta",
            model="corrola",
            model_year=2020,
            price_text=price,
            mileage_text=mileage,
            city="Lahore",
            seller_type="individual",
        )
        for index, (price, mileage) in enumerate(values)
    ]
    first = clean_batch(rows)
    assert_frame_equal(clean_batch(first), first)
    assert len(first) == len(rows)
    for column in ("price_pkr", "mileage_km", "engine_cc"):
        assert first[column].dropna().ge(0).all()
