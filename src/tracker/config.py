"""Validated runtime settings for bounded public listing collection."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ScrapeSettings(BaseModel):
    """Paths and contact information; secrets are never needed by the scraper."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    contact_email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    database: Path = Path("data/tracker.sqlite3")
    cache_dir: Path = Path("raw/cache/v2")
