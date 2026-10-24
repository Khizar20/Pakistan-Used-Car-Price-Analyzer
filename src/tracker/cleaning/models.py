"""Validated normalized vehicle rows shared by cleaning and later storage."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tracker.cleaning.prices import MAX_INTEGER


class CleanListing(BaseModel):
    """A source-linked, normalized row; quality flags never remove observations."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source: str = Field(pattern=r"^[a-z0-9_-]+$")
    source_listing_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    url_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    make: str | None = None
    model: str | None = None
    variant: str | None = None
    model_year: int | None = Field(default=None, ge=1900, le=2100)
    price_pkr: int | None = Field(default=None, ge=0, le=MAX_INTEGER)
    mileage_km: int | None = Field(default=None, ge=0, le=MAX_INTEGER)
    engine_cc: int | None = Field(default=None, ge=0, le=MAX_INTEGER)
    transmission: Literal["automatic", "manual"] | None = None
    fuel_type: (
        Literal[
            "petrol",
            "diesel",
            "hybrid",
            "plug-in hybrid",
            "electric",
            "cng",
            "lpg",
            "petrol/cng",
            "petrol/lpg",
        ]
        | None
    ) = None
    assembly: Literal["local", "imported"] | None = None
    body_type: str | None = None
    color: str | None = None
    city: str | None = None
    registered_city: str | None = None
    seller_type: Literal["individual", "dealer"] | None = None
    is_featured: bool | None = None
    has_photos_count: int | None = Field(default=None, ge=0)
    features: tuple[str, ...] | None = None
    quality_flag: tuple[str, ...] = ()
    duplicate_of: str | None = None

    @field_validator("quality_flag")
    @classmethod
    def canonical_flags(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(values)))

    @property
    def listing_key(self) -> str:
        return f"{self.source}:{self.source_listing_id}"
