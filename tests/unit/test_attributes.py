"""Table-driven vehicle values, explicit aliases and conservative unknowns."""

from __future__ import annotations

from collections.abc import Callable

import pytest

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


@pytest.mark.parametrize(
    "value,expected",
    [
        ("45,000 km", 45000),
        ("45,000 KM", 45000),
        ("45,000 kilometres", 45000),
        ("1,25,000 kms", 125000),
        ("\u06f0 km", 0),
        ("100", 100),
        (100, 100),
        (100.0, 100),
        (None, None),
        (True, None),
        (-1, None),
        ("-5 km", None),
        ("12.5 km", None),
        ("45,000 miles", None),
        ("45k km", None),
        ("Call", None),
        ("", None),
        ("1,,000 km", None),
        ("PKR 100", None),
        ([], None),
    ],
)
def test_mileage(value: object, expected: int | None) -> None:
    assert parse_mileage(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1300 cc", 1300),
        ("1,300cc", 1300),
        ("1.3 L", 1300),
        ("1.5 litres", 1500),
        ("1.234 litres", 1234),
        ("1.2345 L", None),
        ("1300 c.c.", 1300),
        ("1300 cm³", 1300),
        ("۱۳۰۰ cc", 1300),
        ("0 cc", 0),
        (1300, 1300),
        (None, None),
        (False, None),
        ("-1300 cc", None),
        ("1500 hp", None),
        ("Electric", None),
        ("", None),
        ("PKR 1300", None),
        (1.3, None),
        ([], None),
    ],
)
def test_engine(value: object, expected: int | None) -> None:
    assert parse_engine(value) == expected


@pytest.mark.parametrize(
    "function,value,expected",
    [
        (normalize_make, " toyotta ", "Toyota"),
        (normalize_make, "SUZKI", "Suzuki"),
        (normalize_make, "mercedes benz", "Mercedes-Benz"),
        (normalize_make, "kia motors", "KIA"),
        (normalize_make, "bmw", "BMW"),
        (normalize_make, "new brand", "New Brand"),
        (normalize_make, None, None),
        (normalize_make, "N/A", None),
        (normalize_city, "rwp", "Rawalpindi"),
        (normalize_city, "ISB", "Islamabad"),
        (normalize_city, "  GUJRANWALA  ", "Gujranwala"),
        (normalize_city, "D.G. Khan", "Dera Ghazi Khan"),
        (normalize_city, "n/a", None),
        (normalize_city, 1, None),
        (normalize_transmission, "A/T", "automatic"),
        (normalize_transmission, "CVT", "automatic"),
        (normalize_transmission, "DCT", "automatic"),
        (normalize_transmission, "m/t", "manual"),
        (normalize_transmission, "5-speed manual", "manual"),
        (normalize_transmission, "semi", None),
        (normalize_transmission, "", None),
        (normalize_fuel, "HEV", "hybrid"),
        (normalize_fuel, "PHEV", "plug-in hybrid"),
        (normalize_fuel, "petrol + CNG", "petrol/cng"),
        (normalize_fuel, "Gasoline", "petrol"),
        (normalize_fuel, "EV", "electric"),
        (normalize_fuel, "mystery", None),
        (normalize_fuel, None, None),
        (normalize_assembly, "CKD", "local"),
        (normalize_assembly, "CBU", "imported"),
        (normalize_assembly, "Japanese", None),
        (normalize_assembly, None, None),
        (normalize_text, "  ABS\u00a0  airbags ", "ABS airbags"),
        (normalize_text, "unknown", None),
        (normalize_text, False, None),
    ],
)
def test_labels(
    function: Callable[[object], str | None], value: object, expected: str | None
) -> None:
    assert function(value) == expected
    assert function(function(value)) == expected


@pytest.mark.parametrize(
    "make,value,expected",
    [
        ("Toyota", "TOYOTA CORROLA", "Corolla"),
        ("Toyota", "Toyota Toyota Corolla", "Corolla"),
        ("Toyotta", "Corolla GLi", "Corolla"),
        ("Suzki", "wagonr", "Wagon R"),
        ("Honda", "BRV", "BR-V"),
        ("Toyota", "Yaris Sedan", "Yaris"),
        ("MG", "hs", "HS"),
        ("Haval", "h6", "H6"),
        (None, "some model", "Some Model"),
        ("Toyota", None, None),
        ("Toyota", "-", None),
        ("Honda", "unknown model", "Unknown Model"),
    ],
)
def test_model_aliases_are_scoped_by_make(
    make: object, value: object, expected: str | None
) -> None:
    assert normalize_model(make, value) == expected
    assert normalize_model(make, normalize_model(make, value)) == expected
