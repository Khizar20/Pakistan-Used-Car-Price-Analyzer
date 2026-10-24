"""Known effects, grouped no-leakage validation, explanations and browser contract."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests.analysis.synthetic import market
from tracker.analysis.common import design
from tracker.analysis.drivers import group_folds, predict_fair_price, price_drivers


@pytest.fixture(scope="module")
def fitted():
    data = market(240, 3)
    result = price_drivers(data)
    assert result.status == "ok", result.reason
    return data, result


def test_known_coefficients_recovered_and_baseline_beaten(fitted) -> None:
    _, result = fitted
    values = {term.name: term.coefficient for term in result.coefficients}
    assert values["model_year"] == pytest.approx(0.06, abs=0.005)
    assert values["log_mileage"] == pytest.approx(-0.12, abs=0.005)
    assert values["engine_litres"] == pytest.approx(0.30, abs=0.02)
    assert values["transmission=manual"] == pytest.approx(-0.15, abs=0.02)
    assert values["feature:ABS=1"] == pytest.approx(0.05, abs=0.02)
    assert result.linear_metrics.mae_pkr < result.baseline_metrics.mae_pkr
    assert result.linear_metrics.mape_percent < 5
    assert result.linear_metrics.r_squared > 0.95
    assert len(result.diagnostics) == result.listings_used == 240
    assert set(result.diagnostics_by_make) == {"Honda", "Toyota"}
    assert result.shap_effects and all(
        effect.mean_absolute_log_effect >= 0 for effect in result.shap_effects
    )
    assert len(result.dependence["mileage_km"]) == 20


def test_group_folds_never_split_the_same_car() -> None:
    data = market(30, 4)
    folds = group_folds(data)
    tested = []
    for train, test in folds:
        assert set(data.iloc[train].listing_id).isdisjoint(data.iloc[test].listing_id)
        tested.extend(test)
    assert sorted(tested) == list(range(len(data)))
    assert group_folds(data) == folds
    with pytest.raises(ValueError):
        group_folds(data, 31)


def test_exported_coefficients_reproduce_python_predictions(fitted) -> None:
    data, result = fitted
    cars = data.drop_duplicates("listing_id", keep="last").iloc[:20].copy()
    cars["make_model"] = cars.make + " / " + cars.model
    cars["feature:ABS"] = cars.features.map(lambda values: str(int("ABS" in values)))
    model = result.fair_price
    expected = np.exp(
        design(cars, model.spec)
        @ np.asarray([model.coefficients[name] for name in model.spec.names])
    )
    actual = predict_fair_price(cars, model)
    np.testing.assert_allclose(
        [value.estimate_pkr for value in actual], expected, rtol=1e-12
    )
    assert all(
        value.lower_pkr < value.estimate_pkr < value.upper_pkr for value in actual
    )
    minimal = cars[
        ["make", "model", "model_year", "mileage_km", "transmission", "city"]
    ]
    assert len(predict_fair_price(minimal, model)) == 20
    for name, value in (("city", "Unseen"), ("mileage_km", -1)):
        bad = minimal.copy()
        bad[name] = value
        with pytest.raises(ValueError):
            predict_fair_price(bad, model)
    with pytest.raises(ValueError):
        predict_fair_price(pd.DataFrame(), model)


@pytest.mark.parametrize(
    "mode", ["empty", "single", "missing", "constant", "rare", "parameters"]
)
def test_sparse_or_unidentified_inputs_are_insufficient(mode: str) -> None:
    frame = market(60, 1)
    if mode == "empty":
        frame = frame.iloc[:0]
    elif mode == "single":
        frame = frame.iloc[:1]
    elif mode == "missing":
        frame = frame.drop(columns="model_year")
    elif mode == "constant":
        frame["price_pkr"] = 1000000
    elif mode == "rare":
        frame.loc[0, "city"] = "Rare City"
    else:
        frame["city"] = [f"City {index // 5}" for index in range(len(frame))]
    assert price_drivers(frame).status == "insufficient_data"


def test_determinism_and_invalid_configuration(fitted) -> None:
    frame, first = fitted
    assert price_drivers(frame).model_dump() == first.model_dump()
    for kwargs in ({"minimum_listings": 1}, {"cv_splits": 1}):
        with pytest.raises(ValueError):
            price_drivers(frame, **kwargs)
