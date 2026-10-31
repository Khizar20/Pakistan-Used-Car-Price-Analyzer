"""Image ingestion uses invented, anonymous artwork and mocked downloads."""

import gzip
import hashlib
import io
import json
import sqlite3

import httpx
import pytest
from PIL import Image

from tests.unit.test_http import client
from tracker.models import RawListing
from tracker.photos import collect_photos, image_extension, publish_photo
from tracker.scraping.http import AccessBlockedError
from tracker.scraping.markup import sanitize_html
from tracker.scraping.pakwheels import parse_list_page

PHOTO = "https://cache1.pakwheels.com/ad_pictures/123/tn_honda-civic-2020-123.webp"


def artwork():
    output = io.BytesIO()
    Image.new("RGB", (160, 120), "green").save(output, format="WEBP")
    return output.getvalue()


def test_only_vehicle_thumbnail_reference_survives_sanitizing():
    html = (
        f'<li class="classified-listing"><img src="{PHOTO}" alt="Private seller">'
        '<img src="https://example.com/seller.jpg"></li>'
    )
    safe = sanitize_html(html)
    assert PHOTO in safe and "Private seller" not in safe and "seller.jpg" not in safe
    listing = RawListing(
        source_listing_id="1",
        url="https://www.pakwheels.com/used-cars/honda-civic-for-sale-in-karachi-1",
        photo=PHOTO,
    )
    assert listing.photo == PHOTO
    with pytest.raises(ValueError):
        listing.model_validate(
            {**listing.model_dump(), "photo": "https://example.com/seller.jpg"}
        )


def test_observed_thumbnail_is_parsed_from_anonymous_listing_fixture():
    from pathlib import Path

    fixture = Path(__file__).parents[1] / "fixtures/html/pakwheels_list.html"
    # Preserve the real card selector while introducing only a fictitious photo URL.
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(fixture.read_text(encoding="utf-8"), "html.parser")
    soup.select_one("li.classified-listing").append(soup.new_tag("img", src=PHOTO))
    assert parse_list_page(sanitize_html(str(soup)))[0].photo == PHOTO


def test_thumbnail_requests_respect_robots_and_validate_response(tmp_path):
    content = artwork()
    requests = []

    def handler(request):
        requests.append(request.url.path)
        return (
            httpx.Response(200, text="User-agent: *\nAllow: /")
            if request.url.path == "/robots.txt"
            else httpx.Response(
                200, content=content, headers={"content-type": "image/webp"}
            )
        )

    with client(tmp_path, handler) as http:
        assert http.get_photo(PHOTO) == content
        with pytest.raises(ValueError):
            http.get_photo("https://example.com/a.webp")
    assert requests[0] == "/robots.txt"
    with client(tmp_path, lambda _: httpx.Response(403)) as http:
        with pytest.raises(AccessBlockedError):
            http.get_photo(PHOTO)


def test_compressed_thumbnail_is_decoded_once(tmp_path):
    content = artwork()

    def handler(request):
        return (
            httpx.Response(404)
            if request.url.path == "/robots.txt"
            else httpx.Response(
                200,
                content=gzip.compress(content, mtime=0),
                headers={"content-type": "image/webp", "content-encoding": "gzip"},
            )
        )

    with client(tmp_path, handler) as http:
        assert http.get_photo(PHOTO) == content


@pytest.mark.parametrize(
    "status,kind,body,error",
    [
        (403, "image/webp", b"", AccessBlockedError),
        (302, "image/webp", b"", AccessBlockedError),
        (200, "text/html", b"not an image", ValueError),
        (200, "image/webp", b"x" * 2_000_001, ValueError),
    ],
    ids=["denied", "redirect", "html", "oversized"],
)
def test_bad_thumbnails_stop(tmp_path, status, kind, body, error):
    def handler(request):
        return (
            httpx.Response(404)
            if request.url.path == "/robots.txt"
            else httpx.Response(status, content=body, headers={"content-type": kind})
        )

    with client(tmp_path, handler) as http:
        with pytest.raises(error):
            http.get_photo(PHOTO)


def test_private_collection_and_reviewed_publication(tmp_path):
    (tmp_path / "data").mkdir()
    with sqlite3.connect(tmp_path / "data/tracker.sqlite3") as db:
        db.execute(
            "CREATE TABLE raw_vehicles(attributes TEXT, last_seen_at TEXT, "
            "source_listing_id TEXT)"
        )
        for record in [
            {},
            {"make": "Honda", "model": "Civic", "photo": PHOTO, "model_year": 2020},
        ] * 2:
            db.execute(
                "INSERT INTO raw_vehicles VALUES (?, '2026-10-25', '1')",
                (json.dumps(record),),
            )
    content = artwork()

    def handler(request):
        return (
            httpx.Response(404)
            if request.url.path == "/robots.txt"
            else httpx.Response(
                200, content=content, headers={"content-type": "image/webp"}
            )
        )

    with client(tmp_path / "cache", handler) as http:
        assert collect_photos(tmp_path, http) == 1
        assert collect_photos(tmp_path, http, limit=1) == 0
        with pytest.raises(ValueError):
            collect_photos(tmp_path, http, limit=0)
    assert not (tmp_path / "web/public").exists()
    digest = hashlib.sha256(content).hexdigest()
    filename = publish_photo(tmp_path, digest)
    assert (tmp_path / "web/public/images/cars" / filename).read_bytes() == content
    catalog = (tmp_path / "web/src/data/carPhotos.json").read_text()
    assert PHOTO not in catalog and "Honda / Civic" in catalog
    publish_photo(tmp_path, digest)
    with pytest.raises(ValueError):
        publish_photo(tmp_path, "../escape")
    (tmp_path / "raw/photos" / filename).write_bytes(content + b"changed")
    with pytest.raises(ValueError):
        publish_photo(tmp_path, digest)


@pytest.mark.parametrize("size,format", [((1, 1), "PNG"), ((100, 100), "GIF")])
def test_invalid_dimensions_and_formats(size, format):
    output = io.BytesIO()
    Image.new("RGB", size).save(output, format=format)
    with pytest.raises(ValueError):
        image_extension(output.getvalue())


def test_metadata_and_oversized_images_are_rejected():
    image = Image.new("RGB", (100, 100))
    exif = image.getexif()
    exif[270] = "private description"
    output = io.BytesIO()
    image.save(output, format="JPEG", exif=exif)
    with pytest.raises(ValueError, match="metadata"):
        image_extension(output.getvalue())
    with pytest.raises(ValueError, match="budget"):
        image_extension(b"x" * 2_000_001)
