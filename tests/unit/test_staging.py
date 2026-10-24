"""Local SQLite source staging, history, rollback, and restart tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from tracker.scraping.pakwheels import parse_detail_page
from tracker.storage.staging import RawObservation, RawVehicle, StagingStore

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def vehicle():
    path = Path(__file__).parents[1] / "fixtures/html/pakwheels_detail.html"
    return parse_detail_page(path.read_text(encoding="utf-8"))


def test_restart_existing_detail_and_no_full_urls(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "staging.sqlite3"
    record = vehicle()
    with StagingStore.open(path) as store:
        assert store.get(record) is None
        store.save_batch([(record, True)], NOW)
    with StagingStore.open(path) as store:
        assert store.get(record) == (record, True)
        assert store.count() == 1
        with Session(store.engine) as session:
            row = session.scalar(select(RawVehicle))
            assert "url" not in row.attributes
            assert row.url_hash == record.url_hash


def test_same_day_upsert_and_next_day_history() -> None:
    store = StagingStore(create_engine("sqlite+pysqlite:///:memory:"))
    record = vehicle()
    store.save_batch([(record, False)], NOW)
    changed = record.model_copy(update={"price_pkr": 5800000})
    store.save_batch([(changed, True)], NOW + timedelta(hours=2))
    store.save_batch([(changed, True)], NOW + timedelta(days=1))
    assert store.count() == 1
    assert store.get(changed) == (changed, True)
    with Session(store.engine) as session:
        observations = session.scalars(select(RawObservation)).all()
        assert len(observations) == 2
        assert all(row.price_pkr == 5800000 for row in observations)
        row = session.scalar(select(RawVehicle))
        assert row.first_seen_at == NOW.isoformat()
        assert row.last_seen_at == (NOW + timedelta(days=1)).isoformat()


def test_batch_failure_rolls_back() -> None:
    store = StagingStore(create_engine("sqlite+pysqlite:///:memory:"))

    def fail_observation(
        connection, cursor, statement, parameters, context, executemany
    ):
        if "INSERT INTO raw_observations" in statement:
            raise RuntimeError("simulated interruption")

    event.listen(store.engine, "before_cursor_execute", fail_observation)
    with pytest.raises(RuntimeError, match="interruption"):
        store.save_batch([(vehicle(), True)], NOW)
    assert store.count() == 0


def test_timezone_required() -> None:
    store = StagingStore(create_engine("sqlite+pysqlite:///:memory:"))
    with pytest.raises(ValueError, match="timezone"):
        store.save_batch([(vehicle(), True)], NOW.replace(tzinfo=None))


def test_local_timezone_is_normalized_to_utc_day() -> None:
    store = StagingStore(create_engine("sqlite+pysqlite:///:memory:"))
    local = datetime(2026, 10, 25, 1, tzinfo=timezone(timedelta(hours=5)))
    store.save_batch([(vehicle(), True)], local)
    with Session(store.engine) as session:
        row = session.scalar(select(RawObservation))
        assert row.observed_date == "2026-10-24"
