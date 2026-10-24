"""Conservative vehicle aliases and nonnegative mileage/engine parsing."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from decimal import Decimal, localcontext

from tracker.cleaning.prices import NUMBER, parse_price

MISSING_LABELS = frozenset(
    {"", "-", "n/a", "na", "none", "null", "unknown", "not specified"}
)


def normalize_text(value: object) -> str | None:
    """Normalize whitespace while preserving the spelling of free labels."""
    if not isinstance(value, str):
        return None
    text = " ".join(unicodedata.normalize("NFKC", value).split())
    return None if text.casefold() in MISSING_LABELS else text


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _aliases(groups: Mapping[str, tuple[str, ...]]) -> dict[str, str]:
    return {
        _key(alias): canonical
        for canonical, aliases in groups.items()
        for alias in (canonical, *aliases)
    }


MAKES = _aliases(
    {
        "Toyota": ("Toyotta",),
        "Suzuki": ("Suzki",),
        "Honda": ("Hondaa",),
        "Daihatsu": ("Dihatsu",),
        "KIA": ("Kia Motors",),
        "Hyundai": (),
        "Changan": (),
        "MG": (),
        "Haval": (),
        "BMW": (),
        "Audi": (),
        "Mercedes-Benz": ("Mercedes", "Mercedes Benz"),
        "Nissan": (),
        "Mitsubishi": (),
        "FAW": (),
        "DFSK": (),
        "BYD": (),
        "Peugeot": (),
        "Mazda": (),
        "Lexus": (),
    }
)
MODELS = {
    "Toyota": _aliases(
        {
            "Corolla": ("Corrola", "Corolla Altis", "Corolla GLi", "Corolla XLi"),
            "Vitz": ("Vits",),
            "Yaris": ("Yaris Sedan",),
            "Land Cruiser": ("LandCruiser",),
            "Prado": (),
            "Hilux": (),
            "Fortuner": (),
            "Passo": (),
            "Prius": (),
            "Raize": (),
        }
    ),
    "Honda": _aliases(
        {"Civic": ("Civc",), "City": (), "BR-V": ("BRV",), "Vezel": (), "Fit": ()}
    ),
    "Suzuki": _aliases(
        {
            "Wagon R": ("WagonR",),
            "Cultus": (),
            "Mehran": (),
            "Alto": (),
            "Swift": (),
            "Bolan": (),
            "Xbee": (),
        }
    ),
    "KIA": _aliases({"Sportage": (), "Picanto": (), "Stonic": ()}),
    "Haval": _aliases({"H6": (), "Jolion": ()}),
    "MG": _aliases({"HS": (), "ZS": ()}),
}
TRANSMISSIONS = _aliases(
    {
        "automatic": ("auto", "A/T", "AT", "CVT", "DCT", "AGS", "Automatic CVT"),
        "manual": ("M/T", "MT", "5 speed manual", "6 speed manual"),
    }
)
FUELS = _aliases(
    {
        "petrol": ("gasoline",),
        "diesel": (),
        "hybrid": ("HEV",),
        "plug-in hybrid": ("PHEV", "plugin hybrid"),
        "electric": ("EV",),
        "cng": ("compressed natural gas",),
        "lpg": (),
        "petrol/cng": ("petrol + cng",),
        "petrol/lpg": ("petrol + lpg",),
    }
)
ASSEMBLIES = _aliases(
    {"local": ("locally assembled", "CKD"), "imported": ("import", "CBU")}
)
CITIES = _aliases(
    {
        "Karachi": ("Khi",),
        "Lahore": ("Lhr",),
        "Islamabad": ("Isb", "Islamabad Capital Territory"),
        "Rawalpindi": ("Rwp", "Pindi"),
        "Faisalabad": ("Fsd",),
        "Dera Ghazi Khan": ("D.G. Khan", "DG Khan"),
    }
)


def normalize_make(value: object) -> str | None:
    text = normalize_text(value)
    return MAKES.get(_key(text), text.title()) if text else None


def normalize_model(make: object, value: object) -> str | None:
    text = normalize_text(value)
    brand = normalize_make(make)
    if not text:
        return None
    if brand and text.casefold().startswith(brand.casefold() + " "):
        text = text[len(brand) :].strip()
    return MODELS.get(brand or "", {}).get(_key(text), text.title())


def _category(value: object, aliases: Mapping[str, str]) -> str | None:
    text = normalize_text(value)
    return aliases.get(_key(text)) if text else None


def normalize_transmission(value: object) -> str | None:
    return _category(value, TRANSMISSIONS)


def normalize_fuel(value: object) -> str | None:
    return _category(value, FUELS)


def normalize_assembly(value: object) -> str | None:
    return _category(value, ASSEMBLIES)


def normalize_city(value: object) -> str | None:
    text = normalize_text(value)
    return CITIES.get(_key(text), text.title()) if text else None


def parse_mileage(value: object) -> int | None:
    """Parse whole kilometres; do not guess or convert unsupported units."""
    if not isinstance(value, str):
        return parse_price(value)
    text = unicodedata.normalize("NFKC", value).strip()
    match = re.fullmatch(
        rf"({NUMBER})\s*(?:kms?|kilomet(?:er|re)s?)?", text, re.IGNORECASE
    )
    return parse_price(match[1]) if match else None


def parse_engine(value: object) -> int | None:
    """Parse cc or explicitly labelled litres without rounding fractional cc."""
    if not isinstance(value, str):
        return parse_price(value)
    text = unicodedata.normalize("NFKC", value).strip()
    match = re.fullmatch(
        rf"({NUMBER})\s*(cc|c\.c\.|cm3|l|lit(?:er|re)s?)?", text, re.IGNORECASE
    )
    if not match:
        return None
    unit = (match[2] or "").casefold()
    if unit.startswith("l"):
        with localcontext() as context:
            context.prec = max(28, len(match[1]) + 10)
            return parse_price(Decimal(match[1].replace(",", "")) * 1000)
    return parse_price(match[1])
