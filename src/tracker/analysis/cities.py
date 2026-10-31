"""Current asking-price comparisons with explicit cohort and sample support."""

from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from tracker.analysis.common import prepare

MINIMUM_SAMPLE = 5


class CityPrice(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    make: str
    model: str
    city: str | None
    model_year: int | None
    transmission: str | None
    listing_count: int = Field(ge=0)
    priced_listing_count: int = Field(ge=0)
    median_price_pkr: float | None
    lower_quartile_pkr: float | None
    upper_quartile_pkr: float | None
    median_mileage_km: float | None
    observed_through: str
    status: Literal["ok", "insufficient_data"]


def city_prices(frame: pd.DataFrame) -> list[CityPrice]:
    """Count each latest active nonduplicate car once; suppress sparse medians."""
    data, reason = prepare(
        frame,
        [
            "listing_id",
            "observed_at",
            "price_pkr",
            "make",
            "model",
            "city",
            "model_year",
            "transmission",
            "is_active",
        ],
    )
    if reason:
        return []
    current = data.drop_duplicates("listing_id", keep="last")
    current = current.loc[current.is_active.eq(True)].dropna(subset=["make", "model"])
    current = current.loc[
        current.observed_at.ge(data.observed_at.max() - pd.Timedelta(days=7))
    ]
    if "duplicate_of" in current:
        current = current.loc[current.duplicate_of.isna()]
    rows: list[CityPrice] = []
    for year in (False, True):
        for transmission in (False, True):
            for city in (False, True):
                keys = ["make", "model"]
                keys += ["model_year"] if year else []
                keys += ["transmission"] if transmission else []
                keys += ["city"] if city else []
                for labels, group in current.groupby(keys, sort=True, dropna=True):
                    dimensions = dict(zip(keys, labels, strict=True))
                    valid = group.loc[group._valid_price]
                    prices = valid.price_pkr
                    enough = len(prices) >= MINIMUM_SAMPLE
                    if not enough and (year or transmission):
                        continue
                    mileage = pd.to_numeric(
                        valid.get("mileage_km", pd.Series(dtype=float)), errors="coerce"
                    ).dropna()
                    rows.append(
                        CityPrice(
                            make=str(dimensions["make"]),
                            model=str(dimensions["model"]),
                            city=str(dimensions["city"]) if city else None,
                            model_year=int(dimensions["model_year"]) if year else None,
                            transmission=str(dimensions["transmission"])
                            if transmission
                            else None,
                            listing_count=len(group),
                            priced_listing_count=len(prices),
                            median_price_pkr=float(prices.median()) if enough else None,
                            lower_quartile_pkr=float(prices.quantile(0.25))
                            if enough
                            else None,
                            upper_quartile_pkr=float(prices.quantile(0.75))
                            if enough
                            else None,
                            median_mileage_km=float(mileage.median())
                            if enough and not mileage.empty
                            else None,
                            observed_through=group.observed_at.max().date().isoformat(),
                            status="ok" if enough else "insufficient_data",
                        )
                    )
    return rows
