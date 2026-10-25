"""Fixture-based source contracts, exact extraction, and malformed-page cases."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from pydantic import ValidationError

from tracker.models import RawListing
from tracker.scraping.base import ScrapeFilters, SourceAdapter
from tracker.scraping.markup import (
    anonymize_fixture,
    clean_schema,
    load_object,
    sanitize_html,
)
from tracker.scraping.pakwheels import (
    PakWheelsAdapter,
    ParseError,
    discover_model_paths,
    parse_detail_page,
    parse_list_page,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "html"


@pytest.fixture
def list_html() -> str:
    return (FIXTURES / "pakwheels_list.html").read_text(encoding="utf-8")


@pytest.fixture
def detail_html() -> str:
    return (FIXTURES / "pakwheels_detail.html").read_text(encoding="utf-8")


def test_exact_list_records(list_html: str) -> None:
    records = parse_list_page(list_html)
    assert len(records) == 3
    first, second, third = records
    assert first.model_dump() == {
        "source": "pakwheels",
        "source_listing_id": "900002",
        "url": "https://www.pakwheels.com/used-cars/honda-br-v-2024-for-sale-in-karachi-900002",
        "make": "Honda",
        "model": "BR-V",
        "variant": "i-VTEC S",
        "model_year": 2024,
        "price_text": "PKR 59 lacs",
        "price_pkr": 5900000,
        "mileage_text": "33,632 km",
        "engine_text": "1500cc",
        "transmission": "Automatic",
        "fuel_type": "Petrol",
        "city": "Karachi",
        "body_type": None,
        "assembly": None,
        "color": None,
        "registered_city": None,
        "seller_type": None,
        "is_featured": True,
        "has_photos_count": 14,
        "features": None,
        "photo": None,
    }
    assert (second.make, second.model, second.price_pkr, second.fuel_type) == (
        "Suzuki",
        "Xbee",
        4300000,
        "Hybrid",
    )
    assert (third.model_year, third.price_pkr, third.transmission, third.city) == (
        2011,
        2375000,
        "Manual",
        "Sialkot",
    )
    assert first.url_hash == hashlib.sha256(first.url.encode()).hexdigest()


def test_detail_matches_primary_not_related_car(detail_html: str) -> None:
    record = parse_detail_page(detail_html)
    assert (record.make, record.model, record.variant, record.model_year) == (
        "Honda",
        "BR-V",
        "i-VTEC S",
        2024,
    )
    assert (record.price_pkr, record.mileage_text, record.engine_text) == (
        5900000,
        "33,632 km",
        "1500cc",
    )
    assert (record.color, record.body_type, record.assembly) == (
        "Teffeta White",
        "MPV",
        "Local",
    )
    assert record.registered_city == "Karachi"
    assert record.features == [
        "Alloy Wheels",
        "Front Fog Lights",
        "DRLs",
        "Infotainment System",
        "Front Speakers",
        "Rear Speakers",
        "Steering Switches",
        "ABS",
        "Air Bags",
        "Rear Camera",
        "Immobilizer Key",
        "Power Locks",
        "Power Mirrors",
        "Rear AC Vents",
        "Climate Control",
        "Push Start",
        "Keyless Entry",
        "Power Steering",
        "Air Conditioning",
    ]


def test_missing_fields_are_none_with_warnings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    html = (FIXTURES / "pakwheels_missing_fields.html").read_text(encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        records = parse_list_page(html)
    assert len(records) == 3
    assert all(
        record.price_pkr is None and record.mileage_text is None for record in records
    )
    assert "missing price_pkr" in caplog.text
    assert "missing mileage_text" in caplog.text
    assert records[0].model == "BR-V"


@pytest.mark.parametrize(
    "html",
    [
        "",
        "<html>Unavailable</html>",
        '<li class="classified-listing"></li>',
        '<li class="classified-listing"><a class="car-name" href="https://evil.example/car">Bad</a></li>',
    ],
)
def test_empty_or_broken_pages_raise(html: str) -> None:
    with pytest.raises(ParseError, match="No listings"):
        parse_list_page(html)


@pytest.mark.parametrize("selector", ['link[rel="canonical"]'])
def test_detail_missing_primary_identity_raises(
    detail_html: str, selector: str
) -> None:
    tree = BeautifulSoup(detail_html, "html.parser")
    for node in tree.select(selector):
        node.decompose()
    with pytest.raises(ParseError, match="Primary vehicle"):
        parse_detail_page(str(tree))


def test_duplicates_and_empty_cards_do_not_duplicate_records(list_html: str) -> None:
    tree = BeautifulSoup(list_html, "html.parser")
    assert (
        len(parse_list_page(list_html + str(tree.select_one("li.classified-listing"))))
        == 3
    )


def test_metadata_fallback_without_json_and_missing_spec_position(
    list_html: str,
) -> None:
    tree = BeautifulSoup(list_html, "html.parser")
    for node in tree.select("script,.search-vehicle-info-2 li:nth-child(2)"):
        node.decompose()
    record = parse_list_page(str(tree))[0]
    assert record.model_year == 2024
    assert record.mileage_text is None
    assert record.fuel_type == "Petrol"
    assert record.engine_text == "1500 cc"
    assert record.transmission == "Automatic"
    assert record.city == "Karachi"


@pytest.mark.parametrize("value", [True, -1, 1.5, "not a price", None])
def test_invalid_structured_price_degrades_to_none(
    list_html: str, value: object
) -> None:
    tree = BeautifulSoup(list_html, "html.parser")
    script = tree.select_one("li.classified-listing script")
    data = json.loads(script.get_text())
    data["offers"]["price"] = value
    script.string = json.dumps(data)
    assert parse_list_page(str(tree))[0].price_pkr is None


def test_string_price_and_year_are_accepted(list_html: str) -> None:
    tree = BeautifulSoup(list_html, "html.parser")
    script = tree.select_one("li.classified-listing script")
    data = json.loads(script.get_text())
    data["offers"]["price"] = "5900000"
    data["modelDate"] = "2024"
    script.string = json.dumps(data)
    assert parse_list_page(str(tree))[0].price_pkr == 5900000


def test_numeric_dom_price_survives_cache_when_json_is_empty(list_html: str) -> None:
    tree = BeautifulSoup(list_html, "html.parser")
    card = tree.select_one("li.classified-listing")
    card.select_one("script").string = "{}"
    card.append(
        BeautifulSoup(
            '<button data-price="5900000">Show Phone No.</button>', "html.parser"
        )
    )
    assert parse_list_page(sanitize_html(str(tree)))[0].price_pkr == 5900000


def test_real_model_search_numeric_prices() -> None:
    html = (FIXTURES / "pakwheels_model_list.html").read_text(encoding="utf-8")
    first, second = parse_list_page(html)
    assert (first.model_year, first.price_pkr, first.mileage_text) == (
        2016,
        4500000,
        "83,500 km",
    )
    assert (second.model_year, second.price_pkr) == (2025, 7700000)
    assert parse_list_page(sanitize_html(html)) == [first, second]


def test_detail_fallback_labels_and_missing_features(detail_html: str) -> None:
    tree = BeautifulSoup(detail_html, "html.parser")
    for script in tree.select('script[type="application/ld+json"]'):
        data = json.loads(script.get_text())
        for key in ("color", "bodyType", "modelDate"):
            data.pop(key, None)
        script.string = json.dumps(data)
    for node in tree.select(".car-feature-list"):
        node.decompose()
    record = parse_detail_page(str(tree))
    assert record.color == "Teffeta White"
    assert record.body_type == "MPV"
    assert record.model_year == 2024
    assert record.features is None


def test_adapter_protocol_and_bounded_round_robin_pages(list_html: str) -> None:
    adapter = PakWheelsAdapter()
    assert isinstance(adapter, SourceAdapter)
    paths = discover_model_paths(list_html)
    assert len(paths) == 10
    assert paths[:3] == (
        "/used-cars/toyota-corolla/688",
        "/used-cars/honda-civic/642",
        "/used-cars/honda-city/664",
    )
    pages = list(
        adapter.iter_listing_pages(ScrapeFilters(limit_pages=11, model_paths=paths))
    )
    assert len(pages) == 11
    assert pages[0] == "https://www.pakwheels.com/used-cars/toyota-corolla/688"
    assert pages[10] == pages[0] + "?page=2"
    assert len(list(adapter.iter_listing_pages(ScrapeFilters()))) == 3


@pytest.mark.parametrize(
    "path", ["https://evil.example", "/login", "/used-cars/foo/12?sortby=x"]
)
def test_invalid_search_paths_rejected(path: str) -> None:
    with pytest.raises(ValueError):
        list(PakWheelsAdapter().iter_listing_pages(ScrapeFilters(model_paths=(path,))))


@pytest.mark.parametrize("count", [0, 9, 16])
def test_scope_count_validation(list_html: str, count: int) -> None:
    with pytest.raises(ValueError):
        discover_model_paths(list_html, count)


def test_missing_scope_cannot_silently_broaden_collection() -> None:
    with pytest.raises(ParseError, match="scope"):
        discover_model_paths(
            '<div class="related_searches"><h3>View Cars by Model</h3></div>'
        )


@pytest.mark.parametrize(
    "bad",
    [
        {"price_pkr": -1},
        {"model_year": 1800},
        {"url": "file:///private"},
        {"phone": "private"},
    ],
)
def test_record_validation(bad: dict[str, object]) -> None:
    values = {
        "source_listing_id": "900001",
        "url": "https://www.pakwheels.com/used-cars/honda-civic-2011-for-sale-in-sialkot-900001",
        **bad,
    }
    with pytest.raises(ValidationError):
        RawListing.model_validate(values)


@pytest.mark.parametrize("value", ["invalid", "[]", "null", "42"])
def test_malformed_json(value: str) -> None:
    assert load_object(value) == {}


def test_sanitization_removes_unneeded_data_preserves_parser(list_html: str) -> None:
    extra = (
        '<div class="seller">Private Person, 03001234567</div>'
        '<script>token="private"</script><img src="secret-photo">'
        "<p>Exact street address</p>"
    )
    original = parse_list_page(list_html)
    sanitized = sanitize_html(list_html + extra)
    assert parse_list_page(sanitized) == original
    for private in (
        "Private Person",
        "03001234567",
        "Exact street",
        "secret-photo",
        "token=",
    ):
        assert private not in sanitized
    assert sanitize_html(sanitized) == sanitized


def test_schema_allowlist_and_anonymization() -> None:
    result = clean_schema(
        {
            "offers": {"price": 10, "seller": "private"},
            "description": "private",
            "brand": {"name": "Honda", "phone": "private"},
        }
    )
    assert result == {"offers": {"price": 10}, "brand": {"name": "Honda"}}
    assert "12345678" not in anonymize_fixture(
        '<a href="/used-cars/honda-city-2020-for-sale-in-lahore-12345678"></a>'
    )


def test_detail_sanitization_and_irrelevant_schema(detail_html: str) -> None:
    tree = BeautifulSoup(detail_html, "html.parser")
    heading = tree.select_one("h1")
    heading.append(BeautifulSoup('<img src="private">', "html.parser"))
    tree.append(
        BeautifulSoup(
            '<script type="application/ld+json">'
            '{"@type":"WebPage","description":"private"}</script>',
            "html.parser",
        )
    )
    sanitized = sanitize_html(str(tree))
    assert parse_detail_page(sanitized) == parse_detail_page(detail_html)
    assert "private" not in sanitized


def test_sanitizer_empty_card_and_scope_without_group() -> None:
    html = (
        '<li class="classified-listing"></li><div class="related_searches">'
        "<h3>Other</h3><h3>View Cars by Model</h3></div>"
    )
    assert "classified-listing" in sanitize_html(html)


def test_real_detail_without_primary_schema_never_uses_related_car() -> None:
    html = (FIXTURES / "pakwheels_detail_missing_schema.html").read_text(
        encoding="utf-8"
    )
    record = parse_detail_page(html)
    assert record.source_listing_id == "900005"
    assert record.price_pkr is None
    assert record.make is None
    assert record.body_type == "Sedan"
    assert record.color == "Black"
    assert record.assembly == "Local"
    assert len(record.features) == 10


@pytest.mark.parametrize("selector", ["h1", "#scroll_car_detail"])
def test_partial_detail_requires_visible_identity(selector: str) -> None:
    html = (FIXTURES / "pakwheels_detail_missing_schema.html").read_text(
        encoding="utf-8"
    )
    tree = BeautifulSoup(html, "html.parser")
    for node in tree.select(selector):
        node.decompose()
    with pytest.raises(ParseError, match="identity"):
        parse_detail_page(str(tree))
