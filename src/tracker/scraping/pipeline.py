"""Audited scrape-to-clean-to-normalized-storage workflow."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from tracker.cleaning.batch import clean_batch, frame_to_records
from tracker.scraping.base import ScrapeFilters, SourceAdapter
from tracker.scraping.runner import PageClient, ScrapeProgress, ScrapeResult, run_scrape
from tracker.storage.repo import Repository
from tracker.storage.staging import StagingStore


def _now() -> datetime:
    return datetime.now(timezone.utc)


def collect_run(
    *,
    repository: Repository,
    store: StagingStore,
    client: PageClient,
    adapter: SourceAdapter,
    filters: ScrapeFilters,
    started_at: datetime,
    source: str = "pakwheels",
    max_new_details: int | None = None,
    now: Callable[[], datetime] = _now,
) -> tuple[int, ScrapeResult]:
    """Track failures and publish normalized data only in a complete transaction."""
    run_id = repository.start_run(source, started_at)

    def progress(value: ScrapeProgress) -> None:
        repository.record_progress(
            run_id,
            scope_pages=value.scope_pages,
            pages_fetched=value.pages_fetched,
            listings_seen=value.listings_seen,
            errors=value.errors,
        )

    try:
        result = run_scrape(
            adapter=adapter,
            client=client,
            store=store,
            filters=filters,
            observed_at=started_at,
            max_new_details=max_new_details,
            progress=progress,
        )
        rows = frame_to_records(clean_batch(result.records))
        repository.complete_run(run_id, rows, max(now(), started_at))
    except BaseException as exc:
        repository.fail_run(
            run_id,
            max(now(), started_at),
            type(exc).__name__,
            status="interrupted"
            if isinstance(exc, KeyboardInterrupt | SystemExit)
            else "failed",
        )
        raise
    return run_id, result
