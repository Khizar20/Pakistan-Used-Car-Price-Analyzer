"""Fixed-DB snapshots, all schemas, privacy budgets and recoverable file writes."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from typer.testing import CliRunner

from tests.analysis.synthetic import market
from tests.integration.test_scrape import NOW, Source
from tests.integration.test_storage_pipeline import collect
from tracker.analysis.common import DesignSpec
from tracker.analysis.drivers import FairPriceModel, predict_fair_price
from tracker.analysis.runner import load_observations
from tracker.cli import app
from tracker.export.schema import CONTRACTS, MAX_FILE_BYTES, Envelope
from tracker.export.writer import (
    assert_public,
    build_exports,
    public_hash,
    serialize_exports,
    write_exports,
)
from tracker.storage.repo import Repository

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/export"


def fixture_frame(directory: Path) -> pd.DataFrame:
    path = directory / "tracker.sqlite3"
    source = Source()
    collect(source, path, directory / "cache1")
    source.html = source.html.replace('"price": 5900000', '"price": 5800000').replace(
        "PKR 59", "PKR 58"
    )
    collect(source, path, directory / "cache2", 1)
    return load_observations(path)


def validate_all(exports: dict[str, Envelope]) -> dict[str, bytes]:
    payloads = serialize_exports(exports)
    for filename, model in CONTRACTS.items():
        payload = json.loads(payloads[filename])
        model.model_validate(payload)
        Draft202012Validator(
            model.model_json_schema(mode="serialization"),
            format_checker=FormatChecker(),
        ).validate(payload)
        assert len(payloads[filename]) < MAX_FILE_BYTES
        assert_public(payload)
    return payloads


def test_fixed_database_matches_all_eight_snapshots_and_public_projection(tmp_path):
    frame = fixture_frame(tmp_path)
    exports = build_exports(frame, generated_at=NOW)
    payloads = validate_all(exports)
    for filename, payload in payloads.items():
        assert payload == (FIXTURES / filename).read_bytes()
    meta = json.loads(payloads["meta.json"])["data"]
    assert meta["listing_count"] == 1 and meta["observation_count"] == 2
    assert meta["run_count"] == 2 and meta["scope_count"] == 1
    drop = json.loads(payloads["listings_sample.json"])["data"]["rows"][0]
    assert drop["listing_hash"] == public_hash("1")
    assert drop["drop_pkr"] == 100000 and drop["city"] == "Karachi"
    assert (
        not {"seller_type", "listing_id", "source_listing_id", "name", "url"}
        & drop.keys()
    )
    assert (
        json.loads(payloads["models.json"])["data"]["models"][0]["median_price_pkr"]
        == 5800000
    )
    assert exports == build_exports(frame.iloc[::-1], generated_at=NOW)


@pytest.fixture(scope="module")
def fitted_exports():
    frame = market(240, 3)
    return frame, build_exports(frame, generated_at=NOW)


def test_supported_models_schemas_caps_and_portable_prediction_parity(fitted_exports):
    frame, exports = fitted_exports
    payloads = validate_all(exports)
    drivers = json.loads(payloads["drivers.json"])["data"]
    assert drivers["status"] == "ok" and len(drivers["diagnostics"]) == 200
    assert drivers["diagnostics_total"] == 240
    sample = json.loads(payloads["listings_sample.json"])["data"]
    assert sample["total_events"] > len(sample["rows"]) == 100
    assert sample["rows"] == sorted(
        sample["rows"],
        key=lambda row: (row["observed_at"], row["listing_hash"]),
        reverse=True,
    )
    fair = json.loads(payloads["fairprice.json"])["data"]["model"]
    spec = fair.pop("spec")
    private = FairPriceModel.model_validate(
        {
            **fair,
            "spec": DesignSpec(
                numeric=spec["numeric"],
                categories=spec["categories"],
                names=spec["terms"],
            ),
        }
    )
    cars = frame.drop_duplicates("listing_id", keep="last").iloc[:20].copy()
    expected = predict_fair_price(cars, private)
    # Independently evaluate the published transformations/encoding contract.
    for row, prediction in zip(cars.to_dict("records"), expected, strict=True):
        for key, value in fair["defaults"].items():
            row.setdefault(key, value)
        row["make_model"] = row["make"] + " / " + row["model"]
        values = {
            "intercept": 1.0,
            "model_year": row["model_year"] - 2000,
            "log_mileage": np.log1p(row["mileage_km"]),
            "engine_litres": row["engine_cc"] / 1000,
        }
        for column, levels in spec["categories"].items():
            for level in levels[1:]:
                values[column + "=" + level] = float(str(row[column]) == level)
        predicted = np.exp(
            sum(values[term] * fair["coefficients"][term] for term in spec["terms"])
        )
        assert predicted == pytest.approx(prediction.estimate_pkr, rel=1e-12)


def test_extra_private_columns_do_not_enter_export_and_contact_labels_fail(tmp_path):
    frame = fixture_frame(tmp_path)
    baseline = serialize_exports(build_exports(frame, generated_at=NOW))
    for key in ("seller_name", "email", "phone", "address", "url"):
        frame[key] = "private@example.invalid"
    assert serialize_exports(build_exports(frame, generated_at=NOW)) == baseline
    frame["city"] = "private@example.invalid"
    with pytest.raises(ValueError, match="contact detail"):
        build_exports(frame, generated_at=NOW)


@pytest.mark.parametrize(
    "value",
    [
        {"seller_name": "Private"},
        {"phone_number": "hidden"},
        {"listing_id": "1"},
        {"nested": [{"label": "+92 300 1234567"}]},
        {"city": "0300-1234567"},
        {"label": "https://example.invalid/vehicle"},
        {"label": "www.example.invalid"},
        {"label": "contact@example.invalid"},
        {"label": "+1 212 555 0100"},
        {"phone": "hidden"},
        {"sellerName": "Private"},
        {"label": "021 12345678"},
        {"private@example.invalid": "hidden"},
        {"email": "hidden"},
        {"address": "hidden"},
    ],
)
def test_privacy_scan_rejects_sensitive_keys_and_contact_patterns(value):
    with pytest.raises(ValueError, match="Public export contains"):
        assert_public(value)


def test_valid_labels_dates_numbers_and_digest_are_not_misclassified():
    # Oversized benign text must not trigger pathological regex backtracking.
    assert_public("x" * MAX_FILE_BYTES)
    assert_public(
        {
            "listing_hash": "a" * 20 + "03001234567" + "b" * 33,
            "observed_at": "2026-10-24T00:00:00+00:00",
            "model_year": 2024,
            "price_pkr": 5900000,
            "model": "Suzuki 800",
        }
    )


def test_empty_and_inactive_models_are_honest_and_invalid_inputs_fail(tmp_path):
    path = tmp_path / "empty.sqlite3"
    with Repository.open(path):
        pass
    exports = build_exports(load_observations(path), generated_at=NOW)
    validate_all(exports)
    assert exports["meta.json"].model_dump()["data"]["listing_count"] == 0
    for filename in set(exports) - {"meta.json"}:
        assert exports[filename].model_dump()["data"]["status"] == "insufficient_data"
    frame = market(6, 1)
    frame["is_active"] = False
    assert (
        build_exports(frame, generated_at=NOW)["models.json"].model_dump()["data"][
            "models"
        ]
        == []
    )
    frame.loc[0, "observed_at"] = pd.NaT
    with pytest.raises(ValueError, match="Invalid observation"):
        build_exports(frame, generated_at=NOW)


def test_model_counts_use_latest_active_unique_cars_and_usable_prices():
    frame = market(8, 2)
    identities = frame.listing_id.unique()
    frame.loc[frame.listing_id.eq(identities[0]), "duplicate_of"] = "other"
    frame.loc[frame.listing_id.eq(identities[1]), "is_active"] = False
    for index in frame.index[frame.listing_id.eq(identities[2])]:
        frame.at[index, "quality_flag"] = ["placeholder_price"]
    exports = build_exports(frame, generated_at=NOW)
    models = exports["models.json"].model_dump()["data"]["models"]
    assert sum(model["listing_count"] for model in models) == 6
    assert sum(model["priced_listing_count"] for model in models) == 5


def test_missing_vehicle_attributes_remain_nullable_in_observed_drop_rows():
    frame = market(8, 2)
    for column in ("make", "model", "model_year", "city"):
        frame[column] = None
    exports = build_exports(frame, generated_at=NOW)
    payloads = validate_all(exports)
    assert json.loads(payloads["models.json"])["data"]["models"] == []
    rows = json.loads(payloads["listings_sample.json"])["data"]["rows"]
    assert rows and all(
        row["make"] is None and row["model_year"] is None for row in rows
    )


def test_preflight_rejects_incomplete_mixed_changed_and_oversized_bundles(tmp_path):
    exports = build_exports(pd.DataFrame(), generated_at=NOW)
    with pytest.raises(ValueError, match="exactly the eight"):
        serialize_exports({"meta.json": exports["meta.json"]})
    mixed = {
        **exports,
        "meta.json": exports["meta.json"].model_copy(update={"bundle_id": "a" * 64}),
    }
    with pytest.raises(ValueError, match="Mixed export"):
        serialize_exports(mixed)
    changed = {key: model.model_copy(deep=True) for key, model in exports.items()}
    changed["meta.json"].data.caveats.append("Changed content")
    with pytest.raises(ValueError, match="content digest"):
        serialize_exports(changed)
    changed["meta.json"].data.caveats.append("x" * MAX_FILE_BYTES)
    with pytest.raises(ValueError, match="file budget"):
        write_exports(
            changed, output=tmp_path / "data", types_directory=tmp_path / "types"
        )
    assert not (tmp_path / "data").exists()
    with pytest.raises(ValueError, match="must differ"):
        write_exports(exports, output=tmp_path, types_directory=tmp_path)


@pytest.mark.parametrize("existing", [True, False])
def test_failed_publish_restores_previous_files_and_cleans_staging(
    tmp_path, monkeypatch, existing
):
    exports = build_exports(pd.DataFrame(), generated_at=NOW)
    output, types = tmp_path / "data", tmp_path / "types"
    if existing:
        write_exports(exports, output=output, types_directory=types)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    replace = os.replace
    calls = 0

    def fail_once(source, target):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("injected write failure")
        return replace(source, target)

    monkeypatch.setattr("tracker.export.writer.os.replace", fail_once)
    with pytest.raises(OSError, match="injected"):
        write_exports(exports, output=output, types_directory=types)
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    assert not list(tmp_path.rglob(".tracker-*"))


def test_cli_default_outputs_repeated_export_and_missing_database(
    tmp_path, monkeypatch
):
    frame = fixture_frame(tmp_path)
    assert len(frame) == 2
    path = tmp_path / "tracker.sqlite3"
    before = path.read_bytes()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("tracker.cli._now", lambda: NOW)
    for _ in range(2):
        result = CliRunner().invoke(app, ["export", "--database", str(path)])
        assert result.exit_code == 0, result.output
    assert len(list((tmp_path / "web/public/data").glob("*.json"))) == 8
    assert len(list((tmp_path / "web/src/types").glob("*"))) == 10
    assert path.read_bytes() == before
    result = CliRunner().invoke(app, ["export", "--database", "missing.sqlite3"])
    assert result.exit_code == 1 and "Export failed" in result.output
    assert not (tmp_path / "missing.sqlite3").exists()
