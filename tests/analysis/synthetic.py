"""Small deterministic generators; no scraped or personal data."""

from __future__ import annotations

import numpy as np
import pandas as pd


def market(
    listings: int = 240, weeks: int = 6, *, trend: float = -0.01, noise: float = 0.01
) -> pd.DataFrame:
    rng = np.random.default_rng(731)
    records = []
    for listing in range(listings):
        year = int(rng.integers(2008, 2024))
        mileage = int(rng.integers(5000, 150000))
        engine = int(rng.integers(800, 2400))
        automatic, karachi, honda, imported, dealer, abs_feature = rng.integers(0, 2, 6)
        base = (
            np.log(1000000)
            + 0.06 * (year - 2000)
            - 0.12 * np.log1p(mileage)
            + 0.30 * engine / 1000
            + 0.15 * automatic
            + 0.08 * karachi
            + 0.10 * honda
            + 0.07 * imported
            + 0.03 * dealer
            + 0.05 * abs_feature
        )
        for week in range(weeks):
            stamp = pd.Timestamp("2025-01-06", tz="UTC") + pd.Timedelta(weeks=week)
            records.append(
                {
                    "listing_id": str(listing),
                    "observed_at": stamp,
                    "first_seen_at": pd.Timestamp("2025-01-06", tz="UTC"),
                    "model_year": year,
                    "mileage_km": mileage,
                    "engine_cc": engine,
                    "make": "Honda" if honda else "Toyota",
                    "model": "Civic" if honda else "Corolla",
                    "transmission": "automatic" if automatic else "manual",
                    "city": "Karachi" if karachi else "Lahore",
                    "assembly": "imported" if imported else "local",
                    "seller_type": "dealer" if dealer else "individual",
                    "features": ["ABS"] if abs_feature else [],
                    "is_active": True,
                    "quality_flag": [],
                    "duplicate_of": None,
                    "price_pkr": float(
                        np.exp(base + trend * week + rng.normal(0, noise))
                    ),
                }
            )
    return pd.DataFrame(records)
