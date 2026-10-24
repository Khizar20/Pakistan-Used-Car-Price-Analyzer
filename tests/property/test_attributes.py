"""Deterministic nonnegative and idempotent attribute properties."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tracker.cleaning.attributes import (
    normalize_assembly,
    normalize_city,
    normalize_fuel,
    normalize_make,
    normalize_model,
    normalize_text,
    normalize_transmission,
    parse_engine,
    parse_mileage,
)


@settings(derandomize=True)
@given(st.text())
def test_attribute_parsers_are_nonnegative(text: str) -> None:
    for parser in (parse_engine, parse_mileage):
        result = parser(text)
        assert result is None or result >= 0


@settings(derandomize=True)
@given(st.text())
def test_normalization_is_idempotent(text: str) -> None:
    for normalizer in (
        normalize_make,
        normalize_city,
        normalize_fuel,
        normalize_assembly,
        normalize_transmission,
        normalize_text,
    ):
        assert normalizer(normalizer(text)) == normalizer(text)
    assert normalize_model(
        "Toyota", normalize_model("Toyota", text)
    ) == normalize_model("Toyota", text)


@settings(derandomize=True)
@given(st.integers(min_value=0, max_value=10000000))
def test_formatted_mileage_round_trips(mileage: int) -> None:
    assert parse_mileage(f"{mileage:,} km") == mileage
