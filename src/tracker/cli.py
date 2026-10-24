"""Command-line interface for the tracker pipeline."""

from __future__ import annotations

import logging
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
from tracker.scraping.runner import run_scrape
from tracker.storage.staging import StagingStore

app = typer.Typer(
    name="tracker",
    help="Collect and analyze Pakistan used-car asking prices.",
    no_args_is_help=True,
)


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
            PoliteClient(
                contact_email=settings.contact_email,
                cache_dir=settings.cache_dir,
                sanitize=sanitize_html,
            ) as client,
            StagingStore.open(settings.database) as store,
        ):
            result = run_scrape(
                adapter=PakWheelsAdapter(),
                client=client,
                store=store,
                filters=ScrapeFilters(limit_pages=limit_pages),
                observed_at=datetime.now(timezone.utc),
                max_new_details=max_new_details,
            )
            total = store.count()
    except (AccessBlockedError, ParseError) as exc:
        typer.echo(f"Collection stopped: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except (httpx.HTTPError, SQLAlchemyError, OSError) as exc:
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
        f"Database contains {total} listings."
    )
    if result.detail_errors:
        raise typer.Exit(code=1)


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
