"""Large city comparisons retain every cohort in bounded, immutable parts."""

import hashlib
import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from tracker.export.parts import partition_models, prune_parts
from tracker.export.schema import MAX_FILE_BYTES, CityPricesPartExport
from tracker.export.writer import build_exports, serialize_exports, write_exports


def large_exports():
    exports = build_exports(
        pd.DataFrame(), generated_at=datetime(2026, 10, 25, tzinfo=timezone.utc)
    )
    data = exports["models.json"].data.model_dump(mode="json")
    data["city_prices"] = [
        {
            "make": "Honda",
            "model": f"Example {i}",
            "city": "Karachi",
            "model_year": 2020,
            "transmission": "automatic",
            "listing_count": 5,
            "priced_listing_count": 5,
            "median_price_pkr": 2000000,
            "lower_quartile_pkr": 1900000,
            "upper_quartile_pkr": 2100000,
            "median_mileage_km": 30000,
            "observed_through": "2026-10-25",
            "status": "ok",
        }
        for i in range(2000)
    ]
    exports["models.json"] = exports["models.json"].model_validate(
        {**exports["models.json"].model_dump(mode="json"), "data": data}
    )
    # A logical digest always covers the full eight data bodies, before partitioning.
    content = {
        key: model.model_dump(mode="json")["data"] for key, model in exports.items()
    }
    digest = hashlib.sha256(
        json.dumps(content, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    return {
        key: model.model_copy(update={"bundle_id": digest})
        for key, model in exports.items()
    }


def test_large_models_round_trip_without_dropping_or_changing_cohorts(tmp_path):
    exports = large_exports()
    original = exports["models.json"].model_dump(mode="json")
    files = serialize_exports(exports)
    manifest = json.loads(files["models.json"])
    assert manifest["data"]["city_prices"] == []
    assert len(manifest["data"]["city_price_parts"]) == 8
    rows = []
    for digest in manifest["data"]["city_price_parts"]:
        content = files[f"models-cities-{digest}.json"]
        assert hashlib.sha256(content).hexdigest() == digest
        part = CityPricesPartExport.model_validate_json(content)
        assert part.bundle_id == manifest["bundle_id"]
        rows.extend(part.model_dump(mode="json")["data"])
    assert rows == original["data"]["city_prices"]
    assert all(len(content) < MAX_FILE_BYTES for content in files.values())
    assert exports["models.json"].model_dump(mode="json") == original
    assert serialize_exports(exports) == files
    write_exports(exports, output=tmp_path / "data", types_directory=tmp_path / "types")
    assert (tmp_path / "data/models.json").read_bytes() == files["models.json"]


def test_oversized_rows_split_recursively_and_single_row_fails():
    payload = large_exports()["models.json"].model_dump(mode="json")
    for row in payload["data"]["city_prices"]:
        row["model"] = "x" * 3000
    files = partition_models(payload)
    assert all(len(content) < MAX_FILE_BYTES for content in files.values())
    payload["data"]["city_prices"] = [
        {
            **json.loads(
                next(value for key, value in files.items() if key != "models.json")
            )["data"][0],
            "model": "x" * MAX_FILE_BYTES,
        }
    ]
    with pytest.raises(ValueError, match="cohort"):
        partition_models(payload)
    payload["data"]["city_prices"] = []
    payload["data"]["reason"] = "x" * MAX_FILE_BYTES
    with pytest.raises(ValueError, match="summaries"):
        partition_models(payload)


def test_pruning_preserves_readers_manual_files_and_corrupt_previous_state(
    tmp_path, monkeypatch
):
    current = f"models-cities-{'a' * 64}.json"
    previous = f"models-cities-{'b' * 64}.json"
    obsolete = f"models-cities-{'c' * 64}.json"
    for filename in (current, previous, obsolete, "models-cities-manual.json"):
        (tmp_path / filename).write_text("{}")
    for value in (b"bad", b"{}", b'{"data":{"city_price_parts":["../unsafe"]}}'):
        prune_parts(tmp_path, {current}, value)
        assert (tmp_path / obsolete).exists()
    old = json.dumps({"data": {"city_price_parts": ["b" * 64]}}).encode()
    prune_parts(tmp_path, {current}, old)
    assert not (tmp_path / obsolete).exists()
    assert (tmp_path / previous).exists() and (tmp_path / current).exists()
    assert (tmp_path / "models-cities-manual.json").exists()
    (tmp_path / obsolete).touch()

    def locked(_):
        raise PermissionError("locked")

    monkeypatch.setattr("pathlib.Path.unlink", locked)
    prune_parts(tmp_path, {current}, old)
    assert (tmp_path / obsolete).exists()


def test_failed_part_publication_rolls_back_new_parts_and_prior_files(
    tmp_path, monkeypatch
):
    import os

    exports = build_exports(
        pd.DataFrame(), generated_at=datetime(2026, 10, 25, tzinfo=timezone.utc)
    )
    output, types = tmp_path / "data", tmp_path / "types"
    write_exports(exports, output=output, types_directory=types)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    replace = os.replace
    calls = 0

    def fail_part(source, target):
        nonlocal calls
        calls += 1
        if calls == 8:
            raise OSError("part publication interrupted")
        return replace(source, target)

    monkeypatch.setattr("tracker.export.writer.os.replace", fail_part)
    with pytest.raises(OSError, match="interrupted"):
        write_exports(large_exports(), output=output, types_directory=types)
    assert {
        path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()
    } == before


def test_prepartitioned_inputs_cannot_publish_missing_parts():
    exports = large_exports()
    root = json.loads(serialize_exports(exports)["models.json"])
    exports["models.json"] = exports["models.json"].model_validate(root)
    with pytest.raises(ValueError, match="unpartitioned"):
        serialize_exports(exports)
