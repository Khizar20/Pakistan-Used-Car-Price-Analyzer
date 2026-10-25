"""Synchronous, rate-limited public-page access with fail-closed robots checks."""

from __future__ import annotations

import hashlib
import random
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx


class AccessBlockedError(RuntimeError):
    """The source denied access; callers must stop instead of trying to evade it."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def robots_allowed(text: str, user_agent: str, url: str) -> tuple[bool, float]:
    """Evaluate longest-match robots rules, including wildcard and end anchors."""
    groups: list[tuple[list[str], list[tuple[str, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
        elif agents and key in {"allow", "disallow", "crawl-delay"}:
            rules.append((key, value))
    groups.append((agents, rules))
    matching = [
        (
            max(
                len(a) if a != "*" else 0
                for a in names
                if a == "*" or a in user_agent.lower()
            ),
            entries,
        )
        for names, entries in groups
        if any(a == "*" or a in user_agent.lower() for a in names)
    ]
    specificity = max((score for score, _ in matching), default=-1)
    parts = urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    matches: list[tuple[int, bool]] = []
    delay = 0.0
    for score, entries in matching:
        if score != specificity:
            continue
        for key, value in entries:
            if key == "crawl-delay":
                try:
                    delay = max(delay, float(value))
                except ValueError:
                    continue
            elif value:
                anchored = value.endswith("$")
                pattern = value[:-1] if anchored else value
                pattern = "^" + ".*".join(re.escape(p) for p in pattern.split("*"))
                if re.search(pattern + ("$" if anchored else ""), path):
                    matches.append(
                        (len(value.replace("*", "").rstrip("$")), key == "allow")
                    )
    return max(matches, default=(0, True))[1], delay


class PoliteClient:
    """Single-worker HTTP client; all attempts share per-origin start-time limits."""

    def __init__(
        self,
        *,
        contact_email: str,
        cache_dir: Path,
        timeout: float = 30,
        retries: int = 3,
        interval: float = 2,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
        now: Callable[[], datetime] = _utcnow,
        sanitize: Callable[[str], str] | None = None,
    ) -> None:
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact_email):
            raise ValueError("A valid contact email is required.")
        if interval < 2 or retries < 0 or timeout <= 0:
            raise ValueError("Use interval >= 2, retries >= 0, and timeout > 0.")
        self.user_agent = (
            "PakistanUsedCarPriceTracker/0.1 "
            f"(educational research; contact: {contact_email})"
        )
        self._client = httpx.Client(
            headers={"User-Agent": self.user_agent},
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )
        self.cache_dir = cache_dir
        self.retries = retries
        self.interval = interval
        self.clock, self.sleep, self.jitter, self.now = clock, sleep, jitter, now
        self.sanitize = sanitize
        self._last: dict[str, float] = {}
        self._robots: dict[str, str] = {}
        self._delays: dict[str, float] = {}

    def __enter__(self) -> PoliteClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username:
            raise ValueError(
                "Only public HTTP(S) URLs without credentials are supported."
            )
        return f"{parts.scheme}://{parts.netloc}"

    def _request(self, url: str, *, max_bytes: int | None = None) -> httpx.Response:
        origin = self._origin(url)
        for attempt in range(self.retries + 1):
            if origin in self._last:
                gap = max(self.interval, self._delays.get(origin, 0))
                wait = self._last[origin] + gap + max(0, self.jitter()) - self.clock()
                if wait > 0:
                    self.sleep(wait)
            self._last[origin] = self.clock()
            if max_bytes is None:
                response = self._client.get(url)
            else:
                with self._client.stream("GET", url) as streamed:
                    body = bytearray()
                    for chunk in streamed.iter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            raise ValueError("Thumbnail exceeds download limit")
                    response = httpx.Response(
                        streamed.status_code,
                        headers=streamed.headers,
                        content=bytes(body),
                        request=streamed.request,
                    )
            if response.status_code not in {429, 500, 502, 503, 504}:
                return response
            if attempt == self.retries:
                response.raise_for_status()
            delay = float(2**attempt)
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    try:
                        delay = max(
                            delay,
                            (
                                parsedate_to_datetime(retry_after) - self.now()
                            ).total_seconds(),
                        )
                    except (ValueError, TypeError, OverflowError):
                        pass
            self.sleep(delay)
        raise AssertionError("Unreachable retry loop")

    def _check_robots(self, url: str) -> None:
        origin = self._origin(url)
        if origin not in self._robots:
            response = self._request(origin + "/robots.txt")
            if response.status_code == 404:
                self._robots[origin] = ""
            elif response.status_code in {401, 403} or response.is_redirect:
                raise AccessBlockedError(
                    "Cannot verify robots.txt; collection stopped."
                )
            else:
                response.raise_for_status()
                self._robots[origin] = response.text
        allowed, delay = robots_allowed(self._robots[origin], self.user_agent, url)
        self._delays[origin] = delay
        if not allowed:
            raise AccessBlockedError(
                "robots.txt disallows this page; collection stopped."
            )

    def get_photo(self, url: str) -> bytes:
        """Download an allowlisted thumbnail with robots, throttling and size limits."""
        from tracker.models import PHOTO_URL

        if not PHOTO_URL.fullmatch(url):
            raise ValueError("Only observed source thumbnails are supported")
        self._check_robots(url)
        response = self._request(url, max_bytes=2_000_000)
        if response.status_code in {401, 403} or response.is_redirect:
            raise AccessBlockedError("Photo access denied; collection stopped.")
        response.raise_for_status()
        if response.headers.get("content-type", "").split(";")[0] not in {
            "image/webp",
            "image/jpeg",
            "image/png",
        }:
            raise ValueError("Expected a vehicle thumbnail image")
        return response.content

    def get(self, url: str) -> str:
        """Fetch a permitted page or reuse its same-day, URL-keyed cache."""
        self._origin(url)
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache_dir / self.now().date().isoformat() / f"{key}.html"
        if path.exists():
            return path.read_text(encoding="utf-8")
        current = url
        for _ in range(6):
            self._check_robots(current)
            response = self._request(current)
            if response.status_code in {401, 403}:
                raise AccessBlockedError("Source denied access; collection stopped.")
            if response.is_redirect:
                current = urljoin(current, response.headers["Location"])
                continue
            response.raise_for_status()
            if re.search(
                r"<title[^>]*>\s*(?:just a moment|access denied|"
                r"attention required|verify you are human)",
                response.text,
                re.IGNORECASE,
            ):
                raise AccessBlockedError(
                    "Source presented an access challenge; collection stopped."
                )
            html = self.sanitize(response.text) if self.sanitize else response.text
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(html, encoding="utf-8")
            temporary.replace(path)
            return html
        raise AccessBlockedError("Too many redirects; collection stopped.")
