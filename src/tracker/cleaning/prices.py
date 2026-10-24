"""Exact PKR parsing and non-destructive, cohort-aware price quality rules."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from statistics import median
from typing import Literal

MAX_INTEGER = 2**63 - 1
PLACEHOLDER_PRICES = frozenset({1, 123456, 1234567})
PriceFlag = Literal[
    "missing_price", "placeholder_price", "below_price_floor", "price_outlier_mad"
]
Cohort = tuple[str, str, int]
NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3}|\d+)(?:\.\d+)?"
PRICE_PATTERN = re.compile(
    rf"^(?:(?:pkr|rs\.?|rupees?)\s*)?({NUMBER})\s*"
    r"(lakh?s?|lacs?|crores?|cr)?\s*(?:pkr|rs\.?|rupees?)?\s*(?:/-)?$",
    re.IGNORECASE,
)


def parse_price(value: object) -> int | None:
    """Return whole PKR, rejecting signs, ambiguous text, and fractional rupees."""
    if isinstance(value, bool) or value is None:
        return None
    multiplier = 1
    if isinstance(value, str):
        text = unicodedata.normalize("NFKC", value).strip()
        match = PRICE_PATTERN.fullmatch(text)
        if match is None:
            return None
        amount = match[1].replace(",", "")
        unit = (match[2] or "").lower()
        if unit.startswith("la"):
            multiplier = 100_000
        elif unit.startswith("cr"):
            multiplier = 10_000_000
    elif isinstance(value, int | float | Decimal):
        amount = str(value)
    else:
        return None
    try:
        number = Decimal(amount)
        if not number.is_finite() or not 0 <= number <= MAX_INTEGER:
            return None
        if number == 0:
            return 0
        if number.adjusted() < -7:
            return None
        with localcontext() as context:
            context.prec = max(28, len(amount) + 10)
            result = number * multiplier
            if result > MAX_INTEGER:
                return None
            return int(result) if result == result.to_integral_value() else None
    except InvalidOperation:
        return None


@dataclass(frozen=True)
class PricePolicy:
    """Explicit analysis choices, not claims about a universal fair car price."""

    floor_pkr: int = 100_000
    minimum_cohort_size: int = 5
    mad_multiplier: int = 5

    def __post_init__(self) -> None:
        if (
            self.floor_pkr < 0
            or self.minimum_cohort_size < 3
            or self.mad_multiplier < 1
        ):
            raise ValueError(
                "Require floor >= 0, cohort size >= 3, and multiplier >= 1"
            )


DEFAULT_POLICY = PricePolicy()


def flag_prices(
    prices: Sequence[int | None],
    cohorts: Sequence[Cohort | None],
    policy: PricePolicy = DEFAULT_POLICY,
) -> list[tuple[PriceFlag, ...]]:
    """Flag obvious junk and distances strictly greater than five raw cohort MADs.

    Missing/placeholder/below-floor values do not define cohort statistics. Small
    or incomplete cohorts skip this statistical check. With zero MAD, any price
    different from the median is flagged, while a constant group is unflagged.
    """
    if len(prices) != len(cohorts):
        raise ValueError("Prices and cohorts must have equal lengths")
    flags: list[list[PriceFlag]] = []
    groups: dict[Cohort, list[int]] = defaultdict(list)
    for index, (price, cohort) in enumerate(zip(prices, cohorts, strict=False)):
        current: list[PriceFlag] = []
        if price is None:
            current.append("missing_price")
        elif isinstance(price, bool) or not 0 <= price <= MAX_INTEGER:
            raise ValueError("Prices must be nonnegative SQLite-compatible integers")
        else:
            if price in PLACEHOLDER_PRICES:
                current.append("placeholder_price")
            if price < policy.floor_pkr:
                current.append("below_price_floor")
            if not current and cohort is not None:
                groups[cohort].append(index)
        flags.append(current)
    for indices in groups.values():
        if len(indices) < policy.minimum_cohort_size:
            continue
        values = [
            Decimal(price) for index in indices if (price := prices[index]) is not None
        ]
        center = median(values)
        mad = median([abs(value - center) for value in values])
        for index, value in zip(indices, values, strict=False):
            if abs(value - center) > policy.mad_multiplier * mad:
                flags[index].append("price_outlier_mad")
    return [tuple(row) for row in flags]
