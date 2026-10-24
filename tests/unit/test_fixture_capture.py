"""Fixture capture is explicit, bounded, and tested without network calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import capture_fixtures
from tracker.scraping.pakwheels import SEARCH_URL


def test_capture_uses_minimized_documents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixtures = Path(__file__).parents[1] / "fixtures" / "html"

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            assert callable(kwargs["sanitize"])

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def get(self, url: str) -> str:
            name = (
                "pakwheels_list.html" if url == SEARCH_URL else "pakwheels_detail.html"
            )
            return (fixtures / name).read_text(encoding="utf-8")

    monkeypatch.setattr(capture_fixtures, "PoliteClient", FakeClient)
    capture_fixtures.capture(tmp_path, "research@example.com")
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "pakwheels_detail.html",
        "pakwheels_list.html",
        "pakwheels_missing_fields.html",
    ]
    assert "application/ld+json" not in (
        tmp_path / "pakwheels_missing_fields.html"
    ).read_text(encoding="utf-8")
