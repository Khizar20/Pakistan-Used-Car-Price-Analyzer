"""Generated JSON Schema/TypeScript parity and strict public boundaries."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from tracker.export.schema import (
    CONTRACTS,
    Metadata,
    PredictionSpec,
    Residual,
    _mapping,
    _ts_type,
    contract_artifacts,
)

ROOT = Path(__file__).resolve().parents[2]


def test_all_contracts_generate_valid_schemas_and_types_without_drift():
    artifacts = contract_artifacts()
    assert len(CONTRACTS) == 8 and len(artifacts) == 9
    assert artifacts == contract_artifacts()
    for filename, model in CONTRACTS.items():
        schema = json.loads(artifacts[filename.replace(".json", ".schema.json")])
        Draft202012Validator.check_schema(schema)
        assert schema["properties"]["schema_version"]["const"] == "1.0.0"
        assert schema["additionalProperties"] is False
        assert f"export type {model.__name__} =" in artifacts["contracts.ts"]
        for definition in schema.get("$defs", {}).values():
            fields = definition.get("properties", {})
            assert (
                not {"listing_id", "source_listing_id", "name", "names", "url"}
                & fields.keys()
            )
    for filename, contents in artifacts.items():
        assert (ROOT / "web/src/types" / filename).read_text(
            encoding="utf-8"
        ) == contents


def test_public_models_reject_unknown_fields_nonfinite_values_and_raw_ids():
    with pytest.raises(ValidationError):
        Metadata.model_validate({"seller_name": "Private"})
    residual = dict(
        listing_hash="a" * 64,
        make="Honda",
        fitted_pkr=100.0,
        actual_pkr=90.0,
        residual_pkr=-10.0,
        residual_log=-0.1,
    )
    Residual.model_validate(residual)
    with pytest.raises(ValidationError):
        Residual.model_validate({**residual, "listing_hash": "900001"})
    with pytest.raises(ValidationError):
        Residual.model_validate({**residual, "residual_log": float("nan")})
    with pytest.raises(ValidationError):
        PredictionSpec(numeric=["unknown"], categories={}, terms=[])


@pytest.mark.parametrize(
    "node,expected",
    [
        ({"type": "boolean"}, "boolean"),
        ({"type": "null"}, "null"),
        (
            {"type": "object", "properties": {"x": {"type": "string"}}},
            '{ "x"?: string; }',
        ),
        (
            {"type": "array", "prefixItems": [{"type": "integer"}, {"type": "number"}]},
            "[number, number]",
        ),
    ],
)
def test_schema_translation_handles_emitted_json_shapes(node, expected):
    assert _ts_type(node, "Prefix_") == expected


@pytest.mark.parametrize(
    "node", [{}, {"$ref": "https://invalid/schema"}, {"type": "object"}]
)
def test_unknown_schema_shapes_fail_closed(node):
    with pytest.raises(ValueError):
        _ts_type(node, "Prefix_")
    with pytest.raises(ValueError):
        _mapping([])
