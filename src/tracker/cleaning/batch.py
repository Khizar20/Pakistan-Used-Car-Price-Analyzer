"""Validated cleaning orchestration with an explicit nullable DataFrame schema."""

from __future__ import annotations

import math
from collections.abc import Iterable

import pandas as pd

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
from tracker.cleaning.dedupe import mark_duplicates
from tracker.cleaning.models import CleanListing
from tracker.cleaning.prices import (
    DEFAULT_POLICY,
    Cohort,
    PricePolicy,
    flag_prices,
    parse_price,
)
from tracker.models import RawListing

FRAME_DTYPES = dict.fromkeys(CleanListing.model_fields, "string")
FRAME_DTYPES.update(
    dict.fromkeys(
        ("model_year", "price_pkr", "mileage_km", "engine_cc", "has_photos_count"),
        "Int64",
    )
)
FRAME_DTYPES.update(is_featured="boolean", features="object", quality_flag="object")
PRICE_FLAGS = frozenset(
    {"missing_price", "placeholder_price", "below_price_floor", "price_outlier_mad"}
)


def _label(value: object) -> str | None:
    text = normalize_text(value)
    return text.casefold() if text else None


def clean_listing(record: RawListing | CleanListing) -> CleanListing:
    """Normalize one source record, preserving provenance through its URL hash."""
    if isinstance(record, CleanListing):
        return record
    flags: set[str] = set()
    make = normalize_make(record.make)
    model = normalize_model(make, record.model)
    mileage = parse_mileage(record.mileage_text)
    engine = parse_engine(record.engine_text)
    transmission = normalize_transmission(record.transmission)
    fuel = normalize_fuel(record.fuel_type)
    assembly = normalize_assembly(record.assembly)
    display_price = parse_price(record.price_text)
    source_price = parse_price(record.price_pkr)
    price = source_price if source_price is not None else display_price
    if record.price_pkr is not None and source_price is None:
        flags.add("invalid_source_price")
    if (
        source_price is not None
        and display_price is not None
        and source_price != display_price
    ):
        flags.add("price_conflict")
    for field, raw, normalized in (
        ("invalid_mileage", record.mileage_text, mileage),
        ("invalid_engine", record.engine_text, engine),
        ("unknown_transmission", record.transmission, transmission),
        ("unknown_fuel", record.fuel_type, fuel),
        ("unknown_assembly", record.assembly, assembly),
    ):
        if normalize_text(raw) is not None and normalized is None:
            flags.add(field)
    for field, value in (
        ("missing_make", make),
        ("missing_model", model),
        ("missing_model_year", record.model_year),
    ):
        if value is None:
            flags.add(field)
    features = None
    if record.features is not None:
        labels = {
            label.casefold(): label
            for item in record.features
            if (label := normalize_text(item)) is not None
        }
        features = tuple(labels[key] for key in sorted(labels))
    return CleanListing.model_validate(
        {
            "source": record.source,
            "source_listing_id": record.source_listing_id,
            "url_hash": record.url_hash,
            "make": make,
            "model": model,
            "variant": _label(record.variant),
            "model_year": record.model_year,
            "price_pkr": price,
            "mileage_km": mileage,
            "engine_cc": engine,
            "transmission": transmission,
            "fuel_type": fuel,
            "assembly": assembly,
            "body_type": _label(record.body_type),
            "color": _label(record.color),
            "city": normalize_city(record.city),
            "registered_city": normalize_city(record.registered_city),
            "seller_type": record.seller_type,
            "is_featured": record.is_featured,
            "has_photos_count": record.has_photos_count,
            "features": features,
            "quality_flag": tuple(sorted(flags)),
        }
    )


def frame_to_records(frame: pd.DataFrame) -> list[CleanListing]:
    """Revalidate cleaned frames; malformed or unrelated DataFrames fail visibly."""
    if list(frame.columns) != list(FRAME_DTYPES):
        raise ValueError("Expected the complete ordered clean-listing DataFrame schema")
    records: list[CleanListing] = []
    for raw in frame.to_dict(orient="records"):
        values = {
            key: None
            if value is pd.NA
            or value is pd.NaT
            or (isinstance(value, float) and math.isnan(value))
            else value
            for key, value in raw.items()
        }
        records.append(CleanListing.model_validate(values))
    return records


def clean_batch(
    records: Iterable[RawListing | CleanListing] | pd.DataFrame,
    *,
    price_policy: PricePolicy = DEFAULT_POLICY,
    relative_price_tolerance: float = 0.05,
) -> pd.DataFrame:
    """Retain every input row in an explicit schema, with recomputable flags."""
    rows = (
        frame_to_records(records)
        if isinstance(records, pd.DataFrame)
        else [clean_listing(row) for row in records]
    )
    cohorts: list[Cohort | None] = [
        (row.make, row.model, row.model_year)
        if row.make is not None and row.model is not None and row.model_year is not None
        else None
        for row in rows
    ]
    flags = flag_prices([row.price_pkr for row in rows], cohorts, price_policy)
    rows = [
        row.model_copy(
            update={
                "quality_flag": tuple(
                    sorted((set(row.quality_flag) - PRICE_FLAGS) | set(price_flags))
                )
            }
        )
        for row, price_flags in zip(rows, flags, strict=True)
    ]
    rows = mark_duplicates(rows, relative_price_tolerance=relative_price_tolerance)
    return pd.DataFrame(
        {
            name: pd.Series(
                [getattr(row, name) for row in rows],
                dtype=pd.StringDtype(storage="python") if dtype == "string" else dtype,
            )
            for name, dtype in FRAME_DTYPES.items()
        }
    )
