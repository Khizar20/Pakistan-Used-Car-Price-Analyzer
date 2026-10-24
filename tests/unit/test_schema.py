"""Versioned schema, constraints, UTC storage, and nondestructive migration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib.resources import files

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from tracker.storage.schema import SCHEMA_VERSION, ScrapeRun, initialize, make_engine


def run_row(**values: object) -> ScrapeRun:
    return ScrapeRun(
        **{
            "source": "pakwheels",
            "scope_pages": [],
            "started_at": datetime(2026, 10, 24, tzinfo=timezone.utc),
            "status": "running",
            "pages_fetched": 0,
            "listings_seen": 0,
            "errors": 0,
            **values,
        }
    )


def test_migration_is_versioned_idempotent_and_retains_staging() -> None:
    engine = make_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE raw_vehicles (id TEXT)")
        connection.exec_driver_sql("INSERT INTO raw_vehicles VALUES ('preserved')")
    initialize(engine)
    initialize(engine)
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql("PRAGMA user_version").scalar() == SCHEMA_VERSION
        )
        assert (
            connection.exec_driver_sql("SELECT id FROM raw_vehicles").scalar()
            == "preserved"
        )
    inspector = inspect(engine)
    assert {"scrape_runs", "listings", "snapshots"} <= set(inspector.get_table_names())
    assert {item["name"] for item in inspector.get_indexes("snapshots")} == {
        "ix_snapshots_listing_observed"
    }
    assert {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints("snapshots")
    } == {("listing_id", "observed_date")}
    assert len(inspector.get_foreign_keys("snapshots")) == 2
    assert (
        "CREATE TABLE listings"
        in files("tracker.storage").joinpath("migrations/001_initial.sql").read_text()
    )


@pytest.mark.parametrize(
    "setup,message",
    [
        ("PRAGMA user_version = 2", "newer"),
        ("PRAGMA user_version = 1", "missing"),
        ("CREATE TABLE listings (id INTEGER)", "Unversioned"),
    ],
)
def test_unknown_or_corrupt_schema_is_not_silently_rewritten(
    setup: str, message: str
) -> None:
    engine = make_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql(setup)
    with pytest.raises(ValueError, match=message):
        initialize(engine)


def test_timestamps_roundtrip_utc_and_require_a_timezone() -> None:
    engine = make_engine()
    initialize(engine)
    local = datetime(2026, 10, 24, 5, tzinfo=timezone(timedelta(hours=5)))
    with Session(engine) as session, session.begin():
        session.add(run_row(started_at=local))
    with Session(engine) as session:
        row = session.get(ScrapeRun, 1)
        assert row.started_at == local.astimezone(timezone.utc)
        assert row.started_at.tzinfo == timezone.utc
        assert row.finished_at is None
    with Session(engine) as session, pytest.raises(StatementError), session.begin():
        session.add(run_row(started_at=local.replace(tzinfo=None)))


def test_one_active_run_and_foreign_keys_are_enforced() -> None:
    engine = make_engine()
    initialize(engine)
    with Session(engine) as session, session.begin():
        session.add(run_row())
    with Session(engine) as session, pytest.raises(IntegrityError), session.begin():
        session.add(run_row())
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO snapshots (listing_id, observed_at, observed_date, "
                "is_active, scrape_run_id, quality_flag) "
                "VALUES (999, '2026', '2026', 1, 999, '[]')"
            )
        )
