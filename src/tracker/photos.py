"""Source thumbnails stay private until visual review approves a model reference."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from pathlib import Path

from PIL import Image

from tracker.scraping.http import PoliteClient


def image_extension(content: bytes) -> str:
    """Check file decoding, dimensions and metadata without modifying its pixels."""
    if len(content) > 2_000_000:
        raise ValueError("Image exceeds size budget")
    with Image.open(io.BytesIO(content)) as image:
        if image.format not in {"WEBP", "JPEG", "PNG"}:
            raise ValueError("Unsupported photo format")
        if not 80 <= image.width <= 2000 or not 60 <= image.height <= 2000:
            raise ValueError("Unexpected thumbnail dimensions")
        if image.getexif() or any(
            key in image.info for key in ("exif", "xmp", "comment")
        ):
            raise ValueError("Review requires a photo without embedded metadata")
        extension = {"WEBP": "webp", "JPEG": "jpg", "PNG": "png"}[image.format]
        image.verify()
    return extension


def collect_photos(root: Path, client: PoliteClient, *, limit: int = 12) -> int:
    """Queue one observed photo per model; never publish unchecked image contents."""
    if not 1 <= limit <= 30:
        raise ValueError("Photo batch must contain 1 to 30 models")
    root = root.resolve(strict=True)
    database = root / "data/tracker.sqlite3"
    with sqlite3.connect(
        database.resolve(strict=True).as_uri() + "?mode=ro", uri=True
    ) as connection:
        records = connection.execute(
            "SELECT attributes FROM raw_vehicles "
            "ORDER BY last_seen_at DESC, source_listing_id"
        ).fetchall()
    destination = root / "raw/photos"
    destination.mkdir(parents=True, exist_ok=True)
    catalog_path = destination / "candidates.json"
    catalog = (
        json.loads(catalog_path.read_text(encoding="utf-8"))
        if catalog_path.exists()
        else {}
    )
    seen: set[str] = set()
    added = 0
    for (payload,) in records:
        record = json.loads(payload)
        if not all(record.get(key) for key in ("make", "model", "photo")):
            continue
        key = f"{record['make']} / {record['model']}"
        if key in seen:
            continue
        seen.add(key)
        source_hash = hashlib.sha256(str(record["photo"]).encode()).hexdigest()
        if any(item.get("car") == key for item in catalog.values()):
            continue
        content = client.get_photo(record["photo"])
        extension = image_extension(content)
        digest = hashlib.sha256(content).hexdigest()
        filename = f"{digest}.{extension}"
        (destination / filename).write_bytes(content)
        catalog[digest] = {
            "car": key,
            "file": filename,
            "year": record.get("model_year"),
            "source_hash": source_hash,
        }
        catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
        added += 1
        if added == limit:
            break
    return added


def publish_photo(root: Path, digest: str) -> str:
    """Publish a visually reviewed file by hash; source references remain private."""
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("Expected a SHA256 image identifier")
    root = root.resolve(strict=True)
    private = root / "raw/photos"
    candidate = json.loads((private / "candidates.json").read_text(encoding="utf-8"))[
        digest
    ]
    filename = str(candidate["file"])
    source = (private / filename).resolve(strict=True)
    if source.parent != private.resolve():
        raise ValueError("Candidate must be within the review directory")
    content = source.read_bytes()
    extension = image_extension(content)
    if (
        hashlib.sha256(content).hexdigest() != digest
        or filename != f"{digest}.{extension}"
    ):
        raise ValueError("Reviewed image content changed")
    public = root / "web/public/images/cars"
    public.mkdir(parents=True, exist_ok=True)
    (public / filename).write_bytes(content)
    catalog_path = root / "web/src/data/carPhotos.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog = (
        json.loads(catalog_path.read_text(encoding="utf-8"))
        if catalog_path.exists()
        else {}
    )
    catalog[candidate["car"]] = {
        "path": f"images/cars/{filename}",
        "year": candidate["year"],
    }
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    return filename
