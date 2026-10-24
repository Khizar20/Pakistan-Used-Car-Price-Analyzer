"""Versioned normalized SQLite schema and UTC-aware SQLAlchemy mappings."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

from sqlalchemy import (
    JSON,
    URL,
    Boolean,
    Engine,
    ForeignKey,
    String,
    create_engine,
    event,
    inspect,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

SCHEMA_VERSION = 1


def utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("Timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


class UTCDateTime(TypeDecorator[datetime]):
    """SQLite TEXT timestamps round-trip with their UTC timezone intact."""

    impl = String
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> str | None:
        return (
            utc(value).isoformat(timespec="microseconds") if value is not None else None
        )

    def process_result_value(
        self, value: str | None, dialect: Dialect
    ) -> datetime | None:
        return datetime.fromisoformat(value) if value is not None else None


class Base(DeclarativeBase):
    """Normalized tables; raw staging has its own separate metadata."""


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str]
    scope_key: Mapped[str | None]
    scope_pages: Mapped[list[str]] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    pages_fetched: Mapped[int]
    listings_seen: Mapped[int]
    errors: Mapped[int]
    status: Mapped[str]
    error_summary: Mapped[str | None]


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str]
    source_listing_id: Mapped[str]
    url_hash: Mapped[str]
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime())
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime())
    is_active: Mapped[bool] = mapped_column(Boolean)
    disappeared_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_scope_key: Mapped[str]
    last_seen_run_id: Mapped[int] = mapped_column(ForeignKey("scrape_runs.id"))
    consecutive_misses: Mapped[int]
    last_absent_date: Mapped[str | None]
    make: Mapped[str | None]
    model: Mapped[str | None]
    variant: Mapped[str | None]
    model_year: Mapped[int | None]
    mileage_km: Mapped[int | None]
    engine_cc: Mapped[int | None]
    transmission: Mapped[str | None]
    fuel_type: Mapped[str | None]
    body_type: Mapped[str | None]
    assembly: Mapped[str | None]
    color: Mapped[str | None]
    city: Mapped[str | None]
    registered_city: Mapped[str | None]
    seller_type: Mapped[str | None]
    is_featured: Mapped[bool | None]
    has_photos_count: Mapped[int | None]
    features: Mapped[list[str] | None] = mapped_column(JSON)
    quality_flag: Mapped[list[str]] = mapped_column(JSON)
    duplicate_of: Mapped[str | None]


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime())
    observed_date: Mapped[str]
    price_pkr: Mapped[int | None]
    is_active: Mapped[bool] = mapped_column(Boolean)
    scrape_run_id: Mapped[int] = mapped_column(ForeignKey("scrape_runs.id"))
    quality_flag: Mapped[list[str]] = mapped_column(JSON)


def make_engine(path: Path | None = None) -> Engine:
    """Create a foreign-key enforcing file database or an isolated in-memory DB."""
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(path) if path else ":memory:")
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection: sqlite3.Connection, record: object) -> None:
        connection.execute("PRAGMA foreign_keys = ON")

    return engine


def initialize(engine: Engine) -> None:
    """Apply migration 001 atomically, retaining preexisting raw staging tables."""
    script = (
        files("tracker.storage")
        .joinpath("migrations/001_initial.sql")
        .read_text(encoding="utf-8")
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        version = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
        if version > SCHEMA_VERSION:
            raise ValueError("Database schema is newer than this tracker supports")
        tables = set(inspect(connection).get_table_names())
        expected = {"scrape_runs", "listings", "snapshots"}
        if version == SCHEMA_VERSION:
            if not expected <= tables:
                raise ValueError("Versioned database is missing normalized tables")
            return
        if expected & tables:
            raise ValueError("Unversioned normalized tables require manual review")
        for statement in script.split(";"):
            if statement.strip():
                connection.exec_driver_sql(statement)
        connection.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
