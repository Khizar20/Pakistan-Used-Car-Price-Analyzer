"""Grouped validation of robust linear and explained gradient-boosted price models."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from importlib import import_module
from typing import Protocol, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from pydantic import BaseModel, Field

from tracker.analysis.common import (
    DesignSpec,
    FloatArray,
    Result,
    design,
    design_spec,
    fit_linear,
    model_rows,
    prepare,
)

REQUIRED = [
    "listing_id",
    "observed_at",
    "price_pkr",
    "make",
    "model",
    "model_year",
    "mileage_km",
    "engine_cc",
    "transmission",
    "city",
]
OPTIONAL_CATEGORIES = ("assembly", "seller_type", "fuel_type", "body_type")


class Metrics(BaseModel):
    mae_pkr: float
    mape_percent: float
    r_squared: float | None


class Coefficient(BaseModel):
    name: str
    coefficient: float
    lower: float
    upper: float
    effect_percent: float | None
    lower_percent: float | None
    upper_percent: float | None


class Diagnostic(BaseModel):
    listing_id: str
    make: str
    fitted_pkr: float
    actual_pkr: float
    residual_pkr: float
    residual_log: float


class CurvePoint(BaseModel):
    x: float
    price_pkr: float


class ShapEffect(BaseModel):
    feature: str
    mean_absolute_log_effect: float


class FairPriceModel(BaseModel):
    spec: DesignSpec
    coefficients: dict[str, float]
    ranges: dict[str, tuple[float, float]]
    defaults: dict[str, float | str]
    residual_std_log: float
    typical_error_percent: float
    reference_year: int


class PriceEstimate(BaseModel):
    estimate_pkr: float
    lower_pkr: float
    upper_pkr: float


class DriversResult(Result):
    listings_used: int = 0
    omitted_predictors: list[str] = Field(default_factory=list)
    coefficients: list[Coefficient] = Field(default_factory=list)
    linear_metrics: Metrics | None = None
    boosting_metrics: Metrics | None = None
    baseline_metrics: Metrics | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    diagnostics_by_make: dict[str, Metrics] = Field(default_factory=dict)
    shap_effects: list[ShapEffect] = Field(default_factory=list)
    dependence: dict[str, list[CurvePoint]] = Field(default_factory=dict)
    fair_price: FairPriceModel | None = None


class Splitter(Protocol):
    def split(
        self, X: FloatArray, *, groups: NDArray[np.str_]
    ) -> Iterator[tuple[NDArray[np.int64], NDArray[np.int64]]]: ...


def group_folds(
    frame: pd.DataFrame, splits: int = 5
) -> list[tuple[list[int], list[int]]]:
    if splits < 2 or frame.listing_id.nunique() < splits:
        raise ValueError("Need at least one distinct listing per fold and >= 2 folds")
    factory = cast(
        Callable[..., Splitter], import_module("sklearn.model_selection").GroupKFold
    )
    splitter = factory(n_splits=splits, shuffle=True, random_state=731)
    return [
        (
            [int(index) for index in train.ravel()],
            [int(index) for index in test.ravel()],
        )
        for train, test in splitter.split(
            np.zeros((len(frame), 1)), groups=np.asarray(frame.listing_id, dtype=str)
        )
    ]


class Boosting(Protocol):
    def fit(self, X: FloatArray, y: FloatArray) -> object: ...
    def predict(self, X: FloatArray) -> FloatArray: ...


def _boosting() -> Boosting:
    factory = cast(
        Callable[..., Boosting],
        import_module("sklearn.ensemble").GradientBoostingRegressor,
    )
    return factory(
        n_estimators=80,
        max_depth=2,
        learning_rate=0.05,
        random_state=731,
        loss="squared_error",
    )


class Explainer(Protocol):
    def shap_values(self, X: FloatArray, *, check_additivity: bool) -> FloatArray: ...


def _metrics(actual: FloatArray, predicted: FloatArray) -> Metrics:
    residual = actual - predicted
    denominator = float(np.sum((actual - actual.mean()) ** 2))
    return Metrics(
        mae_pkr=float(np.abs(residual).mean()),
        mape_percent=float(100 * np.mean(np.abs(residual) / actual)),
        r_squared=1 - float(np.sum(residual**2)) / denominator
        if denominator > 0
        else None,
    )


def _predictors(data: pd.DataFrame) -> tuple[list[str], list[str], list[str]]:
    categories = ["make_model", "transmission", "city"]
    omitted = []
    for column in OPTIONAL_CATEGORIES:
        if column in data and data[column].notna().all():
            categories.append(column)
        else:
            omitted.append(column)
    features = []
    if (
        "features" in data
        and data.features.map(lambda value: isinstance(value, list | tuple)).all()
    ):
        labels = sorted(
            {str(feature) for values in data.features for feature in values}
        )
        for label in labels:
            name = "feature:" + label
            data[name] = [int(label in values) for values in data.features]
            count = int(data[name].sum())
            if 5 <= count <= len(data) - 5:
                features.append(name)
    else:
        omitted.append("features")
    return categories, features, omitted


def _dependence(
    data: pd.DataFrame, model: Boosting, spec: DesignSpec, reference_year: int
) -> dict[str, list[CurvePoint]]:
    reference = data.iloc[:200].copy()
    curves = {}
    for column, output in (("model_year", "age"), ("mileage_km", "mileage_km")):
        points = []
        for value in np.unique(
            np.linspace(float(data[column].min()), float(data[column].max()), 20)
        ):
            changed = reference.copy()
            changed[column] = value
            price = float(np.exp(model.predict(design(changed, spec))).mean())
            points.append(
                CurvePoint(
                    x=float(reference_year - value)
                    if output == "age"
                    else float(value),
                    price_pkr=price,
                )
            )
        curves[output] = sorted(points, key=lambda point: point.x)
    return curves


def price_drivers(
    frame: pd.DataFrame, *, minimum_listings: int = 50, cv_splits: int = 5
) -> DriversResult:
    if minimum_listings < 10 or cv_splits < 2:
        raise ValueError("Require minimum listings >= 10 and folds >= 2")
    prepared, reason = prepare(frame, REQUIRED)
    if reason:
        return DriversResult(reason=reason)
    # One latest observation per vehicle prevents observation frequency weighting.
    data = model_rows(prepared.drop_duplicates("listing_id", keep="last")).reset_index(
        drop=True
    )
    if len(data) < minimum_listings or data.listing_id.nunique() < cv_splits:
        return DriversResult(
            reason="Too few distinct complete current listings", listings_used=len(data)
        )
    categories, features, omitted = _predictors(data)
    if any(data[column].value_counts().min() < 5 for column in categories):
        return DriversResult(
            reason="Categorical levels need at least five distinct listings",
            listings_used=len(data),
            omitted_predictors=omitted,
        )
    spec = design_spec(data, categories, feature_columns=features)
    matrix = design(data, spec)
    if len(data) < 5 * matrix.shape[1]:
        return DriversResult(
            reason="Too few listings per model parameter",
            listings_used=len(data),
            omitted_predictors=omitted,
        )
    actual = data.price_pkr.to_numpy(dtype=float)
    log_actual = np.log(actual)
    linear, boosted, baseline = (np.zeros(len(data)) for _ in range(3))
    try:
        full = fit_linear(matrix, log_actual)
        for train_indices, test_indices in group_folds(data, cv_splits):
            train, test = data.iloc[train_indices], data.iloc[test_indices]
            fold_spec = design_spec(train, categories, feature_columns=features)
            train_matrix, test_matrix = (
                design(train, fold_spec),
                design(test, fold_spec),
            )
            fold = fit_linear(
                train_matrix, np.log(train.price_pkr.to_numpy(dtype=float))
            )
            linear[test_indices] = np.exp(test_matrix @ fold.params)
            tree = _boosting()
            tree.fit(train_matrix, np.log(train.price_pkr.to_numpy(dtype=float)))
            boosted[test_indices] = np.exp(tree.predict(test_matrix))
            medians = train.groupby("make_model").price_pkr.median()
            baseline[test_indices] = (
                test.make_model.map(medians)
                .fillna(train.price_pkr.median())
                .to_numpy(dtype=float)
            )
    except ValueError as exc:
        return DriversResult(
            reason=str(exc), listings_used=len(data), omitted_predictors=omitted
        )
    bounds = full.conf_int()
    if (
        np.max(np.abs(bounds)) > 50
        or not np.isfinite(linear).all()
        or not np.isfinite(boosted).all()
    ):
        return DriversResult(
            reason="Predictive coefficients or uncertainty are unstable",
            listings_used=len(data),
        )
    coefficients = [
        Coefficient(
            name=name,
            coefficient=float(value),
            lower=float(bounds[index, 0]),
            upper=float(bounds[index, 1]),
            effect_percent=float(100 * np.expm1(value))
            if name != "intercept"
            else None,
            lower_percent=float(100 * np.expm1(bounds[index, 0]))
            if name != "intercept"
            else None,
            upper_percent=float(100 * np.expm1(bounds[index, 1]))
            if name != "intercept"
            else None,
        )
        for index, (name, value) in enumerate(zip(spec.names, full.params, strict=True))
    ]
    linear_metrics = _metrics(actual, linear)
    tree = _boosting()
    tree.fit(matrix, log_actual)
    factory = cast(Callable[..., Explainer], import_module("shap").TreeExplainer)
    explained = factory(tree, feature_perturbation="tree_path_dependent").shap_values(
        matrix[:200], check_additivity=True
    )
    effects = [
        ShapEffect(feature=name, mean_absolute_log_effect=float(value))
        for name, value in zip(spec.names, np.abs(explained).mean(axis=0), strict=True)
        if name != "intercept"
    ]
    reference_year = int(data.observed_at.dt.year.max())
    defaults: dict[str, float | str] = {
        column: str(data[column].mode().iloc[0]) for column in spec.categories
    }
    defaults["engine_cc"] = float(data.engine_cc.median())
    fair = FairPriceModel(
        spec=spec,
        coefficients={
            name: float(value)
            for name, value in zip(spec.names, full.params, strict=True)
        },
        ranges={
            name: (float(data[name].min()), float(data[name].max()))
            for name in ("model_year", "mileage_km", "engine_cc")
        },
        defaults=defaults,
        residual_std_log=float(np.std(full.resid, ddof=matrix.shape[1])),
        typical_error_percent=linear_metrics.mape_percent,
        reference_year=reference_year,
    )
    return DriversResult(
        status="ok",
        listings_used=len(data),
        omitted_predictors=omitted,
        coefficients=coefficients,
        linear_metrics=linear_metrics,
        boosting_metrics=_metrics(actual, boosted),
        baseline_metrics=_metrics(actual, baseline),
        diagnostics=[
            Diagnostic(
                listing_id=str(row.listing_id),
                make=str(row.make),
                fitted_pkr=float(fitted),
                actual_pkr=float(price),
                residual_pkr=float(price - fitted),
                residual_log=float(np.log(price / fitted)),
            )
            for row, fitted, price in zip(
                data.itertuples(), linear, actual, strict=True
            )
        ],
        diagnostics_by_make={
            str(make): _metrics(
                actual[group.index.to_numpy()], linear[group.index.to_numpy()]
            )
            for make, group in data.groupby("make")
        },
        shap_effects=sorted(
            effects, key=lambda value: (-value.mean_absolute_log_effect, value.feature)
        ),
        dependence=_dependence(data, tree, spec, reference_year),
        fair_price=fair,
    )


def predict_fair_price(
    cars: pd.DataFrame, model: FairPriceModel
) -> list[PriceEstimate]:
    """Evaluate exported coefficients in-range; no fit or external state required."""
    required = {"make", "model", "model_year", "mileage_km", "transmission", "city"}
    if not required <= set(cars.columns):
        raise ValueError("Missing Fair Price Check inputs")
    data = cars.copy()
    data["make_model"] = data.make.astype(str) + " / " + data.model.astype(str)
    for name, value in model.defaults.items():
        if name not in data:
            data[name] = value
    for name, (low, high) in model.ranges.items():
        values = pd.to_numeric(data[name], errors="coerce")
        if not values.between(low, high).all():
            raise ValueError(f"Outside training range: {name}")
        data[name] = values
    matrix = design(data, model.spec)
    coefficients = np.asarray([model.coefficients[name] for name in model.spec.names])
    prediction = matrix @ coefficients
    width = 1.96 * model.residual_std_log
    return [
        PriceEstimate(
            estimate_pkr=float(np.exp(value)),
            lower_pkr=float(np.exp(value - width)),
            upper_pkr=float(np.exp(value + width)),
        )
        for value in prediction
    ]
