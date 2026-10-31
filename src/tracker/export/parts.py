"""Lossless city-cohort partitioning within the public per-file size budget."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import cast

from tracker.export.schema import MAX_FILE_BYTES, CityPricesPartExport


def encode(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def partition_models(payload: dict[str, object]) -> dict[str, bytes]:
    """Keep all cohorts in immutable, independently validated envelopes."""
    data = cast(dict[str, object], payload["data"])
    rows = cast(list[object], data["city_prices"])
    result: dict[str, bytes] = {}
    hashes: list[str] = []

    def append(batch: list[object]) -> None:
        part = CityPricesPartExport.model_validate(
            {
                **{key: value for key, value in payload.items() if key != "data"},
                "data": batch,
            }
        )
        content = encode(part.model_dump(mode="json"))
        if len(content) >= MAX_FILE_BYTES:
            if len(batch) <= 1:
                raise ValueError("A city cohort exceeds the public file budget")
            midpoint = len(batch) // 2
            append(batch[:midpoint])
            append(batch[midpoint:])
            return
        digest = hashlib.sha256(content).hexdigest()
        hashes.append(digest)
        result[f"models-cities-{digest}.json"] = content

    for start in range(0, len(rows), 256):
        append(rows[start : start + 256])
    # model_dump produced this private copy; caller model objects remain unchanged.
    data["city_prices"] = []
    data["city_price_parts"] = hashes
    content = encode(payload)
    if len(content) >= MAX_FILE_BYTES:
        raise ValueError("Model summaries exceed the public file budget")
    result["models.json"] = content
    return result


def prune_parts(output: Path, current: set[str], previous: bytes | None) -> None:
    """Retain current and previous generations, including in-flight readers."""
    keep = set(current)
    if previous:
        try:
            old = json.loads(previous)["data"].get("city_price_parts", [])
            if not isinstance(old, list) or any(
                not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
                for value in old
            ):
                return
            keep.update(f"models-cities-{value}.json" for value in old)
        except (ValueError, TypeError, KeyError, AttributeError):
            return
    for path in output.glob("models-cities-*.json"):
        if path.name not in keep and re.fullmatch(
            r"models-cities-[a-f0-9]{64}\.json", path.name
        ):
            try:
                path.unlink()
            except OSError:
                # A locked old artifact must not invalidate a successful publication.
                continue
