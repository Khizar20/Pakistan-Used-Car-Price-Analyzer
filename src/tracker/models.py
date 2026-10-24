"""Validated source records; normalization belongs to the cleaning phase."""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

LISTING_URL = re.compile(
    r"https://www\.pakwheels\.com/used-cars/[a-z0-9-]+-for-sale-in-[a-z0-9-]+-(\d+)$"
)


class RawListing(BaseModel):
    """Vehicle-only data extracted from one public listing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["pakwheels"] = "pakwheels"
    source_listing_id: str = Field(pattern=r"^\d+$")
    url: str
    make: str | None = None
    model: str | None = None
    variant: str | None = None
    model_year: int | None = Field(default=None, ge=1900, le=2100)
    price_text: str | None = None
    price_pkr: int | None = Field(default=None, ge=0)
    mileage_text: str | None = None
    engine_text: str | None = None
    transmission: str | None = None
    fuel_type: str | None = None
    body_type: str | None = None
    assembly: str | None = None
    color: str | None = None
    city: str | None = None
    registered_city: str | None = None
    seller_type: Literal["individual", "dealer"] | None = None
    is_featured: bool | None = None
    has_photos_count: int | None = Field(default=None, ge=0)
    features: list[str] | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not LISTING_URL.fullmatch(value):
            raise ValueError("Expected a public PakWheels vehicle listing URL")
        return value

    @property
    def url_hash(self) -> str:
        return hashlib.sha256(self.url.encode()).hexdigest()
