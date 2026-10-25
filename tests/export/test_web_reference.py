"""Stored synthetic browser fixtures still agree with Python and public schemas."""

import json
from pathlib import Path

import pandas as pd
import pytest

from tracker.analysis.drivers import FairPriceModel, predict_fair_price
from tracker.export.schema import CONTRACTS
from tracker.export.writer import assert_public

FIXTURES = Path(__file__).parents[2] / "web/tests/fixtures"


def test_all_synthetic_browser_exports_validate_and_have_one_identity() -> None:
    identities = set()
    for filename, model in CONTRACTS.items():
        parsed = model.model_validate_json((FIXTURES / filename).read_text())
        assert_public(parsed.model_dump(mode="json"))
        identities.add((parsed.bundle_id, parsed.generated_at))
    assert len(identities) == 1


def test_twenty_browser_references_reproduce_python_predictions() -> None:
    assert b"\r\n" not in (FIXTURES / "fair-reference.json").read_bytes()
    payload = json.loads((FIXTURES / "fair-reference.json").read_text())
    public = payload["model"]
    model = FairPriceModel.model_validate(
        {
            **public,
            "spec": {
                "numeric": public["spec"]["numeric"],
                "categories": public["spec"]["categories"],
                "names": public["spec"]["terms"],
            },
        }
    )
    references = payload["references"]
    assert len(references) == 20
    results = predict_fair_price(pd.DataFrame(row["car"] for row in references), model)
    for row, prediction in zip(references, results, strict=True):
        assert prediction.estimate_pkr == pytest.approx(row["estimate_pkr"], rel=1e-12)
        assert prediction.lower_pkr == pytest.approx(row["lower_pkr"], rel=1e-12)
        assert prediction.upper_pkr == pytest.approx(row["upper_pkr"], rel=1e-12)
