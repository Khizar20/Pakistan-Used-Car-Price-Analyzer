"""Offline end-to-end scrape tests against captured markup and real SQLite."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from tracker import cli
from tracker.config import ScrapeSettings
from tracker.scraping.base import ScrapeFilters
from tracker.scraping.http import AccessBlockedError, PoliteClient
from tracker.scraping.markup import sanitize_html
from tracker.scraping.pakwheels import PakWheelsAdapter, ParseError
from tracker.scraping.runner import run_scrape
from tracker.storage.staging import RawObservation, StagingStore

FIXTURES = Path(__file__).parents[1] / "fixtures/html"
NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


class Source:
    """Mutable mock source for price changes, removals and access failures."""

    def __init__(self) -> None:
        tree = BeautifulSoup(
            (FIXTURES / "pakwheels_list.html").read_text(encoding="utf-8"),
            "html.parser",
        )
        for node in tree.select("li.classified-listing")[1:]:
            node.decompose()
        self.html = str(tree)
        self.detail = (FIXTURES / "pakwheels_detail.html").read_text(encoding="utf-8")
        self.calls: list[str] = []
        self.detail_status = 200
        self.bad_search = False
        self.time = 0.0

    def sleep(self, delay: float) -> None:
        self.time += delay

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        if "for-sale-in" in request.url.path:
            return httpx.Response(self.detail_status, text=self.detail)
        if self.bad_search and request.url.path.endswith("/642"):
            return httpx.Response(200, text="<html>Markup changed</html>")
        return httpx.Response(200, text=self.html)

    def client(self, cache_dir: Path) -> PoliteClient:
        return PoliteClient(
            contact_email="research@example.com",
            cache_dir=cache_dir,
            transport=httpx.MockTransport(self.handler),
            clock=lambda: self.time,
            sleep=self.sleep,
            jitter=lambda: 0,
            now=lambda: NOW,
            sanitize=sanitize_html,
        )


def test_three_pages_and_restart_only_refetch_list_price(tmp_path: Path) -> None:
    source = Source()
    path = tmp_path / "tracker.sqlite3"
    with source.client(tmp_path / "cache1") as client, StagingStore.open(path) as store:
        result = run_scrape(
            adapter=PakWheelsAdapter(),
            client=client,
            store=store,
            filters=ScrapeFilters(limit_pages=3),
            observed_at=NOW,
        )
        assert (result.search_pages, result.listings_seen, result.detail_pages) == (
            3,
            1,
            1,
        )
        assert result.detail_errors == 0
        assert len(result.model_paths) == 10
    detail_calls = sum("for-sale-in" in url for url in source.calls)
    source.html = source.html.replace('"price": 5900000', '"price": 5800000')
    with source.client(tmp_path / "cache2") as client, StagingStore.open(path) as store:
        result = run_scrape(
            adapter=PakWheelsAdapter(),
            client=client,
            store=store,
            filters=ScrapeFilters(limit_pages=3),
            observed_at=NOW + timedelta(days=1),
        )
        assert result.detail_pages == 0
        assert sum("for-sale-in" in url for url in source.calls) == detail_calls
        with Session(store.engine) as session:
            rows = session.scalars(
                select(RawObservation).order_by(RawObservation.observed_date)
            ).all()
            assert [row.price_pkr for row in rows] == [5900000, 5800000]


@pytest.mark.parametrize("status", [404, 410])
def test_missing_detail_keeps_summary_and_retries_next_run(
    tmp_path: Path, status: int
) -> None:
    source = Source()
    source.detail_status = status
    with (
        source.client(tmp_path / "cache1") as client,
        StagingStore.open(tmp_path / "db.sqlite3") as store,
    ):
        result = run_scrape(
            adapter=PakWheelsAdapter(),
            client=client,
            store=store,
            filters=ScrapeFilters(limit_pages=1),
            observed_at=NOW,
        )
        assert result.detail_errors == 1
        assert store.count() == 1
    source.detail_status = 200
    with (
        source.client(tmp_path / "cache2") as client,
        StagingStore.open(tmp_path / "db.sqlite3") as store,
    ):
        result = run_scrape(
            adapter=PakWheelsAdapter(),
            client=client,
            store=store,
            filters=ScrapeFilters(limit_pages=1),
            observed_at=NOW,
        )
        assert result.detail_pages == 1
        assert result.detail_errors == 0


@pytest.mark.parametrize("mode", ["missing_schema", "wrong_vehicle"])
def test_invalid_detail_remains_retryable(tmp_path: Path, mode: str) -> None:
    source = Source()
    source.detail = (
        "<html>Missing listing</html>"
        if mode == "missing_schema"
        else source.detail.replace("900002", "999999")
    )
    with (
        source.client(tmp_path / "cache") as client,
        StagingStore.open(tmp_path / "db.sqlite3") as store,
    ):
        result = run_scrape(
            adapter=PakWheelsAdapter(),
            client=client,
            store=store,
            filters=ScrapeFilters(limit_pages=1),
            observed_at=NOW,
        )
        assert result.detail_errors == 1
        assert store.count() == 1


@pytest.mark.parametrize(
    "status,exception", [(403, AccessBlockedError), (503, httpx.HTTPStatusError)]
)
def test_access_or_server_failure_stops_page_atomically(
    tmp_path: Path, status: int, exception: type[Exception]
) -> None:
    source = Source()
    source.detail_status = status
    with (
        source.client(tmp_path / "cache") as client,
        StagingStore.open(tmp_path / "db.sqlite3") as store,
    ):
        with pytest.raises(exception):
            run_scrape(
                adapter=PakWheelsAdapter(),
                client=client,
                store=store,
                filters=ScrapeFilters(limit_pages=1),
                observed_at=NOW,
            )
        assert store.count() == 0


def test_later_broken_search_page_preserves_committed_page(tmp_path: Path) -> None:
    source = Source()
    source.bad_search = True
    with (
        source.client(tmp_path / "cache") as client,
        StagingStore.open(tmp_path / "db.sqlite3") as store,
    ):
        with pytest.raises(ParseError):
            run_scrape(
                adapter=PakWheelsAdapter(),
                client=client,
                store=store,
                filters=ScrapeFilters(limit_pages=3),
                observed_at=NOW,
            )
        assert store.count() == 1


def test_detail_budget_and_withdrawn_price(tmp_path: Path) -> None:
    source = Source()
    with (
        source.client(tmp_path / "cache") as client,
        StagingStore.open(tmp_path / "db.sqlite3") as store,
    ):
        first = run_scrape(
            adapter=PakWheelsAdapter(),
            client=client,
            store=store,
            filters=ScrapeFilters(limit_pages=1),
            observed_at=NOW,
            max_new_details=0,
        )
        assert first.detail_pages == 0
        assert store.count() == 1
    tree = BeautifulSoup(source.html, "html.parser")
    script = tree.select_one('script[type="application/ld+json"]')
    data = json.loads(script.get_text())
    data["offers"].pop("price")
    script.string = json.dumps(data)
    price = tree.select_one(".price-details")
    price.string = "Call for price"
    source.html = str(tree)
    with (
        source.client(tmp_path / "cache2") as client,
        StagingStore.open(tmp_path / "db.sqlite3") as store,
    ):
        result = run_scrape(
            adapter=PakWheelsAdapter(),
            client=client,
            store=store,
            filters=ScrapeFilters(limit_pages=1),
            observed_at=NOW,
        )
        assert result.detail_pages == 1
        with Session(store.engine) as session:
            row = session.scalar(select(RawObservation))
            assert row.price_pkr is None
            assert row.price_text == "Call for price"


def test_cli_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = Source()
    monkeypatch.setattr(
        cli, "PoliteClient", lambda **kwargs: source.client(kwargs["cache_dir"])
    )
    result = CliRunner().invoke(
        cli.app,
        [
            "scrape",
            "--source",
            "pakwheels",
            "--limit-pages",
            "3",
            "--contact-email",
            "research@example.com",
            "--database",
            str(tmp_path / "db.sqlite3"),
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Saved 1 unique listings from 3 search pages" in result.output


@pytest.mark.parametrize("status", [403, 503, 404])
def test_cli_reports_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    source = Source()
    source.detail_status = status
    monkeypatch.setattr(
        cli, "PoliteClient", lambda **kwargs: source.client(kwargs["cache_dir"])
    )
    result = CliRunner().invoke(
        cli.app,
        [
            "scrape",
            "--limit-pages",
            "1",
            "--contact-email",
            "research@example.com",
            "--database",
            str(tmp_path / "db.sqlite3"),
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 1
    assert (
        "Collection stopped" in result.output
        if status != 404
        else "1 detail errors" in result.output
    )


@pytest.mark.parametrize(
    "args",
    [
        ["--source", "unknown"],
        ["--limit-pages", "0"],
        ["--contact-email", "invalid"],
        [],
    ],
)
def test_cli_rejects_invalid_configuration(
    args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TRACKER_CONTACT_EMAIL", raising=False)
    result = CliRunner().invoke(cli.app, ["scrape", *args])
    assert result.exit_code == 2


def test_runner_rejects_invalid_settings_before_fetch(tmp_path: Path) -> None:
    source = Source()
    with (
        source.client(tmp_path / "cache") as client,
        StagingStore.open(tmp_path / "db.sqlite3") as store,
    ):
        for values in (
            {"max_new_details": -1, "observed_at": NOW},
            {"observed_at": NOW.replace(tzinfo=None)},
        ):
            with pytest.raises(ValueError):
                run_scrape(
                    adapter=PakWheelsAdapter(),
                    client=client,
                    store=store,
                    filters=ScrapeFilters(),
                    **values,
                )
    assert source.calls == []
    assert ScrapeSettings(contact_email="research@example.com").database == Path(
        "data/tracker.sqlite3"
    )


def test_verified_partial_detail_is_merged_with_its_summary(tmp_path: Path) -> None:
    source = Source()
    tree = BeautifulSoup(source.detail, "html.parser")
    tree.select_one('script[type="application/ld+json"]').decompose()
    source.detail = str(tree)
    with (
        source.client(tmp_path / "cache") as client,
        StagingStore.open(tmp_path / "db.sqlite3") as store,
    ):
        result = run_scrape(
            adapter=PakWheelsAdapter(),
            client=client,
            store=store,
            filters=ScrapeFilters(limit_pages=1),
            observed_at=NOW,
        )
        assert result.detail_errors == 0
        summary = PakWheelsAdapter.parse_list_page(source.html)[0]
        record, fetched = store.get(summary)
        assert fetched is True
        assert record.price_pkr == 5900000
        assert record.model == "BR-V"
        assert record.color == "Teffeta White"
