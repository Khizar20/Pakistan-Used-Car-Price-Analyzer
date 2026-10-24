"""Explicitly opted-in source markup checks; excluded from default runs."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tracker.scraping.http import PoliteClient
from tracker.scraping.markup import sanitize_html
from tracker.scraping.pakwheels import SEARCH_URL, parse_list_page


@pytest.mark.live
def test_live_pakwheels(tmp_path: Path) -> None:
    contact = os.environ.get("TRACKER_CONTACT_EMAIL")
    if not contact:
        pytest.fail("Set TRACKER_CONTACT_EMAIL before opting into live tests")
    with PoliteClient(
        contact_email=contact, cache_dir=tmp_path, sanitize=sanitize_html
    ) as client:
        assert parse_list_page(client.get(SEARCH_URL))
