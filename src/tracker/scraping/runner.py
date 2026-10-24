"""Bounded source collection with detail reuse and atomic local page writes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx

from tracker.models import RawListing
from tracker.scraping.base import ScrapeFilters, SourceAdapter
from tracker.scraping.pakwheels import SEARCH_URL, ParseError, discover_model_paths
from tracker.storage.staging import StagingStore

logger = logging.getLogger(__name__)


class PageClient(Protocol):
    def get(self, url: str) -> str: ...


@dataclass(frozen=True)
class ScrapeResult:
    search_pages: int
    detail_pages: int
    listings_seen: int
    detail_errors: int
    model_paths: tuple[str, ...]


def _merge(summary: RawListing, detail: RawListing) -> RawListing:
    if (summary.source, summary.source_listing_id) != (
        detail.source,
        detail.source_listing_id,
    ):
        raise ParseError("Detail page belongs to a different listing")
    values = detail.model_dump()
    values.update(summary.model_dump(exclude_none=True))
    # The current list page is authoritative, including a newly withdrawn price.
    values.update(price_pkr=summary.price_pkr, price_text=summary.price_text)
    return RawListing.model_validate(values)


def run_scrape(
    *,
    adapter: SourceAdapter,
    client: PageClient,
    store: StagingStore,
    filters: ScrapeFilters,
    observed_at: datetime,
    max_new_details: int | None = None,
) -> ScrapeResult:
    """Discover model scope, parse bounded pages, and reuse successful details."""
    if max_new_details is not None and max_new_details < 0:
        raise ValueError("max_new_details must be nonnegative")
    if observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    paths = filters.model_paths or discover_model_paths(client.get(SEARCH_URL))
    filters = filters.model_copy(update={"model_paths": paths})
    seen: set[tuple[str, str]] = set()
    search_pages = detail_pages = errors = 0
    for url in adapter.iter_listing_pages(filters):
        summaries = adapter.parse_list_page(client.get(url))
        search_pages += 1
        batch: list[tuple[RawListing, bool]] = []
        for summary in summaries:
            key = summary.source, summary.source_listing_id
            if key in seen:
                continue
            seen.add(key)
            saved = store.get(summary)
            record, detail_fetched = saved if saved else (summary, False)
            record = _merge(summary, record)
            if not detail_fetched and (
                max_new_details is None or detail_pages < max_new_details
            ):
                detail_pages += 1
                try:
                    detail = adapter.parse_detail_page(client.get(summary.url))
                    record = _merge(summary, detail)
                    detail_fetched = True
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code not in {404, 410}:
                        raise
                    errors += 1
                    logger.warning(
                        "Listing %s disappeared before detail fetch",
                        summary.source_listing_id,
                    )
                except ParseError:
                    errors += 1
                    logger.warning(
                        "Listing %s detail could not be parsed; will retry next run",
                        summary.source_listing_id,
                    )
            batch.append((record, detail_fetched))
        store.save_batch(batch, observed_at)
    return ScrapeResult(search_pages, detail_pages, len(seen), errors, paths)
