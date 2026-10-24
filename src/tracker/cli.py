"""Command-line interface for the tracker pipeline."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import httpx
import typer
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from tracker.config import ScrapeSettings
from tracker.scraping.base import ScrapeFilters
from tracker.scraping.http import AccessBlockedError, PoliteClient
from tracker.scraping.markup import sanitize_html
from tracker.scraping.pakwheels import PakWheelsAdapter, ParseError
from tracker.scraping.pipeline import collect_run
from tracker.storage.operations import backup_database, inspect_database
from tracker.storage.repo import Repository, RunStateError
from tracker.storage.schema import SCHEMA_VERSION
from tracker.storage.staging import StagingStore

app = typer.Typer(
    name="tracker",
    help="Collect and analyze Pakistan used-car asking prices.",
    no_args_is_help=True,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _future_phase(command: str, phase: int) -> None:
    """Explain why a pipeline command is not available in this phase."""
    typer.echo(f"'{command}' will be implemented in Phase {phase}.", err=True)
    raise typer.Exit(code=2)


@app.command()
def scrape(
    source: Annotated[str, typer.Option(help="Listing source.")] = "pakwheels",
    limit_pages: Annotated[
        int, typer.Option(min=1, max=100, help="Total model-search pages.")
    ] = 3,
    contact_email: Annotated[
        str | None,
        typer.Option(
            envvar="TRACKER_CONTACT_EMAIL",
            help="Contact email included in the User-Agent.",
        ),
    ] = None,
    database: Annotated[
        Path, typer.Option(help="Local SQLite staging database.")
    ] = Path("data/tracker.sqlite3"),
    cache_dir: Annotated[
        Path, typer.Option(help="Same-day vehicle-only HTML cache.")
    ] = Path("raw/cache/v2"),
    max_new_details: Annotated[
        int | None,
        typer.Option(
            min=0,
            help="Optional detail-request budget; remaining summaries are still saved.",
        ),
    ] = None,
    model_path: Annotated[
        list[str] | None,
        typer.Option(help="Repeat to pin observed public model paths."),
    ] = None,
) -> None:
    """Collect public used-car listing data."""
    if source != "pakwheels":
        raise typer.BadParameter("Supported source: pakwheels", param_hint="--source")
    if not contact_email:
        raise typer.BadParameter(
            "Set TRACKER_CONTACT_EMAIL or pass --contact-email",
            param_hint="--contact-email",
        )
    try:
        settings = ScrapeSettings(
            contact_email=contact_email, database=database, cache_dir=cache_dir
        )
    except ValidationError as exc:
        raise typer.BadParameter(
            "Provide a valid contact email", param_hint="--contact-email"
        ) from exc
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    try:
        with (
            Repository.open(settings.database) as repository,
            StagingStore.open(settings.database) as store,
            PoliteClient(
                contact_email=settings.contact_email,
                cache_dir=settings.cache_dir,
                sanitize=sanitize_html,
            ) as client,
        ):
            run_id, result = collect_run(
                repository=repository,
                adapter=PakWheelsAdapter(),
                client=client,
                store=store,
                filters=ScrapeFilters(
                    limit_pages=limit_pages, model_paths=tuple(model_path or ())
                ),
                started_at=_now(),
                now=_now,
                max_new_details=max_new_details,
            )
            total = inspect_database(settings.database).listings
    except (AccessBlockedError, ParseError, RunStateError) as exc:
        typer.echo(f"Collection stopped: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except (httpx.HTTPError, SQLAlchemyError, OSError, ValueError) as exc:
        typer.echo(
            f"Collection stopped ({type(exc).__name__}); "
            "earlier committed pages are retained. "
            "Check source availability and local paths.",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"Saved {result.listings_seen} unique listings "
        f"from {result.search_pages} search pages; "
        f"requested {result.detail_pages} detail pages; "
        f"{result.detail_errors} detail errors. "
        f"Database contains {total} normalized listings. Run {run_id}."
    )
    if result.detail_errors:
        raise typer.Exit(code=1)


@app.command()
def status(
    database: Annotated[Path, typer.Option(help="Existing SQLite database.")] = Path(
        "data/tracker.sqlite3"
    ),
    as_json: Annotated[
        bool, typer.Option("--json", help="Print machine-readable status.")
    ] = False,
) -> None:
    """Show row counts, last run, errors and unfinished work without writing."""
    try:
        result = inspect_database(database)
    except (OSError, sqlite3.Error, ValueError) as exc:
        typer.echo(f"Cannot read database status ({type(exc).__name__}).", err=True)
        raise typer.Exit(code=1) from exc
    if as_json:
        typer.echo(json.dumps(asdict(result), indent=2))
        return
    typer.echo(f"Schema version: {result.schema_version}")
    typer.echo(
        f"Listings: {result.listings} ({result.active_listings} active); "
        f"snapshots: {result.snapshots}; raw listings: {result.raw_listings}"
    )
    typer.echo(f"Runs: {result.runs}; recorded errors: {result.total_errors}")
    if result.last_run:
        typer.echo(
            f"Last run: {result.last_run.id}, {result.last_run.status}, "
            f"started {result.last_run.started_at}, errors {result.last_run.errors}"
        )
        if result.last_run.error_summary:
            typer.echo(f"Last error: {result.last_run.error_summary}")
    if result.unfinished_run_id:
        typer.echo(
            f"Unfinished run: {result.unfinished_run_id}. "
            "Verify no scraper is running, then use "
            f"tracker recover-run {result.unfinished_run_id}."
        )
    if result.schema_version == 0:
        typer.echo(
            "Raw staging only. Use tracker migrate before normalized collection."
        )


@app.command()
def backup(
    database: Annotated[Path, typer.Option(help="Existing source database.")] = Path(
        "data/tracker.sqlite3"
    ),
    destination: Annotated[
        Path | None, typer.Option(help="New backup file; never overwritten.")
    ] = None,
) -> None:
    """Create a consistent SQLite backup, including committed WAL data."""
    destination = (
        destination
        or database.parent / "backups" / f"tracker-{_now():%Y%m%dT%H%M%S%fZ}.sqlite3"
    )
    try:
        saved = backup_database(database, destination)
    except (OSError, sqlite3.Error, ValueError) as exc:
        typer.echo(
            f"Backup failed ({type(exc).__name__}); "
            "existing files were not overwritten.",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    typer.echo(f"Backup created: {saved}")


@app.command()
def migrate(
    database: Annotated[
        Path, typer.Option(help="SQLite database to initialize or upgrade.")
    ] = Path("data/tracker.sqlite3"),
) -> None:
    """Apply normalized migrations while retaining raw staging data."""
    try:
        with Repository.open(database):
            pass
    except (OSError, SQLAlchemyError, ValueError) as exc:
        typer.echo(
            f"Migration failed ({type(exc).__name__}); inspect the database.", err=True
        )
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"Database schema is at version {SCHEMA_VERSION}. Raw staging is retained."
    )


@app.command()
def recover_run(
    run_id: Annotated[int, typer.Argument(min=1)],
    database: Annotated[Path, typer.Option(help="Existing SQLite database.")] = Path(
        "data/tracker.sqlite3"
    ),
) -> None:
    """Explicitly close a crashed run; first verify that its process has stopped."""
    try:
        current = inspect_database(database)
        if current.schema_version != SCHEMA_VERSION:
            raise ValueError("Recovery requires a normalized database")
        with Repository.open(database) as repository:
            repository.fail_run(
                run_id, _now(), "ExplicitInterruptedRunRecovery", status="interrupted"
            )
    except (OSError, sqlite3.Error, SQLAlchemyError, ValueError) as exc:
        typer.echo(
            f"Recovery failed ({type(exc).__name__}); inspect run status.", err=True
        )
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"Run {run_id} marked interrupted; normalized observations were not fabricated."
    )


@app.command()
def analyze() -> None:
    """Analyze stored price observations."""
    _future_phase("analyze", 5)


@app.command(name="export")
def export_data() -> None:
    """Export dashboard-ready aggregate data."""
    _future_phase("export", 6)


if __name__ == "__main__":
    app()
