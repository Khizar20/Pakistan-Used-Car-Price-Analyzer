"""Validation, typed design contract and known log-linear coefficients."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from tests.analysis.synthetic import market
from tracker.analysis.common import (
    DesignSpec,
    design,
    design_spec,
    fit_linear,
    model_rows,
    prepare,
)

REQUIRED = ["listing_id", "observed_at", "price_pkr"]


def test_prepare_does_not_mutate_and_retains_unknown_prices() -> None:
    frame = market(10, 2)
    frame.loc[0, "price_pkr"] = None
    before = frame.copy(deep=True)
    data, reason = prepare(frame, REQUIRED)
    assert reason is None and len(data) == 20
    assert data._valid_price.sum() == 19
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize("mode", ["missing", "empty", "identity", "time", "duplicate"])
def test_invalid_contracts(mode: str) -> None:
    frame = market(2, 1)
    if mode == "missing":
        frame = frame.drop(columns="price_pkr")
    elif mode == "empty":
        frame = frame.iloc[:0]
    elif mode == "identity":
        frame.loc[0, "listing_id"] = None
    elif mode == "time":
        frame["observed_at"] = "bad"
    else:
        frame = pd.concat([frame, frame])
    assert prepare(frame, REQUIRED)[1] is not None


def test_quality_flags_and_duplicate_exclusion() -> None:
    frame = market(4, 1)
    frame.at[0, "quality_flag"] = ["placeholder_price"]
    frame.at[1, "duplicate_of"] = "0"
    frame.at[2, "quality_flag"] = "invalid serialized flags"
    assert prepare(frame, REQUIRED)[0]._valid_price.sum() == 1


def test_serialized_category_order_does_not_change_design_columns() -> None:
    data = model_rows(prepare(market(30, 1), REQUIRED)[0])
    spec = design_spec(data, ["transmission", "make_model", "city"])
    reloaded = DesignSpec.model_validate_json(
        json.dumps(spec.model_dump(), sort_keys=True)
    )
    np.testing.assert_array_equal(design(data, spec), design(data, reloaded))
    with pytest.raises(ValueError, match="terms do not match"):
        design(data, spec.model_copy(update={"names": ["intercept"]}))


def test_design_and_robust_regression_recover_truth() -> None:
    data = model_rows(prepare(market(240, 1, noise=0), REQUIRED)[0])
    spec = design_spec(
        data, ["make_model", "transmission", "city", "assembly", "seller_type"]
    )
    # Feature effect is omitted here, so use a separate exact response.
    matrix = design(data, spec)
    coefficients = np.arange(matrix.shape[1], dtype=float) / 100
    target = matrix @ coefficients + np.random.default_rng(11).normal(
        0, 0.00001, len(data)
    )
    fitted = fit_linear(matrix, target)
    np.testing.assert_allclose(fitted.params, coefficients, atol=0.0001)
    clustered = fit_linear(matrix, target, data.listing_id.tolist())
    assert np.isfinite(clustered.conf_int()).all()
    bad = data.copy()
    bad["city"] = "unknown city"
    with pytest.raises(ValueError, match="Unknown category"):
        design(bad, spec)


@pytest.mark.parametrize(
    "matrix,target",
    [
        (np.ones((2, 1)), np.ones(2)),
        (np.ones((10, 2)), np.arange(10.0)),
        (np.ones((10, 1)), np.ones(10)),
        (np.full((10, 1), np.nan), np.arange(10.0)),
    ],
)
def test_unidentified_models_rejected(matrix, target) -> None:
    with pytest.raises(ValueError):
        fit_linear(matrix, target)
