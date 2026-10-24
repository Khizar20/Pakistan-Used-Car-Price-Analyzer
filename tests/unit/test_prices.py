"""Exact currency parsing and non-destructive quality flag examples."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tracker.cleaning.prices import MAX_INTEGER, PricePolicy, flag_prices, parse_price


@pytest.mark.parametrize(
    "value,expected",
    [
        ("PKR 35 lakh", 3500000),
        ("PKR 1.25 crore", 12500000),
        ("Rs 3,500,000", 3500000),
        ("Rs. 35 lacs", 3500000),
        ("35 lac", 3500000),
        ("35 lakhs", 3500000),
        ("1 cr", 10000000),
        ("  pkr 35.50 Lakh  ", 3550000),
        ("Rs.3,500,000/-", 3500000),
        ("1,25,00,000", 12500000),
        ("35 lakh PKR", 3500000),
        ("۳۵ lakh", 3500000),
        ("PKR\u00a035 lakh", 3500000),
        (0, 0),
        (3500000, 3500000),
        (3500000.0, 3500000),
        (Decimal("0.00001"), None),
        ("0.00001 lakh", 1),
        (Decimal("3500000"), 3500000),
        (MAX_INTEGER, MAX_INTEGER),
    ],
)
def test_price_formats(value: object, expected: int | None) -> None:
    assert parse_price(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        [],
        {},
        "",
        "-",
        "Call for price",
        "Negotiable",
        "N/A",
        "PKR -35 lakh",
        "-3500000",
        -1,
        -1.0,
        "+3500000",
        "USD 3500000",
        "35 lakh to 40 lakh",
        "35.5",
        35.5,
        float("nan"),
        float("inf"),
        Decimal("NaN"),
        Decimal("Infinity"),
        "1e6",
        "35.5.0 lakh",
        "3,50,0000",
        "1,,000",
        "1,000,00",
        MAX_INTEGER + 1,
        "999999999999 crore",
    ],
)
def test_bad_or_ambiguous_price_is_none(value: object) -> None:
    assert parse_price(value) is None


def test_junk_flags_preserve_values_and_input() -> None:
    prices = [None, 1, 123456, 1234567, 99999, 100000, 3500000]
    before = prices.copy()
    assert flag_prices(prices, [None] * len(prices)) == [
        ("missing_price",),
        ("placeholder_price", "below_price_floor"),
        ("placeholder_price",),
        ("placeholder_price",),
        ("below_price_floor",),
        (),
        (),
    ]
    assert prices == before


def test_mad_is_cohort_specific_and_excludes_junk() -> None:
    cohort = ("Toyota", "Corolla", 2020)
    other = ("Honda", "Civic", 2020)
    prices = [1000000, 1100000, 1200000, 1300000, 9000000, 1234567, 1, 9000000]
    flags = flag_prices(prices, [cohort] * 7 + [other])
    assert flags[4] == ("price_outlier_mad",)
    assert flags[5] == ("placeholder_price",)
    assert flags[6] == ("placeholder_price", "below_price_floor")
    assert flags[7] == ()


def test_mad_zero_and_small_or_missing_cohorts() -> None:
    cohort = ("Toyota", "Corolla", 2020)
    assert flag_prices([1000000] * 5, [cohort] * 5) == [()] * 5
    assert flag_prices([1000000] * 4 + [1100000], [cohort] * 5)[-1] == (
        "price_outlier_mad",
    )
    assert flag_prices([1000000] * 3 + [9000000], [cohort] * 4) == [()] * 4
    assert flag_prices([1000000] * 4 + [9000000], [None] * 5) == [()] * 5


def test_mad_threshold_is_strict_and_policy_configurable() -> None:
    cohort = ("Toyota", "Corolla", 2020)
    # Median 1200000, MAD 100000; distance 500000 is not greater than 5 MAD.
    prices = [1000000, 1100000, 1200000, 1300000, 1700000]
    assert flag_prices(prices, [cohort] * 5) == [()] * 5
    assert flag_prices(prices, [cohort] * 5, PricePolicy(mad_multiplier=4))[-1] == (
        "price_outlier_mad",
    )
    assert flag_prices([100000], [None], PricePolicy(floor_pkr=200000)) == [
        ("below_price_floor",)
    ]


@pytest.mark.parametrize(
    "kwargs", [{"floor_pkr": -1}, {"minimum_cohort_size": 2}, {"mad_multiplier": 0}]
)
def test_invalid_policy(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        PricePolicy(**kwargs)


def test_invalid_flag_inputs() -> None:
    with pytest.raises(ValueError, match="lengths"):
        flag_prices([1], [])
    for price in (-1, True, MAX_INTEGER + 1):
        with pytest.raises(ValueError, match="integers"):
            flag_prices([price], [None])
    assert flag_prices([], []) == []


@pytest.mark.parametrize(
    "value",
    [
        Decimal("1e-10000000"),
        Decimal("1e10000000"),
        "1000000000000000000.00000000001",
        "99999999999999 lakh",
    ],
)
def test_decimal_extremes_are_not_rounded_into_valid_prices(value: object) -> None:
    assert parse_price(value) is None
