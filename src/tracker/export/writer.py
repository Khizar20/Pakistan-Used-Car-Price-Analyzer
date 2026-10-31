"""Allowlisted public projections, privacy/size preflight and recoverable writes."""

from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from pydantic import BaseModel

from tracker.analysis.cities import city_prices
from tracker.analysis.common import prepare
from tracker.analysis.runner import ASSUMPTIONS, analyze_frame
from tracker.export.parts import encode, partition_models, prune_parts
from tracker.export.schema import (
    CONTRACTS,
    DIAGNOSTIC_LIMIT,
    MAX_FILE_BYTES,
    SAMPLE_LIMIT,
    DriverSummary,
    DropSummary,
    Envelope,
    FairModel,
    FairPriceSummary,
    ListingSample,
    Metadata,
    ModelsSummary,
    ModelSummary,
    PredictionSpec,
    PublicCoefficient,
    Residual,
    SampleSummary,
    contract_artifacts,
)

FORBIDDEN = re.compile(
    r"name|phone|email|url|address|listing_?id",
    re.I,
)
CONTACT = re.compile(
    r"@|://|www\.|(?<!\w)\+?\d(?:[ ()-]*\d){8,14}(?!\w)",
    re.I,
)


def public_hash(identity: str) -> str:
    """Pseudonym stable within this database; not a seller identity or listing URL."""
    return hashlib.sha256(("public-listing:v1:" + identity).encode()).hexdigest()


def assert_public(value: object) -> None:
    """Reject sensitive fields/contact strings anywhere in the public projection."""
    if isinstance(value, dict):
        for key, child in value.items():
            if FORBIDDEN.search(str(key)) or CONTACT.search(str(key)):
                raise ValueError("Public export contains a forbidden field")
            assert_public(child)
    elif isinstance(value, list):
        for child in value:
            assert_public(child)
    elif isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value):
        return
    elif isinstance(value, str) and CONTACT.search(value):
        raise ValueError("Public export contains a contact detail")


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _models(data: pd.DataFrame) -> ModelsSummary:
    if data.empty:
        return ModelsSummary(
            status="insufficient_data", reason="No current listings", models=[]
        )
    current = data.drop_duplicates("listing_id", keep="last")
    current = current.loc[current.is_active.eq(True)]
    if "duplicate_of" in current:
        current = current.loc[current.duplicate_of.isna()]
    models = []
    for (make, model), group in current.dropna(subset=["make", "model"]).groupby(
        ["make", "model"], sort=True
    ):
        prices = group.loc[group._valid_price, "price_pkr"]
        models.append(
            ModelSummary(
                make=str(make),
                model=str(model),
                listing_count=len(group),
                priced_listing_count=len(prices),
                median_price_pkr=float(prices.median()) if not prices.empty else None,
            )
        )
    return ModelsSummary(
        status="ok" if models else "insufficient_data",
        reason=None if models else "No current listings with make/model attributes",
        models=models,
        city_prices=city_prices(data),
    )


def build_exports(
    frame: pd.DataFrame, *, generated_at: datetime
) -> dict[str, Envelope]:
    """Analyze one input snapshot and construct only explicitly public fields."""
    data, reason = prepare(
        frame,
        [
            "listing_id",
            "observed_at",
            "price_pkr",
            "is_active",
            "make",
            "model",
            "model_year",
            "city",
        ],
    )
    if reason and not frame.empty:
        raise ValueError(reason)
    report = analyze_frame(frame, generated_at=generated_at)
    drops, drivers = report.drops, report.drivers
    coefficients = [
        PublicCoefficient(
            term=term.name,
            coefficient=term.coefficient,
            lower=term.lower,
            upper=term.upper,
            effect_percent=term.effect_percent,
            lower_percent=term.lower_percent,
            upper_percent=term.upper_percent,
        )
        for term in drivers.coefficients
    ]
    diagnostics = [
        Residual(
            listing_hash=public_hash(row.listing_id),
            make=row.make,
            fitted_pkr=row.fitted_pkr,
            actual_pkr=row.actual_pkr,
            residual_pkr=row.residual_pkr,
            residual_log=row.residual_log,
        )
        for row in drivers.diagnostics
    ]
    diagnostics.sort(key=lambda row: row.listing_hash)
    fair: FairModel | None = None
    if drivers.fair_price:
        model = drivers.fair_price
        fair = FairModel(
            spec=PredictionSpec.model_validate(
                {
                    "numeric": model.spec.numeric,
                    "categories": model.spec.categories,
                    "terms": model.spec.names,
                }
            ),
            coefficients=model.coefficients,
            ranges=model.ranges,
            defaults=model.defaults,
            residual_std_log=model.residual_std_log,
            typical_error_percent=model.typical_error_percent,
            reference_year=model.reference_year,
            transformations={
                "intercept": "1",
                "model_year": "model_year - 2000",
                "log_mileage": "log(1 + mileage_km)",
                "engine_litres": "engine_cc / 1000",
                "categories": "first sorted level is baseline; other levels are 0/1",
            },
        )
    rows = []
    attributes = (
        data.drop_duplicates("listing_id", keep="last").set_index("listing_id")
        if not data.empty
        else pd.DataFrame()
    )
    events = sorted(
        drops.events,
        key=lambda event: (event.observed_at, public_hash(event.listing_id)),
        reverse=True,
    )
    for event in events[:SAMPLE_LIMIT]:
        row = attributes.loc[event.listing_id]
        rows.append(
            ListingSample(
                listing_hash=public_hash(event.listing_id),
                make=_text(row["make"]),
                model=_text(row["model"]),
                city=_text(row["city"]),
                model_year=int(row["model_year"])
                if pd.notna(row["model_year"])
                else None,
                observed_at=event.observed_at,
                old_price_pkr=event.old_price_pkr,
                new_price_pkr=event.new_price_pkr,
                drop_pkr=event.drop_pkr,
                drop_percent=event.drop_percent,
                days_listed=event.days_listed,
            )
        )
    bodies: dict[str, BaseModel] = {
        "meta.json": Metadata(
            date_start=report.date_start,
            date_end=report.date_end,
            run_count=report.observed_runs,
            listing_count=report.listings,
            observation_count=report.observations,
            scope_count=report.observed_scopes,
            seasonal_series_basis=report.seasonal_series_basis,
            caveats=[
                *ASSUMPTIONS[:-1],
                "Run count includes published runs represented by observations only.",
                "Listing hashes are database-local pseudonyms; "
                "hashing is not proof of anonymization.",
                "Public samples contain at most 100 recent drop events; "
                "residuals at most 200 cars.",
                "Fair-price estimates are conditional medians "
                "with approximate residual ranges.",
            ],
        ),
        "index.json": report.index,
        "drops.json": DropSummary(
            status=drops.status,
            reason=drops.reason,
            observed_listings=drops.observed_listings,
            eligible_listings=drops.eligible_listings,
            drop_share=drops.drop_share,
            median_drop_pkr=drops.median_drop_pkr,
            median_drop_percent=drops.median_drop_percent,
            days_to_first_drop=drops.days_to_first_drop,
            drop_sizes_pkr=[event.drop_pkr for event in drops.events],
            drop_sizes_percent=[event.drop_percent for event in drops.events],
            survival=drops.survival,
        ),
        "seasonality.json": report.seasonality,
        "drivers.json": DriverSummary(
            status=drivers.status,
            reason=drivers.reason,
            listings_used=drivers.listings_used,
            omitted_predictors=drivers.omitted_predictors,
            coefficients=coefficients,
            linear_metrics=drivers.linear_metrics,
            boosting_metrics=drivers.boosting_metrics,
            baseline_metrics=drivers.baseline_metrics,
            diagnostics=diagnostics[:DIAGNOSTIC_LIMIT],
            diagnostics_total=len(diagnostics),
            diagnostics_by_make=drivers.diagnostics_by_make,
            shap_effects=drivers.shap_effects,
            dependence=drivers.dependence,
        ),
        "fairprice.json": FairPriceSummary(
            status=drivers.status, reason=drivers.reason, model=fair
        ),
        "models.json": _models(data),
        "listings_sample.json": SampleSummary(
            status="ok" if rows else "insufficient_data",
            reason=None if rows else "No usable observed price drops",
            total_events=len(events),
            rows=rows,
        ),
    }
    content = {key: body.model_dump(mode="json") for key, body in bodies.items()}
    assert_public(content)
    digest = hashlib.sha256(
        json.dumps(content, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    return {
        filename: CONTRACTS[filename].model_validate(
            {
                "generated_at": report.generated_at,
                "bundle_id": digest,
                "data": body,
            }
        )
        for filename, body in content.items()
    }


def serialize_exports(exports: dict[str, Envelope]) -> dict[str, bytes]:
    """Validate the entire bundle and its privacy/size budget before any writes."""
    if set(exports) != set(CONTRACTS):
        raise ValueError(
            "An export bundle must contain exactly the eight contracted files"
        )
    payloads = {}
    identities = set()
    content = {}
    for filename, model in CONTRACTS.items():
        validated = model.model_validate(exports[filename].model_dump(mode="json"))
        payload = validated.model_dump(mode="json")
        if filename == "models.json" and payload["data"]["city_price_parts"]:
            raise ValueError("Export requires full, unpartitioned city cohorts")
        content[filename] = payload["data"]
        identities.add((validated.bundle_id, validated.generated_at))
        assert_public(payload)
        encoded = encode(payload)
        if len(encoded) >= MAX_FILE_BYTES:
            if filename == "models.json":
                payloads.update(partition_models(payload))
                # Digest verification uses the full logical body, including all rows.
                content[filename] = validated.model_dump(mode="json")["data"]
                continue
            raise ValueError(
                f"{filename} exceeds the public file budget ({MAX_FILE_BYTES} bytes)"
            )
        payloads[filename] = encoded
    if len(identities) != 1:
        raise ValueError("Mixed export bundles are forbidden")
    digest = hashlib.sha256(
        json.dumps(content, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    if next(iter(identities))[0] != digest:
        raise ValueError("Export content digest does not match its bundle")
    return payloads


def write_exports(
    exports: dict[str, Envelope],
    *,
    output: Path,
    types_directory: Path,
) -> list[Path]:
    """Preflight all files, stage replacements, restore prior files on write failure."""
    payloads = serialize_exports(exports)
    if output.resolve() == types_directory.resolve():
        raise ValueError("Data and contract directories must differ")
    targets = {
        output / key: value for key, value in payloads.items() if key != "meta.json"
    }
    targets.update(
        {
            types_directory / key: value.encode("utf-8")
            for key, value in contract_artifacts().items()
        }
    )
    # Metadata goes last; readers can reject interrupted bundles by digest.
    targets[output / "meta.json"] = payloads["meta.json"]
    with ExitStack() as stack:
        stages = {}
        for directory in (output, types_directory):
            directory.mkdir(parents=True, exist_ok=True)
            stages[directory] = Path(
                stack.enter_context(
                    TemporaryDirectory(prefix=".tracker-", dir=directory)
                )
            )
        previous = {
            target: target.read_bytes() if target.exists() else None
            for target in targets
        }
        for index, (target, payload) in enumerate(targets.items()):
            (stages[target.parent] / str(index)).write_bytes(payload)
        changed = []
        try:
            for index, target in enumerate(targets):
                os.replace(stages[target.parent] / str(index), target)
                changed.append(target)
        except BaseException:
            for index, target in enumerate(reversed(changed)):
                old = previous[target]
                if old is None:
                    target.unlink()
                else:
                    restore = stages[target.parent] / f"restore-{index}"
                    restore.write_bytes(old)
                    os.replace(restore, target)
            raise
        prune_parts(output, set(payloads), previous.get(output / "models.json"))
    return list(targets)
