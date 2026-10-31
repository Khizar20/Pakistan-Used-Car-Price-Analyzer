"""Version-one public contracts and deterministic schema-derived TypeScript."""

from __future__ import annotations

import json
from typing import Annotated, Final, Literal, cast

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from tracker.analysis.cities import CityPrice
from tracker.analysis.drivers import CurvePoint, Metrics, ShapEffect
from tracker.analysis.drops import SurvivalCurve
from tracker.analysis.index import IndexResult
from tracker.analysis.seasonality import SeasonalityResult

SCHEMA_VERSION: Final = "1.1.0"
MAX_FILE_BYTES = 500_000
SAMPLE_LIMIT: Final = 100
DIAGNOSTIC_LIMIT = 200
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Count = Annotated[int, Field(ge=0)]


class PublicModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        json_schema_serialization_defaults_required=True,
    )


class Envelope(PublicModel):
    schema_version: Literal["1.1.0"] = SCHEMA_VERSION
    generated_at: AwareDatetime
    bundle_id: Digest


class Status(PublicModel):
    status: Literal["ok", "insufficient_data"]
    reason: str | None


class Metadata(PublicModel):
    date_start: str | None
    date_end: str | None
    run_count: Count
    listing_count: Count
    observation_count: Count
    scope_count: Count
    seasonal_series_basis: str
    caveats: list[str]


class MetaExport(Envelope):
    data: Metadata


class IndexExport(Envelope):
    data: IndexResult


class DropSummary(Status):
    observed_listings: Count
    eligible_listings: Count
    drop_share: Annotated[float, Field(ge=0, le=1)] | None
    median_drop_pkr: float | None
    median_drop_percent: float | None
    days_to_first_drop: list[float]
    drop_sizes_pkr: list[float]
    drop_sizes_percent: list[float]
    survival: list[SurvivalCurve]


class DropsExport(Envelope):
    data: DropSummary


class SeasonalityExport(Envelope):
    data: SeasonalityResult


class PublicCoefficient(PublicModel):
    term: str
    coefficient: float
    lower: float
    upper: float
    effect_percent: float | None
    lower_percent: float | None
    upper_percent: float | None


class Residual(PublicModel):
    listing_hash: Digest
    make: str
    fitted_pkr: float
    actual_pkr: float
    residual_pkr: float
    residual_log: float


class DriverSummary(Status):
    listings_used: Count
    omitted_predictors: list[str]
    coefficients: list[PublicCoefficient]
    linear_metrics: Metrics | None
    boosting_metrics: Metrics | None
    baseline_metrics: Metrics | None
    diagnostics: Annotated[list[Residual], Field(max_length=DIAGNOSTIC_LIMIT)]
    diagnostics_total: Count
    diagnostics_by_make: dict[str, Metrics]
    shap_effects: list[ShapEffect]
    dependence: dict[str, list[CurvePoint]]


class DriversExport(Envelope):
    data: DriverSummary


class PredictionSpec(PublicModel):
    numeric: list[Literal["model_year", "log_mileage", "engine_litres"]]
    categories: dict[str, list[str]]
    terms: list[str]


class FairModel(PublicModel):
    spec: PredictionSpec
    coefficients: dict[str, float]
    ranges: dict[str, tuple[float, float]]
    defaults: dict[str, float | str]
    residual_std_log: Annotated[float, Field(ge=0)]
    typical_error_percent: Annotated[float, Field(ge=0)]
    reference_year: int
    transformations: dict[str, str]
    interval_multiplier: Annotated[float, Field(ge=1.96, le=1.96)] = 1.96
    point_estimate: Literal["conditional_median"] = "conditional_median"


class FairPriceSummary(Status):
    model: FairModel | None


class FairPriceExport(Envelope):
    data: FairPriceSummary


class ModelSummary(PublicModel):
    make: str
    model: str
    listing_count: Count
    priced_listing_count: Count
    median_price_pkr: float | None


class ModelsSummary(Status):
    models: list[ModelSummary]
    city_prices: list[CityPrice] = Field(default_factory=list)
    city_price_parts: list[Digest] = Field(default_factory=list)
    minimum_city_sample: int = 5
    population: Literal["latest_active_nonduplicate"] = "latest_active_nonduplicate"


class ModelsExport(Envelope):
    data: ModelsSummary


class CityPricesPartExport(Envelope):
    data: list[CityPrice]


class ListingSample(PublicModel):
    listing_hash: Digest
    make: str | None
    model: str | None
    model_year: int | None
    city: str | None
    observed_at: str
    old_price_pkr: float
    new_price_pkr: float
    drop_pkr: float
    drop_percent: float
    days_listed: float


class SampleSummary(Status):
    total_events: Count
    limit: Literal[100] = SAMPLE_LIMIT
    rows: Annotated[list[ListingSample], Field(max_length=SAMPLE_LIMIT)]


class SampleExport(Envelope):
    data: SampleSummary


CONTRACTS: dict[str, type[Envelope]] = {
    "meta.json": MetaExport,
    "index.json": IndexExport,
    "drops.json": DropsExport,
    "seasonality.json": SeasonalityExport,
    "drivers.json": DriversExport,
    "fairprice.json": FairPriceExport,
    "models.json": ModelsExport,
    "listings_sample.json": SampleExport,
}


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON Schema object")
    return cast(dict[str, object], value)


def _ts_type(node: dict[str, object], prefix: str) -> str:
    """Translate the subset emitted by these contracts, refusing unknown constructs."""
    if "$ref" in node:
        reference = str(node["$ref"])
        if not reference.startswith("#/$defs/"):
            raise ValueError("Only local schema references are supported")
        return prefix + reference.removeprefix("#/$defs/")
    if "const" in node:
        return json.dumps(node["const"])
    for keyword in ("enum", "anyOf"):
        alternatives = node.get(keyword)
        if isinstance(alternatives, list):
            return (
                "("
                + " | ".join(
                    json.dumps(item)
                    if keyword == "enum"
                    else _ts_type(_mapping(item), prefix)
                    for item in alternatives
                )
                + ")"
            )
    kind = node.get("type")
    if kind in ("integer", "number"):
        return "number"
    if kind in ("string", "boolean", "null"):
        return str(kind)
    if kind == "array":
        items = node.get("prefixItems")
        if isinstance(items, list):
            return "[" + ", ".join(_ts_type(_mapping(v), prefix) for v in items) + "]"
        return "Array<" + _ts_type(_mapping(node["items"]), prefix) + ">"
    if kind == "object":
        properties = node.get("properties")
        if isinstance(properties, dict):
            required = node.get("required", [])
            return (
                "{ "
                + " ".join(
                    json.dumps(key)
                    + ("" if key in cast(list[str], required) else "?")
                    + ": "
                    + _ts_type(_mapping(value), prefix)
                    + ";"
                    for key, value in properties.items()
                )
                + " }"
            )
        additional = node.get("additionalProperties")
        if isinstance(additional, dict):
            return "Record<string, " + _ts_type(_mapping(additional), prefix) + ">"
    raise ValueError("Unsupported JSON Schema construct")


def contract_artifacts() -> dict[str, str]:
    """Generate schemas and declarations from the same serialization contracts."""
    artifacts: dict[str, str] = {}
    declarations = [
        "// Generated by tracker export; edit Python contracts, not this file."
    ]
    artifact_contracts: dict[str, type[Envelope]] = {
        **CONTRACTS,
        "city_prices.json": CityPricesPartExport,
    }
    for filename, model in artifact_contracts.items():
        schema = model.model_json_schema(mode="serialization")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        artifacts[filename.replace(".json", ".schema.json")] = (
            json.dumps(schema, indent=2, sort_keys=True) + "\n"
        )
        prefix = model.__name__ + "_"
        for key, definition in sorted(_mapping(schema.get("$defs", {})).items()):
            declarations.append(
                f"type {prefix}{key} = {_ts_type(_mapping(definition), prefix)};"
            )
        declarations.append(
            f"export type {model.__name__} = {_ts_type(schema, prefix)};"
        )
    artifacts["contracts.ts"] = "\n".join(declarations) + "\n"
    return artifacts
