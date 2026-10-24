"""Retain only the observed vehicle markup needed by the PakWheels adapter."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import cast

from bs4 import BeautifulSoup, Tag

SCHEMA_FIELDS = {
    "@context",
    "@type",
    "brand",
    "model",
    "modelDate",
    "manufacturer",
    "fuelType",
    "vehicleTransmission",
    "color",
    "bodyType",
    "vehicleEngine",
    "mileageFromOdometer",
    "offers",
    "name",
}
EVENT_FIELDS = {"item_category2", "item_category3", "item_category4", "city"}


def object_dict(value: object) -> dict[str, object]:
    """Narrow untrusted JSON to an object with string keys."""
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def load_object(text: str) -> dict[str, object]:
    try:
        value: object = json.loads(text)
    except (ValueError, TypeError):
        return {}
    return object_dict(value)


def clean_schema(data: Mapping[str, object]) -> dict[str, object]:
    """Drop free-text descriptions, images, sellers, and arbitrary JSON keys."""
    result = {key: value for key, value in data.items() if key in SCHEMA_FIELDS}
    for key, fields in {
        "brand": {"@type", "name"},
        "vehicleEngine": {"@type", "engineDisplacement"},
        "offers": {"@type", "price", "priceCurrency", "availability", "url"},
    }.items():
        if key in result:
            result[key] = {
                name: value
                for name, value in object_dict(result[key]).items()
                if name in fields
            }
    return result


def sanitize_html(html: str) -> str:
    """Build a small cache document without descriptions or seller/contact UI."""
    source = BeautifulSoup(html, "html.parser")
    output = BeautifulSoup(
        "<!doctype html><html><head></head><body></body></html>", "html.parser"
    )
    head = cast(Tag, output.head)
    body = cast(Tag, output.body)
    canonical = source.select_one('link[rel="canonical"]')
    if canonical:
        head.append(canonical)
    for heading in source.select(".related_searches h3"):
        if heading.get_text(strip=True) == "View Cars by Model":
            group = heading.find_next_sibling("ul")
            if group:
                container = output.new_tag("div", attrs={"class": "related_searches"})
                container.append(heading)
                container.append(group)
                body.append(container)
    # Preserve the actual card structure but only selected vehicle subtrees.
    for card in source.select("li.classified-listing"):
        saved = output.new_tag("li")
        saved.attrs = {
            key: value
            for key, value in card.attrs.items()
            if key in {"class", "data-listing-id"}
        }
        for selector in (
            'script[type="application/ld+json"]',
            ".car-name",
            ".price-details",
            ".search-vehicle-info",
            ".search-vehicle-info-2",
            ".total-pictures-bar",
        ):
            node = card.select_one(selector)
            if node:
                saved.append(node)
        event = card.select_one("[data-ga4-event]")
        if event:
            metadata = load_object(str(event.get("data-ga4-event", "")))
            button = output.new_tag("button")
            button["data-ga4-event"] = json.dumps(
                {key: value for key, value in metadata.items() if key in EVENT_FIELDS}
            )
            saved.append(button)
        price = card.select_one("[data-price]")
        if price:
            numeric = output.new_tag("span")
            numeric["data-price"] = str(price.get("data-price", ""))
            saved.append(numeric)
        body.append(saved)
    # Detail schema can include related cars: preserve all, match canonical later.
    for node in source.select('script[type="application/ld+json"]'):
        data = load_object(node.get_text())
        if data.get("@type") == ["Product"] or data.get("@type") == "Product":
            body.append(node)
    for selector in (
        "h1",
        ".breadcrumb",
        "#scroll_car_detail",
        ".car-feature-list",
        ".price-box strong,strong.generic-green",
    ):
        for node in source.select(selector):
            body.append(node)
    for node in output.select("script"):
        node.string = json.dumps(
            clean_schema(load_object(node.get_text())), ensure_ascii=False
        )
    for element in list(output.find_all(True)):
        if not isinstance(element, Tag):
            continue
        if element.name == "img":
            element.decompose()
            continue
        element.attrs = {
            key: value
            for key, value in element.attrs.items()
            if key
            in {
                "class",
                "id",
                "href",
                "rel",
                "type",
                "data-listing-id",
                "data-ga4-event",
                "data-price",
            }
        }
    # Parse-only documents are deliberately not rendered as pages.
    return str(output)


def anonymize_fixture(html: str) -> str:
    """Replace source listing identifiers consistently in a minimized fixture."""
    ids = sorted(
        set(re.findall(r"(?:for-sale-in-[a-z-]+-|data-listing-id=\")(\d{5,})", html))
    )
    for index, listing_id in enumerate(ids, start=1):
        html = html.replace(listing_id, str(900000 + index))
    return html
