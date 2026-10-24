"""In-memory listing/snapshot/run lifecycle, scope safeguards and rollback."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from tracker.cleaning.models import CleanListing
from tracker.storage.repo import Repository, RunStateError, scope_key
from tracker.storage.schema import Listing, ScrapeRun, Snapshot, make_engine

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
PAGES = ("https://example.com/model?page=1",)


def row(**values: object) -> CleanListing:
    return CleanListing.model_validate(
        {
            "source": "pakwheels",
            "source_listing_id": "123",
            "url_hash": "0" * 64,
            "make": "Toyota",
            "model": "Corolla",
            "model_year": 2020,
            "price_pkr": 3500000,
            "features": ("ABS",),
            **values,
        }
    )


@pytest.fixture
def repo():
    with Repository(make_engine()) as repository:
        yield repository


def finish(
    repo: Repository,
    day: int,
    records: list[CleanListing],
    *,
    pages: tuple[str, ...] = PAGES,
    errors: int = 0,
    hours: int = 0,
) -> int:
    stamp = NOW + timedelta(days=day, hours=hours)
    run_id = repo.start_run("pakwheels", stamp, pages)
    repo.record_progress(
        run_id,
        scope_pages=pages,
        pages_fetched=1,
        listings_seen=len(records),
        errors=errors,
    )
    repo.complete_run(run_id, records, stamp + timedelta(minutes=1))
    return run_id


def test_upsert_same_day_snapshot_idempotence_and_next_day_change(
    repo: Repository,
) -> None:
    finish(repo, 0, [row()])
    finish(repo, 0, [row(price_pkr=3400000)], hours=2)
    finish(repo, 1, [row(price_pkr=3300000)])
    with Session(repo.engine) as session:
        assert session.scalar(select(func.count()).select_from(Listing)) == 1
        snapshots = session.scalars(
            select(Snapshot).order_by(Snapshot.observed_at)
        ).all()
        assert [item.price_pkr for item in snapshots] == [3500000, 3300000]
        listing = session.scalar(select(Listing))
        assert listing.first_seen_at == NOW
        assert listing.last_seen_at == NOW + timedelta(days=1)
        assert listing.features == ["ABS"]


def test_three_missing_runs_mark_inactive_and_reappearance_reactivates(
    repo: Repository,
) -> None:
    finish(repo, 0, [row()])
    finish(repo, 1, [])
    finish(repo, 2, [])
    with Session(repo.engine) as session:
        assert session.scalar(select(Listing)).is_active
    finish(repo, 3, [])
    with Session(repo.engine) as session:
        listing = session.scalar(select(Listing))
        assert not listing.is_active and listing.consecutive_misses == 3
        assert listing.disappeared_at == NOW + timedelta(days=3)
        snapshot = session.scalar(select(Snapshot).where(Snapshot.is_active.is_(False)))
        assert snapshot.price_pkr is None
    finish(repo, 4, [row(price_pkr=3200000)])
    with Session(repo.engine) as session:
        listing = session.scalar(select(Listing))
        assert listing.is_active and listing.disappeared_at is None
        assert listing.consecutive_misses == 0
        assert session.scalar(select(func.count()).select_from(Snapshot)) == 3


def test_failed_partial_other_scope_and_same_day_do_not_count_as_absence(
    repo: Repository,
) -> None:
    finish(repo, 0, [row()])
    finish(repo, 0, [], hours=2)
    finish(repo, 1, [], errors=1)
    failed = repo.start_run("pakwheels", NOW + timedelta(days=2), PAGES)
    repo.fail_run(failed, NOW + timedelta(days=2, minutes=1), "TimeoutException")
    finish(repo, 3, [], pages=("https://example.com/other",))
    with Session(repo.engine) as session:
        assert session.scalar(select(Listing)).consecutive_misses == 0
    finish(repo, 4, [])
    finish(repo, 4, [], hours=2)
    with Session(repo.engine) as session:
        assert session.scalar(select(Listing)).consecutive_misses == 1


def test_sighting_in_another_scope_protects_listing_from_old_scope_absence(
    repo: Repository,
) -> None:
    finish(repo, 0, [row()])
    finish(repo, 1, [row()], pages=("https://example.com/other",))
    for day in (2, 3, 4):
        finish(repo, day, [])
    with Session(repo.engine) as session:
        assert session.scalar(select(Listing)).is_active


def test_atomic_publication_rolls_back_and_leaves_explicit_recoverable_run(
    repo: Repository,
) -> None:
    run_id = repo.start_run("pakwheels", NOW, PAGES)

    def fail_snapshot(connection, cursor, statement, parameters, context, executemany):
        if "INSERT INTO snapshots" in statement:
            raise RuntimeError("simulated interruption")

    event.listen(repo.engine, "before_cursor_execute", fail_snapshot)
    with pytest.raises(RuntimeError, match="interruption"):
        repo.complete_run(run_id, [row()], NOW)
    event.remove(repo.engine, "before_cursor_execute", fail_snapshot)
    with Session(repo.engine) as session:
        assert session.scalar(select(func.count()).select_from(Listing)) == 0
        assert session.scalar(select(func.count()).select_from(Snapshot)) == 0
        assert session.get(ScrapeRun, run_id).status == "running"
    with pytest.raises(RunStateError, match="unfinished"):
        repo.start_run("pakwheels", NOW)
    repo.fail_run(run_id, NOW, "explicit recovery", status="interrupted")
    assert repo.start_run("pakwheels", NOW, PAGES) > run_id


def test_unknown_price_and_quality_flags_preserved_in_snapshot(
    repo: Repository,
) -> None:
    finish(repo, 0, [row(price_pkr=None, quality_flag=("missing_price",))])
    with Session(repo.engine) as session:
        snapshot = session.scalar(select(Snapshot))
        assert snapshot.price_pkr is None and snapshot.quality_flag == ["missing_price"]


def test_progress_and_run_validation(repo: Repository) -> None:
    with pytest.raises(ValueError):
        repo.start_run("", NOW)
    run_id = repo.start_run("pakwheels", NOW)
    with pytest.raises(RunStateError):
        repo.complete_run(run_id, [], NOW)
    with pytest.raises(ValueError):
        repo.record_progress(
            run_id, scope_pages=[], pages_fetched=0, listings_seen=0, errors=0
        )
    repo.record_progress(
        run_id, scope_pages=PAGES, pages_fetched=2, listings_seen=1, errors=0
    )
    with pytest.raises(ValueError, match="backwards"):
        repo.record_progress(
            run_id, scope_pages=PAGES, pages_fetched=1, listings_seen=1, errors=0
        )
    with pytest.raises(RunStateError, match="scope"):
        repo.record_progress(
            run_id, scope_pages=["other"], pages_fetched=2, listings_seen=1, errors=0
        )
    with pytest.raises(ValueError):
        repo.complete_run(run_id, [row(), row()], NOW)
    with pytest.raises(ValueError):
        repo.complete_run(run_id, [], NOW, n_runs=0)
    with pytest.raises(RunStateError):
        repo.complete_run(run_id, [], NOW - timedelta(days=1))
    with pytest.raises(ValueError):
        repo.fail_run(run_id, NOW - timedelta(days=1), "invalid")
    repo.fail_run(run_id, NOW, "test")
    with pytest.raises(RunStateError):
        repo.fail_run(run_id, NOW, "already closed")
    with pytest.raises(ValueError, match="backdated"):
        repo.start_run("pakwheels", NOW - timedelta(days=1))
    assert scope_key("pakwheels", PAGES) != scope_key("other", PAGES)


def test_wrong_source_rolls_back(repo: Repository) -> None:
    run_id = repo.start_run("other", NOW, PAGES)
    with pytest.raises(RunStateError, match="source"):
        repo.complete_run(run_id, [row()], NOW)
