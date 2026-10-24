"""Batch contracts, malformed inputs, precedence and stable nullable dtypes."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from pydantic import ValidationError

from tracker.cleaning.batch import (
    FRAME_DTYPES,
    clean_batch,
    clean_listing,
    frame_to_records,
)
from tracker.cleaning.prices import MAX_INTEGER, PricePolicy
from tracker.models import RawListing
from tracker.scraping.pakwheels import parse_list_page


def source(**kwargs: object) -> RawListing:
    return RawListing.model_validate(
        {
            "source_listing_id": "910001",
            "url": "https://www.pakwheels.com/used-cars/toyota-corolla-2020-for-sale-in-lahore-910001",
            "make": " toyotta ",
            "model": "corrola",
            "model_year": 2020,
            "price_text": "PKR 35 lakh",
            "mileage_text": "45,000 km",
            "engine_text": "1.3 L",
            "transmission": "CVT",
            "fuel_type": "Petrol",
            "city": "LAHORE",
            "seller_type": "individual",
            **kwargs,
        }
    )


def test_normalized_values_and_input_not_mutated() -> None:
    raw = source(
        features=["ABS", " ABS ", "Air Bags", " "],
        variant="GLi",
        color="WHITE",
        body_type="Sedan",
    )
    before = raw.model_dump()
    row = clean_listing(raw)
    assert (row.make, row.model, row.variant) == ("Toyota", "Corolla", "gli")
    assert (row.price_pkr, row.mileage_km, row.engine_cc) == (3500000, 45000, 1300)
    assert (row.transmission, row.fuel_type, row.city) == (
        "automatic",
        "petrol",
        "Lahore",
    )
    assert row.features == ("ABS", "Air Bags")
    assert row.color == "white"
    assert row.body_type == "sedan"
    assert row.url_hash == raw.url_hash
    assert "url" not in row.model_dump()
    assert raw.model_dump() == before
    assert clean_listing(row) == row


def test_unknowns_and_invalid_numeric_values_are_flagged() -> None:
    raw = source(
        make=None,
        model=None,
        model_year=None,
        mileage_text="-1 km",
        engine_text="-1 cc",
        transmission="semi",
        fuel_type="mystery",
        assembly="Japanese",
    )
    row = frame_to_records(clean_batch([raw]))[0]
    assert row.mileage_km is None and row.engine_cc is None
    assert set(row.quality_flag) == {
        "invalid_mileage",
        "invalid_engine",
        "missing_make",
        "missing_model",
        "missing_model_year",
        "unknown_transmission",
        "unknown_fuel",
        "unknown_assembly",
    }


def test_source_price_precedence_and_visible_conflicts() -> None:
    row = clean_listing(source(price_pkr=3600000))
    assert row.price_pkr == 3600000
    assert row.quality_flag == ("price_conflict",)
    recovered = clean_listing(source(price_pkr=MAX_INTEGER + 1))
    assert recovered.price_pkr == 3500000
    assert recovered.quality_flag == ("invalid_source_price",)
    missing = frame_to_records(clean_batch([source(price_text="Call for price")]))[0]
    assert missing.price_pkr is None
    assert missing.quality_flag == ("missing_price",)


def test_full_batch_is_idempotent_with_nullable_schema() -> None:
    path = Path(__file__).parents[1] / "fixtures/html/pakwheels_list.html"
    raw = parse_list_page(path.read_text(encoding="utf-8"))
    frame = clean_batch(raw)
    assert {name: str(dtype) for name, dtype in frame.dtypes.items()} == FRAME_DTYPES
    assert_frame_equal(clean_batch(frame), frame)
    assert_frame_equal(clean_batch(frame_to_records(frame)), frame)
    assert frame["engine_cc"].dtype == "Int64"
    assert frame["is_featured"].dtype == "boolean"
    assert len(frame) == len(raw)


def test_empty_batch_has_the_same_complete_schema() -> None:
    frame = clean_batch([])
    assert frame.empty
    assert list(frame.columns) == list(FRAME_DTYPES)
    assert {name: str(dtype) for name, dtype in frame.dtypes.items()} == FRAME_DTYPES
    assert_frame_equal(clean_batch(frame), frame)


def test_frame_validation_does_not_silently_drop_or_fix_bad_columns() -> None:
    with pytest.raises(ValueError, match="schema"):
        frame_to_records(pd.DataFrame({"price": [1]}))
    frame = clean_batch([source()])
    frame.loc[0, "mileage_km"] = -1
    with pytest.raises(ValidationError):
        frame_to_records(frame)


def test_float_nan_is_recovered_as_none_in_nullable_frame() -> None:
    frame = clean_batch([source()]).astype(object)
    frame.loc[0, "engine_cc"] = float("nan")
    assert frame_to_records(frame)[0].engine_cc is None


def test_recompute_policy_instead_of_accumulating_stale_flags() -> None:
    frame = clean_batch([source()], price_policy=PricePolicy(floor_pkr=4000000))
    assert frame.loc[0, "quality_flag"] == ("below_price_floor",)
    recomputed = clean_batch(frame)
    assert recomputed.loc[0, "quality_flag"] == ()
    with pytest.raises(ValueError, match="identity"):
        clean_batch([source(), source()])
