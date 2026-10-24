"""Local raw-record staging until Phase 4 introduces the normalized repository."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, URL, Boolean, Engine, String, create_engine, func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from tracker.models import RawListing


class StagingBase(DeclarativeBase):
    """Separate schema namespace for source records awaiting cleaning."""


class RawVehicle(StagingBase):
    __tablename__ = "raw_vehicles"

    source: Mapped[str] = mapped_column(String, primary_key=True)
    source_listing_id: Mapped[str] = mapped_column(String, primary_key=True)
    url_hash: Mapped[str] = mapped_column(String, nullable=False)
    attributes: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    detail_fetched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    first_seen_at: Mapped[str] = mapped_column(String, nullable=False)
    last_seen_at: Mapped[str] = mapped_column(String, nullable=False)


class RawObservation(StagingBase):
    __tablename__ = "raw_observations"

    source: Mapped[str] = mapped_column(String, primary_key=True)
    source_listing_id: Mapped[str] = mapped_column(String, primary_key=True)
    observed_date: Mapped[str] = mapped_column(String, primary_key=True)
    observed_at: Mapped[str] = mapped_column(String, nullable=False)
    price_pkr: Mapped[int | None]
    price_text: Mapped[str | None]


class StagingStore:
    """Persist one current source record and one latest observation per UTC day."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        StagingBase.metadata.create_all(engine)

    @classmethod
    def open(cls, path: Path) -> StagingStore:
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(create_engine(URL.create("sqlite+pysqlite", database=str(path))))

    def __enter__(self) -> StagingStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.engine.dispose()

    def get(self, listing: RawListing) -> tuple[RawListing, bool] | None:
        """Recover existing attributes using the current page's validated URL."""
        with Session(self.engine) as session:
            vehicle = session.get(
                RawVehicle, (listing.source, listing.source_listing_id)
            )
            if vehicle is None:
                return None
            return RawListing.model_validate(
                {**vehicle.attributes, "url": listing.url}
            ), vehicle.detail_fetched

    def save_batch(
        self,
        records: list[tuple[RawListing, bool]],
        observed_at: datetime,
    ) -> None:
        """Commit a parsed page atomically; retain history across scrape days."""
        if observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        observed_at = observed_at.astimezone(timezone.utc)
        stamp = observed_at.isoformat()
        with self.engine.begin() as connection:
            for record, detail_fetched in records:
                values: dict[str, object] = {
                    "source": record.source,
                    "source_listing_id": record.source_listing_id,
                    "url_hash": record.url_hash,
                    "attributes": record.model_dump(mode="json", exclude={"url"}),
                    "detail_fetched": detail_fetched,
                    "first_seen_at": stamp,
                    "last_seen_at": stamp,
                }
                statement = insert(RawVehicle).values(**values)
                connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=["source", "source_listing_id"],
                        set_={
                            key: value
                            for key, value in values.items()
                            if key
                            not in {"source", "source_listing_id", "first_seen_at"}
                        },
                    )
                )
                observation: dict[str, object] = {
                    "source": record.source,
                    "source_listing_id": record.source_listing_id,
                    "observed_date": observed_at.date().isoformat(),
                    "observed_at": stamp,
                    "price_pkr": record.price_pkr,
                    "price_text": record.price_text,
                }
                connection.execute(
                    insert(RawObservation)
                    .values(**observation)
                    .on_conflict_do_update(
                        index_elements=["source", "source_listing_id", "observed_date"],
                        set_=observation,
                    )
                )

    def count(self) -> int:
        with Session(self.engine) as session:
            return int(
                session.scalar(select(func.count()).select_from(RawVehicle)) or 0
            )
