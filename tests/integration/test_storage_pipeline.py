"""Phase 4 acceptance: offline consecutive-day scraping, cleaning and persistence."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from tests.integration.test_scrape import NOW, Source
from tracker.scraping.base import ScrapeFilters
from tracker.scraping.pakwheels import PakWheelsAdapter, ParseError
from tracker.scraping.pipeline import collect_run
from tracker.storage.repo import Repository, RunStateError
from tracker.storage.schema import Listing, ScrapeRun, Snapshot
from tracker.storage.staging import RawVehicle, StagingStore


def collect(source: Source, path: Path, cache: Path, day: int = 0) -> int:
    stamp = NOW + timedelta(days=day)
    with (
        Repository.open(path) as repository,
        StagingStore.open(path) as store,
        source.client(cache) as client,
    ):
        run_id, _ = collect_run(
            repository=repository,
            store=store,
            client=client,
            adapter=PakWheelsAdapter(),
            filters=ScrapeFilters(limit_pages=3),
            started_at=stamp,
            now=lambda: stamp + timedelta(minutes=1),
        )
        return run_id


def test_two_consecutive_fixture_days_preserve_price_history_and_reuse_details(
    tmp_path: Path,
) -> None:
    source = Source()
    path = tmp_path / "tracker.sqlite3"
    first = collect(source, path, tmp_path / "cache1")
    detail_calls = sum("for-sale-in" in url for url in source.calls)
    source.html = source.html.replace('"price": 5900000', '"price": 5800000')
    second = collect(source, path, tmp_path / "cache2", 1)
    assert sum("for-sale-in" in url for url in source.calls) == detail_calls
    with Repository.open(path) as repository, Session(repository.engine) as session:
        assert session.scalar(select(func.count()).select_from(Listing)) == 1
        snapshots = session.scalars(
            select(Snapshot).order_by(Snapshot.observed_at)
        ).all()
        assert [row.price_pkr for row in snapshots] == [5900000, 5800000]
        assert [row.scrape_run_id for row in snapshots] == [first, second]
        listing = session.scalar(select(Listing))
        assert listing.make == "Honda" and listing.engine_cc == 1500
        assert listing.mileage_km == 33632 and listing.transmission == "automatic"
        runs = session.scalars(select(ScrapeRun).order_by(ScrapeRun.id)).all()
        assert [run.status for run in runs] == ["success", "success"]
        assert [run.pages_fetched for run in runs] == [5, 4]
        assert runs[0].scope_key == runs[1].scope_key


def test_partial_detail_error_is_audited_without_losing_summary(tmp_path: Path) -> None:
    source = Source()
    source.detail_status = 404
    path = tmp_path / "tracker.sqlite3"
    run_id = collect(source, path, tmp_path / "cache")
    with Repository.open(path) as repository, Session(repository.engine) as session:
        run = session.get(ScrapeRun, run_id)
        assert run.status == "partial" and run.errors == 1
        assert session.scalar(select(func.count()).select_from(Listing)) == 1


def test_later_page_failure_keeps_raw_progress_but_no_partial_normalized_run(
    tmp_path: Path,
) -> None:
    source = Source()
    source.bad_search = True
    path = tmp_path / "tracker.sqlite3"
    with pytest.raises(ParseError):
        collect(source, path, tmp_path / "cache")
    with Repository.open(path) as repository, Session(repository.engine) as session:
        run = session.scalar(select(ScrapeRun))
        assert run.status == "failed" and run.error_summary == "ParseError"
        assert run.pages_fetched == 3 and run.listings_seen == 1
        assert session.scalar(select(func.count()).select_from(RawVehicle)) == 1
        assert session.scalar(select(func.count()).select_from(Listing)) == 0


def test_normalized_publish_failure_rolls_back_but_records_failed_run(
    tmp_path: Path,
) -> None:
    source = Source()
    path = tmp_path / "tracker.sqlite3"
    with (
        Repository.open(path) as repository,
        StagingStore.open(path) as store,
        source.client(tmp_path / "cache") as client,
    ):

        def fail_snapshot(
            connection, cursor, statement, parameters, context, executemany
        ):
            if "INSERT INTO snapshots" in statement:
                raise RuntimeError("injected database interruption")

        event.listen(repository.engine, "before_cursor_execute", fail_snapshot)
        with pytest.raises(RuntimeError):
            collect_run(
                repository=repository,
                store=store,
                client=client,
                adapter=PakWheelsAdapter(),
                filters=ScrapeFilters(limit_pages=1),
                started_at=NOW,
                now=lambda: NOW,
            )
        with Session(repository.engine) as session:
            assert session.scalar(select(ScrapeRun)).status == "failed"
            assert session.scalar(select(func.count()).select_from(Listing)) == 0
            assert session.scalar(select(func.count()).select_from(Snapshot)) == 0


def test_keyboard_interrupt_is_recorded_and_existing_run_blocks_network(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tracker.sqlite3"
    source = Source()

    class InterruptedClient:
        def get(self, url: str) -> str:
            raise KeyboardInterrupt

    with Repository.open(path) as repository, StagingStore.open(path) as store:
        with pytest.raises(KeyboardInterrupt):
            collect_run(
                repository=repository,
                store=store,
                client=InterruptedClient(),
                adapter=PakWheelsAdapter(),
                filters=ScrapeFilters(),
                started_at=NOW,
                now=lambda: NOW,
            )
        with Session(repository.engine) as session:
            assert session.scalar(select(ScrapeRun)).status == "interrupted"
        repository.start_run("pakwheels", NOW)
        with source.client(tmp_path / "cache") as client, pytest.raises(RunStateError):
            collect_run(
                repository=repository,
                store=store,
                client=client,
                adapter=PakWheelsAdapter(),
                filters=ScrapeFilters(),
                started_at=NOW,
            )
        assert source.calls == []
