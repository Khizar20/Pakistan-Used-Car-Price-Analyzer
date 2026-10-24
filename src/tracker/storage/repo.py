"""Transactional normalized storage and scope-aware daily run lifecycle."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import Engine, func, select, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from tracker.cleaning.models import CleanListing
from tracker.storage.schema import (
    Listing,
    ScrapeRun,
    Snapshot,
    initialize,
    make_engine,
    utc,
)


class RunStateError(ValueError):
    """A run is unfinished, already closed, or incompatible with this operation."""


def scope_key(source: str, pages: Sequence[str]) -> str:
    payload = json.dumps({"source": source, "pages": list(pages)}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class Repository:
    """One writer publishes a cleaned run atomically; raw staging is independent."""

    def __init__(self, engine: Engine) -> None:
        initialize(engine)
        self.engine = engine

    @classmethod
    def open(cls, path: Path) -> Repository:
        return cls(make_engine(path))

    def __enter__(self) -> Repository:
        return self

    def __exit__(self, *_: object) -> None:
        self.engine.dispose()

    @staticmethod
    def _running(session: Session, run_id: int) -> ScrapeRun:
        run = session.get(ScrapeRun, run_id)
        if run is None or run.status != "running":
            raise RunStateError("Run does not exist or is already finished")
        return run

    def start_run(
        self, source: str, started_at: datetime, scope_pages: Sequence[str] = ()
    ) -> int:
        stamp = utc(started_at)
        if not source.strip():
            raise ValueError("A source is required")
        with Session(self.engine) as session, session.begin():
            session.execute(text("BEGIN IMMEDIATE"))
            if (
                session.scalar(
                    select(ScrapeRun.id).where(ScrapeRun.status == "running")
                )
                is not None
            ):
                raise RunStateError(
                    "An unfinished scrape exists; inspect status "
                    "and recover it explicitly"
                )
            latest = session.scalar(select(func.max(ScrapeRun.started_at)))
            if latest is not None and stamp < latest:
                raise ValueError("Scrape runs cannot be backdated")
            run = ScrapeRun(
                source=source,
                started_at=stamp,
                scope_pages=list(scope_pages),
                scope_key=scope_key(source, scope_pages) if scope_pages else None,
                status="running",
                pages_fetched=0,
                listings_seen=0,
                errors=0,
            )
            session.add(run)
            session.flush()
            return run.id

    def record_progress(
        self,
        run_id: int,
        *,
        scope_pages: Sequence[str],
        pages_fetched: int,
        listings_seen: int,
        errors: int,
    ) -> None:
        if min(pages_fetched, listings_seen, errors) < 0 or not scope_pages:
            raise ValueError("Progress requires a scope and nonnegative counters")
        with Session(self.engine) as session, session.begin():
            run = self._running(session, run_id)
            key = scope_key(run.source, scope_pages)
            if run.scope_key is not None and run.scope_key != key:
                raise RunStateError("Cannot change the scope of a running scrape")
            if (
                pages_fetched < run.pages_fetched
                or listings_seen < run.listings_seen
                or errors < run.errors
            ):
                raise ValueError("Progress counters cannot go backwards")
            run.scope_key, run.scope_pages = key, list(scope_pages)
            run.pages_fetched, run.listings_seen, run.errors = (
                pages_fetched,
                listings_seen,
                errors,
            )

    def upsert_listing(
        self, session: Session, record: CleanListing, run: ScrapeRun
    ) -> Listing:
        if run.scope_key is None or record.source != run.source:
            raise RunStateError(
                "A listing must belong to the registered source and scope"
            )
        listing = session.scalar(
            select(Listing).where(
                Listing.source == record.source,
                Listing.source_listing_id == record.source_listing_id,
            )
        )
        values = record.model_dump(exclude={"price_pkr"})
        values["features"] = (
            list(record.features) if record.features is not None else None
        )
        values["quality_flag"] = list(record.quality_flag)
        if listing is None:
            listing = Listing(**values, first_seen_at=run.started_at)
            session.add(listing)
        elif listing.last_seen_at > run.started_at:
            raise ValueError("Cannot replace a newer listing observation")
        for field, value in values.items():
            setattr(listing, field, value)
        listing.last_seen_at = run.started_at
        listing.last_seen_run_id = run.id
        listing.last_scope_key = run.scope_key
        listing.is_active, listing.disappeared_at = True, None
        listing.consecutive_misses, listing.last_absent_date = 0, None
        session.flush()
        return listing

    def record_snapshot(
        self, session: Session, listing: Listing, record: CleanListing, run: ScrapeRun
    ) -> bool:
        """Keep the first observation of a UTC day, including its unknown price."""
        statement = (
            insert(Snapshot)
            .values(
                listing_id=listing.id,
                observed_at=run.started_at,
                observed_date=run.started_at.date().isoformat(),
                price_pkr=record.price_pkr,
                is_active=True,
                scrape_run_id=run.id,
                quality_flag=list(record.quality_flag),
            )
            .on_conflict_do_nothing(index_elements=["listing_id", "observed_date"])
        )
        return session.connection().execute(statement).rowcount == 1

    def mark_inactive_after(
        self, session: Session, run: ScrapeRun, n_runs: int = 3
    ) -> int:
        """Count absent successful same-scope days; never count failures or reruns."""
        if n_runs < 1:
            raise ValueError("Missing-run threshold must be positive")
        if run.status != "success":
            return 0
        day = run.started_at.date().isoformat()
        candidates = session.scalars(
            select(Listing).where(
                Listing.source == run.source,
                Listing.last_scope_key == run.scope_key,
                Listing.is_active.is_(True),
                Listing.last_seen_run_id != run.id,
            )
        ).all()
        changed = 0
        for listing in candidates:
            if (
                listing.last_seen_at.date() >= run.started_at.date()
                or listing.last_absent_date == day
            ):
                continue
            listing.consecutive_misses += 1
            listing.last_absent_date = day
            if listing.consecutive_misses >= n_runs:
                listing.is_active = False
                listing.disappeared_at = run.started_at
                session.execute(
                    insert(Snapshot)
                    .values(
                        listing_id=listing.id,
                        observed_at=run.started_at,
                        observed_date=day,
                        price_pkr=None,
                        is_active=False,
                        scrape_run_id=run.id,
                        quality_flag=["not_observed_in_scope"],
                    )
                    .on_conflict_do_nothing(
                        index_elements=["listing_id", "observed_date"]
                    )
                )
                changed += 1
        return changed

    def complete_run(
        self,
        run_id: int,
        records: Sequence[CleanListing],
        finished_at: datetime,
        *,
        n_runs: int = 3,
    ) -> None:
        stamp = utc(finished_at)
        if n_runs < 1 or len({record.listing_key for record in records}) != len(
            records
        ):
            raise ValueError(
                "Use a positive threshold and one row per listing identity"
            )
        with Session(self.engine) as session, session.begin():
            run = self._running(session, run_id)
            if stamp < run.started_at or run.scope_key is None:
                raise RunStateError(
                    "Cannot finish before start or without a registered scope"
                )
            for record in records:
                listing = self.upsert_listing(session, record, run)
                self.record_snapshot(session, listing, record, run)
            run.status = "partial" if run.errors else "success"
            run.listings_seen, run.finished_at = len(records), stamp
            self.mark_inactive_after(session, run, n_runs)

    def fail_run(
        self,
        run_id: int,
        finished_at: datetime,
        error_summary: str,
        *,
        status: Literal["failed", "interrupted"] = "failed",
    ) -> None:
        stamp = utc(finished_at)
        with Session(self.engine) as session, session.begin():
            run = self._running(session, run_id)
            if stamp < run.started_at:
                raise ValueError("Cannot finish before run start")
            run.status, run.finished_at = status, stamp
            run.errors = max(1, run.errors)
            run.error_summary = error_summary
