"""Read-only observations and private typed analysis bundles (not public exports)."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pandas as pd
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from tracker.analysis.common import prepare
from tracker.analysis.drivers import DriversResult, price_drivers
from tracker.analysis.drops import DropResult, price_drops
from tracker.analysis.index import IndexResult, price_index
from tracker.analysis.seasonality import SeasonalityResult, seasonality
from tracker.storage.schema import SCHEMA_VERSION, utc

ASSUMPTIONS = (
    "Asking prices are not transaction prices; associations are not causal effects.",
    "Latest listing attributes are joined to historical prices; attribute history "
    "was not collected and is not reconstructed.",
    "Disappearance means absence from a bounded collection scope, not a proven sale.",
    "Selected pages and changing scopes can bias composition and observed volume.",
    "Fair-value survival buckets require an independent supplied fair_price_pkr; "
    "database observations have no such reference and remain unknown.",
    "Posting dates are unavailable in normalized storage; "
    "volume uses first observation.",
    "This private bundle contains internal listing identifiers; use the future "
    "public export contract before publishing.",
)


class AnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    generated_at: AwareDatetime
    observations: int
    listings: int
    observed_runs: int
    observed_scopes: int
    date_start: str | None
    date_end: str | None
    seasonal_series_basis: str
    assumptions: list[str] = Field(default_factory=lambda: list(ASSUMPTIONS))
    index: IndexResult
    drops: DropResult
    seasonality: SeasonalityResult
    drivers: DriversResult


def load_observations(database: Path) -> pd.DataFrame:
    """Read a consistent committed snapshot; never create, migrate or update a DB."""
    uri = database.resolve(strict=True).as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.execute("BEGIN")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise ValueError("Analysis requires the supported normalized schema")
        cursor = connection.execute(
            """
            SELECT s.listing_id, s.observed_at, s.price_pkr, s.is_active,
                   s.quality_flag, s.scrape_run_id, r.scope_key,
                   l.make, l.model, l.model_year, l.mileage_km, l.engine_cc,
                   l.transmission, l.city, l.assembly, l.seller_type,
                   l.fuel_type, l.body_type, l.features, l.duplicate_of
            FROM snapshots s
            JOIN listings l ON l.id = s.listing_id
            JOIN scrape_runs r ON r.id = s.scrape_run_id
            WHERE r.status IN ('success', 'partial')
            ORDER BY s.observed_at, s.listing_id
            """
        )
        frame = pd.DataFrame.from_records(
            cursor.fetchall(), columns=[column[0] for column in cursor.description]
        )
    for column in ("quality_flag", "features"):
        decoded: list[list[str] | None] = []
        for value in frame[column]:
            parsed: object = json.loads(value) if isinstance(value, str) else value
            if parsed is None and column == "features":
                decoded.append(None)
            elif isinstance(parsed, list) and all(isinstance(v, str) for v in parsed):
                decoded.append(parsed)
            else:
                raise ValueError(f"Invalid normalized {column} JSON")
        frame[column] = pd.Series(decoded, dtype=object)
    frame["is_active"] = frame.is_active.astype(bool)
    return frame


def analyze_frame(frame: pd.DataFrame, *, generated_at: datetime) -> AnalysisReport:
    """Compute all four analyses without touching files, the clock or the input."""
    stamp = utc(generated_at)
    data, reason = prepare(frame, ["listing_id", "observed_at", "price_pkr"])
    index = price_index(frame)
    series = (
        index.quality_adjusted if index.quality_adjusted.status == "ok" else index.raw
    )
    basis = (
        "quality_adjusted_index"
        if index.quality_adjusted.status == "ok"
        else "matched_cohort_index"
        if index.raw.status == "ok"
        else "unavailable"
    )
    weekly = pd.Series(
        [point.value for point in series.points],
        index=pd.to_datetime([point.week for point in series.points], utc=True),
        dtype=float,
    )
    return AnalysisReport(
        generated_at=stamp,
        observations=len(frame),
        listings=int(frame.listing_id.nunique()) if "listing_id" in frame else 0,
        observed_runs=int(frame.scrape_run_id.nunique())
        if "scrape_run_id" in frame
        else 0,
        observed_scopes=int(frame.scope_key.nunique()) if "scope_key" in frame else 0,
        date_start=None if reason else data.observed_at.min().date().isoformat(),
        date_end=None if reason else data.observed_at.max().date().isoformat(),
        seasonal_series_basis=basis,
        index=index,
        drops=price_drops(frame),
        seasonality=seasonality(frame, weekly_series=weekly),
        drivers=price_drivers(frame),
    )


def write_analysis(report: AnalysisReport, directory: Path) -> Path:
    """Write one finite JSON bundle to a new directory; refuse any existing path."""
    payload = json.dumps(report.model_dump(mode="json"), indent=2, allow_nan=False)
    directory.mkdir(parents=True, exist_ok=False)
    target = directory / "analysis.json"
    with target.open("x", encoding="utf-8", newline="\n") as output:
        output.write(payload + "\n")
    return target
