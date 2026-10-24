"""Pure input contracts and a typed boundary around statistical regression."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from importlib import import_module
from typing import Literal, Protocol, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

FloatArray = NDArray[np.float64]
BAD_FLAGS = frozenset(
    {
        "placeholder_price",
        "below_price_floor",
        "price_outlier_mad",
        "invalid_source_price",
        "price_conflict",
        "possible_duplicate",
    }
)


class Result(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    status: Literal["ok", "insufficient_data"] = "insufficient_data"
    reason: str | None = None


def prepare(
    frame: pd.DataFrame, required: Sequence[str]
) -> tuple[pd.DataFrame, str | None]:
    """Validate observation identities/times without dropping unknown-price rows."""
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        return pd.DataFrame(), "Missing columns: " + ", ".join(missing)
    if frame.empty:
        return pd.DataFrame(), "No observations available"
    data = frame.copy(deep=True)
    if "listing_id" in required:
        if data.listing_id.isna().any():
            return pd.DataFrame(), "Listing identity is missing"
        data["listing_id"] = data.listing_id.astype(str)
    if "observed_at" in required:
        data["observed_at"] = pd.to_datetime(
            data.observed_at, utc=True, errors="coerce"
        )
        if data.observed_at.isna().any():
            return pd.DataFrame(), "Invalid observation timestamps"
        if (
            "listing_id" in required
            and data.duplicated(["listing_id", "observed_at"]).any()
        ):
            return pd.DataFrame(), "Duplicate listing/timestamp observations"
        data = data.sort_values(
            ["observed_at", "listing_id"]
            if "listing_id" in required
            else ["observed_at"],
            kind="stable",
        ).reset_index(drop=True)
    if "price_pkr" in data:
        data["price_pkr"] = pd.to_numeric(data.price_pkr, errors="coerce").astype(float)
        data["_valid_price"] = np.isfinite(data.price_pkr) & data.price_pkr.gt(0)
        if "quality_flag" in data:
            good = data.quality_flag.map(
                lambda value: not bool(BAD_FLAGS.intersection(value))
                if isinstance(value, list | tuple)
                else value is None
            )
            data["_valid_price"] &= good
        if "duplicate_of" in data:
            data["_valid_price"] &= data.duplicate_of.isna()
    return data, None


class DesignSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    numeric: list[str]
    categories: dict[str, list[str]]
    names: list[str]


NUMERIC = ("model_year", "log_mileage", "engine_litres")


def numeric_values(frame: pd.DataFrame, name: str) -> FloatArray:
    if name == "log_mileage":
        return np.asarray(np.log1p(pd.to_numeric(frame.mileage_km)), dtype=float)
    if name == "engine_litres":
        return np.asarray(pd.to_numeric(frame.engine_cc) / 1000, dtype=float)
    return np.asarray(pd.to_numeric(frame.model_year) - 2000, dtype=float)


def design_spec(
    frame: pd.DataFrame,
    categories: Sequence[str],
    *,
    feature_columns: Sequence[str] = (),
) -> DesignSpec:
    numeric = [name for name in NUMERIC if np.ptp(numeric_values(frame, name)) > 0]
    levels = {
        column: sorted(frame[column].astype(str).unique().tolist())
        for column in categories
    }
    levels.update(
        {
            column: ["0", "1"]
            for column in feature_columns
            if frame[column].nunique() > 1
        }
    )
    names = [
        "intercept",
        *numeric,
        *(
            f"{column}={level}"
            for column, values in levels.items()
            for level in values[1:]
        ),
    ]
    return DesignSpec(numeric=numeric, categories=levels, names=names)


def design(frame: pd.DataFrame, spec: DesignSpec) -> FloatArray:
    columns: dict[str, FloatArray] = {"intercept": np.ones(len(frame))}
    columns.update({name: numeric_values(frame, name) for name in spec.numeric})
    for column, levels in spec.categories.items():
        values = frame[column].astype(str)
        if not values.isin(levels).all():
            raise ValueError(f"Unknown category for {column}")
        columns.update(
            {
                f"{column}={level}": np.asarray(values.eq(level), dtype=float)
                for level in levels[1:]
            }
        )
    if len(spec.names) != len(columns) or set(spec.names) != set(columns):
        raise ValueError("Prediction terms do not match numeric and category encoding")
    return np.column_stack([columns[name] for name in spec.names])


class LinearFit(Protocol):
    params: FloatArray
    resid: FloatArray
    rsquared: float

    def conf_int(self, alpha: float = 0.05) -> FloatArray: ...


class OLSModel(Protocol):
    def fit(
        self, *, cov_type: str, cov_kwds: dict[str, object] | None = None
    ) -> LinearFit: ...


def fit_linear(
    matrix: FloatArray, target: FloatArray, groups: Sequence[str] | None = None
) -> LinearFit:
    """Fit identified log-linear models with HC3 or listing-clustered errors."""
    if (
        len(target) <= matrix.shape[1] + 2
        or not np.isfinite(matrix).all()
        or not np.isfinite(target).all()
    ):
        raise ValueError("Too few finite observations for the model size")
    if np.ptp(target) < 1e-12 or np.linalg.matrix_rank(matrix) < matrix.shape[1]:
        raise ValueError("Constant prices or non-identifiable model predictors")
    constructor = cast(
        Callable[[FloatArray, FloatArray], OLSModel],
        import_module("statsmodels.api").OLS,
    )
    result = constructor(target, matrix).fit(
        cov_type="cluster" if groups is not None else "HC3",
        cov_kwds={"groups": np.asarray(groups)} if groups is not None else None,
    )
    if not np.isfinite(result.params).all() or not np.isfinite(result.conf_int()).all():
        raise ValueError("Model uncertainty could not be estimated")
    return result


def model_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Complete positive-price rows for the common quality-adjustment formula."""
    result = frame.loc[frame._valid_price].copy()
    for column in ("model_year", "mileage_km", "engine_cc"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.dropna(
        subset=[
            "make",
            "model",
            "transmission",
            "city",
            "model_year",
            "mileage_km",
            "engine_cc",
        ]
    )
    finite = pd.Series(
        np.isfinite(
            result[["model_year", "mileage_km", "engine_cc"]].to_numpy(dtype=float)
        ).all(axis=1),
        index=result.index,
    )
    result = result.loc[finite & result.mileage_km.ge(0) & result.engine_cc.gt(0)]
    result["make_model"] = result.make.astype(str) + " / " + result.model.astype(str)
    return result
