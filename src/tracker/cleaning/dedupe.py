"""Deterministic, conservative candidate marking for possible reposted vehicles."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal

from tracker.cleaning.models import CleanListing
from tracker.cleaning.prices import PLACEHOLDER_PRICES

DedupeKey = tuple[str, str, int, int, str, str]


def _key(row: CleanListing) -> DedupeKey | None:
    if (
        not row.make
        or not row.model
        or row.model_year is None
        or row.mileage_km is None
        or not row.city
        or row.seller_type is None
        or row.price_pkr is None
        or row.price_pkr <= 0
        or row.price_pkr in PLACEHOLDER_PRICES
        or "below_price_floor" in row.quality_flag
    ):
        return None
    return (
        row.make,
        row.model,
        row.model_year,
        row.mileage_km,
        row.city,
        row.seller_type,
    )


def _compatible(left: CleanListing, right: CleanListing) -> bool:
    return all(
        first is None or second is None or first == second
        for first, second in (
            (left.variant, right.variant),
            (left.transmission, right.transmission),
            (left.engine_cc, right.engine_cc),
            (left.fuel_type, right.fuel_type),
            (left.assembly, right.assembly),
            (left.body_type, right.body_type),
        )
    )


def mark_duplicates(
    records: Sequence[CleanListing],
    *,
    relative_price_tolerance: float = 0.05,
) -> list[CleanListing]:
    """Mark candidates against stable roots, avoiding transitive price chains.

    Match complete make/model/year/mileage/city/seller-type keys with at most a
    five-percent difference relative to the smaller price. Known conflicting
    technical attributes veto a match. Unknown key fields are not wildcards.
    The lexicographically smallest qualified listing identity is the candidate
    group's root; this does not claim it was the earliest original advertisement.
    """
    if (
        not math.isfinite(relative_price_tolerance)
        or not 0 <= relative_price_tolerance < 1
    ):
        raise ValueError("Price tolerance must be finite and in [0, 1)")
    if len({row.listing_key for row in records}) != len(records):
        raise ValueError("Provide one row per listing identity")
    tolerance = Decimal(str(relative_price_tolerance))
    roots: dict[DedupeKey, list[CleanListing]] = defaultdict(list)
    marked: dict[str, CleanListing] = {}
    for record in sorted(records, key=lambda row: row.listing_key):
        flags = tuple(
            flag for flag in record.quality_flag if flag != "possible_duplicate"
        )
        row = record.model_copy(update={"quality_flag": flags, "duplicate_of": None})
        key = _key(row)
        if key is not None and row.price_pkr is not None:
            for root in roots[key]:
                if root.price_pkr is None:
                    continue
                difference = abs(row.price_pkr - root.price_pkr)
                if _compatible(row, root) and difference <= tolerance * min(
                    row.price_pkr, root.price_pkr
                ):
                    row = row.model_copy(
                        update={
                            "duplicate_of": root.listing_key,
                            "quality_flag": tuple(
                                sorted((*flags, "possible_duplicate"))
                            ),
                        }
                    )
                    break
            else:
                roots[key].append(row)
        marked[row.listing_key] = row
    return [marked[row.listing_key] for row in records]
