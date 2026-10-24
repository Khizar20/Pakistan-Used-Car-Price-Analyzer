"""Offline HTTP behavior tests using a fake clock and HTTPX mock transport."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from tracker.scraping.http import AccessBlockedError, PoliteClient, robots_allowed


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.value

    def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.value += delay


def client(
    tmp_path: Path, handler: object, clock: FakeClock | None = None, **kwargs: object
) -> PoliteClient:
    fake = clock or FakeClock()
    return PoliteClient(
        contact_email="research@example.com",
        cache_dir=tmp_path,
        transport=httpx.MockTransport(handler),
        clock=fake.now,
        sleep=fake.sleep,
        jitter=lambda: 0.25,
        now=lambda: datetime(2026, 10, 24, tzinfo=timezone.utc),
        **kwargs,
    )


def test_rate_limit_retries_and_cache(tmp_path: Path) -> None:
    fake = FakeClock()
    requests: list[tuple[str, float]] = []
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        assert "research@example.com" in request.headers["User-Agent"]
        requests.append((request.url.path, fake.value))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 3")
        attempts += 1
        return httpx.Response(503 if attempts == 1 else 200, text="<h1>Vehicle</h1>")

    with client(tmp_path, handler, fake) as http:
        assert http.get("https://example.com/cars") == "<h1>Vehicle</h1>"
        assert http.get("https://example.com/cars") == "<h1>Vehicle</h1>"
    assert len(requests) == 3
    assert [when for _, when in requests] == [0, 3.25, 6.5]


@pytest.mark.parametrize(
    "retry_after,minimum",
    [("10", 10), ("Sat, 24 Oct 2026 00:00:20 GMT", 20), ("invalid", 1)],
)
def test_retry_after(tmp_path: Path, retry_after: str, minimum: int) -> None:
    fake = FakeClock()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        calls += 1
        return (
            httpx.Response(429, headers={"Retry-After": retry_after})
            if calls == 1
            else httpx.Response(200, text="OK")
        )

    with client(tmp_path, handler, fake) as http:
        assert http.get("https://example.com/cars") == "OK"
    assert max(fake.sleeps) >= minimum


@pytest.mark.parametrize("status", [401, 403, 302, 503])
def test_robots_unavailable_fails_closed(tmp_path: Path, status: int) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(status)

    with client(tmp_path, handler, retries=0) as http:
        with pytest.raises((AccessBlockedError, httpx.HTTPStatusError)):
            http.get("https://example.com/cars")
    assert calls == ["/robots.txt"]


def test_robots_blocks_before_page_request(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/robots.txt"
        return httpx.Response(200, text="User-agent: *\nDisallow: /cars")

    with client(tmp_path, handler) as http:
        with pytest.raises(AccessBlockedError, match="disallows"):
            http.get("https://example.com/cars")


@pytest.mark.parametrize(
    "path,allowed",
    [
        ("/cars", False),
        ("/cars/public", True),
        ("/x.json", False),
        ("/x.json/more", True),
        ("/cars?sortby=price", False),
    ],
)
def test_robots_patterns(path: str, allowed: bool) -> None:
    text = (
        "User-agent: *\nDisallow: /cars\nAllow: /cars/public\n"
        "Disallow: /*.json$\nDisallow: /*?*sortby=*"
    )
    assert robots_allowed(text, "tracker", "https://example.com" + path)[0] is allowed


def test_specific_robots_group_and_invalid_delay() -> None:
    text = (
        "User-agent: *\nDisallow: /\nUser-agent: tracker\nUser-agent: other\n"
        "Crawl-delay: invalid\nAllow: /"
    )
    assert robots_allowed(text, "tracker/0.1", "https://example.com") == (True, 0)
    assert robots_allowed("", "tracker", "https://example.com") == (True, 0)


@pytest.mark.parametrize(
    "status,body", [(403, ""), (401, ""), (200, "<title>Just a moment...</title>")]
)
def test_access_block_stops_without_cache(
    tmp_path: Path, status: int, body: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(404)
            if request.url.path == "/robots.txt"
            else httpx.Response(status, text=body)
        )

    with client(tmp_path, handler) as http:
        with pytest.raises(AccessBlockedError):
            http.get("https://example.com/cars")
    assert not list(tmp_path.rglob("*.html"))


def test_redirect_is_checked_against_destination_robots(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "blocked.example":
            assert request.url.path == "/robots.txt"
            return httpx.Response(200, text="User-agent: *\nDisallow: /")
        return (
            httpx.Response(404)
            if request.url.path == "/robots.txt"
            else httpx.Response(
                302, headers={"Location": "https://blocked.example/cars"}
            )
        )

    with client(tmp_path, handler) as http:
        with pytest.raises(AccessBlockedError):
            http.get("https://example.com/cars")
    assert calls[-1] == "https://blocked.example/robots.txt"


def test_redirect_loop_is_bounded(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(404)
            if request.url.path == "/robots.txt"
            else httpx.Response(302, headers={"Location": "/loop"})
        )

    with client(tmp_path, handler) as http:
        with pytest.raises(AccessBlockedError, match="redirects"):
            http.get("https://example.com/cars")


def test_sanitized_cache_reused_across_clients_and_date_keys(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(404)
            if request.url.path == "/robots.txt"
            else httpx.Response(200, text="private")
        )

    with client(tmp_path, handler, sanitize=lambda _: "vehicle only") as http:
        assert http.get("https://example.com/cars") == "vehicle only"
    with client(
        tmp_path, lambda _: pytest.fail("Cache hit must not use network")
    ) as http:
        assert http.get("https://example.com/cars") == "vehicle only"
    assert len(list((tmp_path / "2026-10-24").glob("*.html"))) == 1


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "https://user:password@example.com", "invalid"]
)
def test_invalid_urls(tmp_path: Path, url: str) -> None:
    with client(tmp_path, lambda _: pytest.fail("No network")) as http:
        with pytest.raises(ValueError):
            http.get(url)


@pytest.mark.parametrize(
    "kwargs",
    [{"interval": 1}, {"retries": -1}, {"timeout": 0}, {"contact_email": "invalid"}],
)
def test_invalid_settings(tmp_path: Path, kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "contact_email": "research@example.com",
        "cache_dir": tmp_path,
        **kwargs,
    }
    with pytest.raises(ValueError):
        PoliteClient(**values)
