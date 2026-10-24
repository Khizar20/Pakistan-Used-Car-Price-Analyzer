"""Typed adapter contract and crawl scope shared by listing sources."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from tracker.models import RawListing


class ScrapeFilters(BaseModel):
    """Bounded crawl settings; paths are discovered from the source, not guessed."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    limit_pages: int = Field(default=3, ge=1, le=100)
    model_paths: tuple[str, ...] = ()


@runtime_checkable
class SourceAdapter(Protocol):
    """Network-independent parser and public search-page URL contract."""

    def iter_listing_pages(self, filters: ScrapeFilters) -> Iterator[str]: ...

    def parse_list_page(self, html: str) -> list[RawListing]: ...

    def parse_detail_page(self, html: str) -> RawListing: ...
