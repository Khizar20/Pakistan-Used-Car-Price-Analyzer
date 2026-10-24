"""Deterministic properties for exact integer currency normalization."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from tracker.cleaning.prices import parse_price


@settings(derandomize=True)
@given(st.integers(min_value=0, max_value=10**12))
def test_formatted_price_round_trips(price: int) -> None:
    assert parse_price(f"Rs {price:,}") == price
    assert parse_price(f"PKR {Decimal(price) / 100000:f} lakh") == price
    assert parse_price(f"{Decimal(price) / 10000000:f} crore") == price
    assert parse_price(parse_price(price)) == price


@settings(derandomize=True)
@given(st.text())
def test_arbitrary_text_never_yields_a_negative_price(text: str) -> None:
    result = parse_price(text)
    assert result is None or result >= 0
