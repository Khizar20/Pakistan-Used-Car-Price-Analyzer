"""Near duplicates, near misses, stable identities and chain prevention."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tracker.cleaning.dedupe import mark_duplicates
from tracker.cleaning.models import CleanListing


def row(listing_id: str, **kwargs: object) -> CleanListing:
    return CleanListing.model_validate(
        {
            "source": "pakwheels",
            "source_listing_id": listing_id,
            "url_hash": "0" * 64,
            "make": "Toyota",
            "model": "Corolla",
            "model_year": 2020,
            "mileage_km": 45000,
            "city": "Lahore",
            "seller_type": "individual",
            "price_pkr": 3500000,
            **kwargs,
        }
    )


def test_reposts_are_marked_without_dropping_or_mutating() -> None:
    original = [row("2", price_pkr=3600000), row("1"), row("3", price_pkr=3650000)]
    result = mark_duplicates(original)
    assert [item.duplicate_of for item in result] == [
        "pakwheels:1",
        None,
        "pakwheels:1",
    ]
    assert result[0].quality_flag == ("possible_duplicate",)
    assert all(item.duplicate_of is None for item in original)
    assert mark_duplicates(result) == result
    assert {
        item.listing_key: item for item in mark_duplicates(list(reversed(original)))
    } == {item.listing_key: item for item in result}


@pytest.mark.parametrize(
    "change",
    [
        {"make": "Honda"},
        {"model": "Yaris"},
        {"model_year": 2021},
        {"mileage_km": 45001},
        {"city": "Karachi"},
        {"seller_type": "dealer"},
        {"price_pkr": 3700000},
        {"transmission": "manual"},
        {"variant": "XLi"},
        {"engine_cc": 1800},
        {"fuel_type": "diesel"},
        {"assembly": "imported"},
        {"body_type": "Hatchback"},
    ],
)
def test_near_misses_are_not_marked(change: dict[str, object]) -> None:
    baseline = dict(
        transmission="automatic",
        variant="GLi",
        engine_cc=1300,
        fuel_type="petrol",
        assembly="local",
        body_type="Sedan",
    )
    records = [row("1", **baseline), row("2", **{**baseline, **change})]
    assert all(item.duplicate_of is None for item in mark_duplicates(records))


@pytest.mark.parametrize(
    "field",
    ["make", "model", "model_year", "mileage_km", "city", "seller_type", "price_pkr"],
)
def test_missing_keys_are_not_wildcards(field: str) -> None:
    records = [row("1", **{field: None}), row("2", **{field: None})]
    assert all(item.duplicate_of is None for item in mark_duplicates(records))


@pytest.mark.parametrize(
    "price,flags", [(0, ()), (1, ()), (1234567, ()), (3500000, ("below_price_floor",))]
)
def test_unusable_price_does_not_create_duplicate_groups(
    price: int, flags: tuple[str, ...]
) -> None:
    assert all(
        item.duplicate_of is None
        for item in mark_duplicates(
            [
                row("1", price_pkr=price, quality_flag=flags),
                row("2", price_pkr=price, quality_flag=flags),
            ]
        )
    )


def test_no_transitive_price_chain() -> None:
    result = mark_duplicates(
        [
            row("1", price_pkr=2000000),
            row("2", price_pkr=2100000),
            row("3", price_pkr=2205000),
        ]
    )
    assert [item.duplicate_of for item in result] == [None, "pakwheels:1", None]
    assert mark_duplicates(result) == result


def test_tolerance_boundary_is_symmetric_and_exact() -> None:
    result = mark_duplicates([row("1", price_pkr=2100000), row("2", price_pkr=2000000)])
    assert result[1].duplicate_of == "pakwheels:1"
    assert (
        mark_duplicates(
            [row("1"), row("2", price_pkr=3500001)], relative_price_tolerance=0
        )[1].duplicate_of
        is None
    )


@pytest.mark.parametrize("tolerance", [-0.1, 1, float("nan"), float("inf")])
def test_invalid_tolerance(tolerance: float) -> None:
    with pytest.raises(ValueError, match="tolerance"):
        mark_duplicates([], relative_price_tolerance=tolerance)


def test_repeated_identity_is_rejected_and_empty_is_valid() -> None:
    with pytest.raises(ValueError, match="identity"):
        mark_duplicates([row("1"), row("1")])
    assert mark_duplicates([]) == []


@pytest.mark.parametrize(
    "change",
    [
        {"price_pkr": -1},
        {"mileage_km": -1},
        {"engine_cc": -1},
        {"transmission": "mystery"},
        {"url_hash": "bad"},
    ],
)
def test_normalized_model_guards_contract(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        row("1", **change)
    assert row("1", quality_flag=("b", "a", "a")).quality_flag == ("a", "b")
