"""Pure parsers against observed PakWheels public-page markup."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from bs4.element import PageElement
from pydantic import ValidationError

from tracker.models import LISTING_URL, RawListing
from tracker.scraping.base import ScrapeFilters
from tracker.scraping.markup import load_object, object_dict

BASE_URL = "https://www.pakwheels.com"
SEARCH_URL = BASE_URL + "/used-cars/search/-/"
logger = logging.getLogger(__name__)


class ParseError(ValueError):
    """Expected listing structure is missing or invalid."""


def _text(node: PageElement | None) -> str | None:
    return " ".join(node.stripped_strings) or None if isinstance(node, Tag) else None


def _string(value: object) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _product(node: BeautifulSoup | Tag, url: str) -> dict[str, object]:
    for script in node.select('script[type="application/ld+json"]'):
        data = load_object(script.get_text())
        if object_dict(data.get("offers")).get("url") == url:
            return data
    return {}


def _record(
    node: BeautifulSoup | Tag,
    url: str,
    *,
    detail: bool,
) -> RawListing:
    match = LISTING_URL.fullmatch(url)
    if not match:
        raise ParseError("Missing or invalid public listing URL")
    data = _product(node, url)
    event_node = node.select_one("[data-ga4-event]") if not detail else None
    event = load_object(str(event_node.get("data-ga4-event", ""))) if event_node else {}
    make = _string(object_dict(data.get("brand")).get("name")) or _string(
        event.get("item_category2")
    )
    model = _string(data.get("model")) or _string(event.get("item_category3"))
    variant = _string(event.get("item_category4"))
    title = _text(node.select_one("h1" if detail else ".car-name h3"))
    year = _integer(data.get("modelDate"))
    if title and not year:
        found = re.search(r"\b(19\d{2}|20\d{2})\b", title)
        year = int(found[0]) if found else None
    if title and make and model and not variant:
        remainder = title.removeprefix(f"{make} {model}").strip()
        remainder = re.sub(r"\b(?:19\d{2}|20\d{2})\b|for Sale", "", remainder).strip()
        variant = remainder or None
    city = _string(event.get("city"))
    if not city:
        name = _string(data.get("name")) or ""
        found_city = re.search(r" for sale in ([A-Za-z .-]+)$", name)
        city = (
            found_city[1]
            if found_city
            else _text(node.select_one(".search-vehicle-info li"))
        )
    specs: dict[str, str] = {}
    if detail:
        for label in node.select("#scroll_car_detail li.ad-data"):
            specs[_text(label) or ""] = _text(label.find_next_sibling("li")) or ""
    mileage = _string(data.get("mileageFromOdometer"))
    engine = _string(object_dict(data.get("vehicleEngine")).get("engineDisplacement"))
    transmission = _string(data.get("vehicleTransmission"))
    fuel = _string(data.get("fuelType"))
    # Positional fields are not used: missing mileage must not shift the fuel.
    for item in node.select(".search-vehicle-info-2 li"):
        value = _text(item) or ""
        if re.fullmatch(r"[\d,]+\s*km", value, re.IGNORECASE):
            mileage = mileage or value
        elif re.fullmatch(r"\d+\s*cc", value, re.IGNORECASE):
            engine = engine or value
        elif value in {"Automatic", "Manual"}:
            transmission = transmission or value
        elif value in {"Petrol", "Diesel", "Hybrid", "PHEV", "Electric", "CNG", "LPG"}:
            fuel = fuel or value
    price = _integer(object_dict(data.get("offers")).get("price"))
    numeric = node.select_one("[data-price]") if not detail else None
    if price is None and numeric is not None:
        price = _integer(numeric.get("data-price"))
    photo_text = _text(node.select_one(".total-pictures-bar"))
    features = [_text(item) for item in node.select(".car-feature-list li")]
    values: dict[str, object] = {
        "source_listing_id": match[1],
        "url": url,
        "make": make,
        "model": model,
        "variant": variant,
        "model_year": year if year and 1900 <= year <= 2100 else None,
        "price_text": _text(
            node.select_one(
                ".price-box strong,strong.generic-green" if detail else ".price-details"
            )
        ),
        "price_pkr": price,
        "mileage_text": mileage,
        "engine_text": engine,
        "transmission": transmission,
        "fuel_type": fuel,
        "city": city,
        "body_type": _string(data.get("bodyType")) or specs.get("Body Type") or None,
        "assembly": specs.get("Assembly") or None,
        "color": _string(data.get("color")) or specs.get("Color") or None,
        "registered_city": specs.get("Registered In") or None,
        "features": [value for value in features if value] if features else None,
        "is_featured": None
        if detail
        else "featured-listing" in node.get_attribute_list("class"),
        "has_photos_count": _integer(photo_text),
    }
    for field in (
        "make",
        "model",
        "model_year",
        "price_pkr",
        "mileage_text",
        "engine_text",
        "transmission",
        "fuel_type",
        "city",
    ):
        if values[field] is None:
            logger.warning("Listing %s is missing %s", match[1], field)
    return RawListing.model_validate(values)


def parse_list_page(html: str) -> list[RawListing]:
    """Extract unique listing records; never silently accept an empty page."""
    tree = BeautifulSoup(html, "html.parser")
    records: dict[str, RawListing] = {}
    for card in tree.select("li.classified-listing"):
        link = card.select_one("a.car-name[href]")
        if not link:
            logger.warning("Skipping a listing card with no vehicle link")
            continue
        url = urljoin(BASE_URL, str(link.get("href", "")))
        try:
            record = _record(card, url, detail=False)
        except (ParseError, ValidationError):
            logger.warning("Skipping a listing card with invalid vehicle identity")
            continue
        records[record.source_listing_id] = record
    if not records:
        raise ParseError("No listings found; check the page, scope, or site markup")
    return list(records.values())


def parse_detail_page(html: str) -> RawListing:
    """Match the primary vehicle schema, excluding related-listing schemas."""
    tree = BeautifulSoup(html, "html.parser")
    canonical = tree.select_one('link[rel="canonical"]')
    url = str(canonical.get("href", "")) if canonical else ""
    match = LISTING_URL.fullmatch(url)
    if not match:
        raise ParseError("Primary vehicle schema or canonical URL is missing")
    if not _product(tree, url):
        # Some detail pages omit primary JSON while recommendations have it.
        # Require two independent visible identity signals before partial recovery.
        reference = next(
            (
                label.find_next_sibling("li")
                for label in tree.select("#scroll_car_detail li.ad-data")
                if _text(label) == "Ad Ref #"
            ),
            None,
        )
        if tree.select_one("h1") is None or _text(reference) != match[1]:
            raise ParseError("Primary vehicle identity could not be verified")
    return _record(tree, url, detail=True)


def discover_model_paths(html: str, count: int = 10) -> tuple[str, ...]:
    """Rank the site's model links by displayed approximate listing volume."""
    if not 10 <= count <= 15:
        raise ValueError("Choose 10 to 15 models")
    tree = BeautifulSoup(html, "html.parser")
    models: dict[str, int] = {}
    for heading in tree.select(".related_searches h3"):
        if heading.get_text(strip=True) != "View Cars by Model":
            continue
        group = heading.find_next_sibling("ul")
        if not isinstance(group, Tag):
            continue
        for link in group.select("a[href]"):
            path = str(link.get("href"))
            text = link.parent.get_text(" ", strip=True) if link.parent else ""
            volume = re.search(r"\(([\d,]+)\+?\)", text)
            if re.fullmatch(r"/used-cars/[a-z0-9-]+/\d+", path) and volume:
                models[path] = int(volume[1].replace(",", ""))
    if len(models) < count:
        raise ParseError("Model-volume links are missing; cannot select crawl scope")
    return tuple(sorted(models, key=lambda path: (-models[path], path))[:count])


class PakWheelsAdapter:
    """PakWheels implementation of the source adapter protocol."""

    parse_list_page = staticmethod(parse_list_page)
    parse_detail_page = staticmethod(parse_detail_page)

    def iter_listing_pages(self, filters: ScrapeFilters) -> Iterator[str]:
        paths = filters.model_paths or ("/used-cars/search/-/",)
        for path in paths:
            if path != "/used-cars/search/-/" and not re.fullmatch(
                r"/used-cars/[a-z0-9-]+/\d+", path
            ):
                raise ValueError("Model paths must be public PakWheels search paths")
        # Round-robin by page so small budgets sample different models.
        for page in range(1, filters.limit_pages + 1):
            path = paths[(page - 1) % len(paths)]
            number = (page - 1) // len(paths) + 1
            yield BASE_URL + path + (f"?page={number}" if number > 1 else "")
