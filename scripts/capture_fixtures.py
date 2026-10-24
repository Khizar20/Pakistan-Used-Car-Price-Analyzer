"""Explicit, live-only capture of tiny vehicle-only parser fixtures."""

from __future__ import annotations

import argparse
from pathlib import Path

from bs4 import BeautifulSoup

from tracker.scraping.http import PoliteClient
from tracker.scraping.markup import anonymize_fixture, sanitize_html
from tracker.scraping.pakwheels import SEARCH_URL


def capture(destination: Path, contact_email: str) -> None:
    """Fetch a search page and one detail page; minimize before saving anything."""
    destination.mkdir(parents=True, exist_ok=True)
    with PoliteClient(
        contact_email=contact_email,
        cache_dir=Path("raw/fixtures"),
        sanitize=sanitize_html,
    ) as client:
        html = client.get(SEARCH_URL)
        tree = BeautifulSoup(html, "html.parser")
        cards = tree.select("li.classified-listing")
        if not cards:
            raise RuntimeError("No cards available for real HTML fixtures")
        link = cards[0].select_one("a.car-name[href]")
        if link is None:
            raise RuntimeError("First listing has no detail link")
        url = "https://www.pakwheels.com" + str(link["href"])
        detail = client.get(url)
    # Keep three actual cards, not an entire source search response.
    for card in cards[3:]:
        card.decompose()
    minimized = anonymize_fixture(str(tree))
    (destination / "pakwheels_list.html").write_text(minimized, encoding="utf-8")
    (destination / "pakwheels_detail.html").write_text(
        anonymize_fixture(detail), encoding="utf-8"
    )
    edge = BeautifulSoup(minimized, "html.parser")
    for node in edge.select("script,.search-vehicle-info-2,.price-details"):
        node.decompose()
    (destination / "pakwheels_missing_fields.html").write_text(
        str(edge), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contact-email", required=True)
    parser.add_argument("--destination", type=Path, default=Path("tests/fixtures/html"))
    args = parser.parse_args()
    capture(args.destination, args.contact_email)


if __name__ == "__main__":
    main()
