"""Explicitly regenerate synthetic browser fixtures; never touch production data."""

import json
from datetime import datetime, timezone
from pathlib import Path

from tests.analysis.synthetic import market
from tracker.analysis.drivers import FairPriceModel, predict_fair_price
from tracker.export.writer import build_exports, serialize_exports


def main() -> None:
    destination = Path("web/tests/fixtures")
    destination.mkdir(parents=True, exist_ok=True)
    frame = market(240, 6)
    exports = build_exports(
        frame, generated_at=datetime(2026, 10, 25, tzinfo=timezone.utc)
    )
    for filename, payload in serialize_exports(exports).items():
        (destination / filename).write_bytes(payload)
    fair = exports["fairprice.json"].model_dump(mode="json")["data"]["model"]
    private = FairPriceModel.model_validate(
        {
            **fair,
            "spec": {
                "numeric": fair["spec"]["numeric"],
                "categories": fair["spec"]["categories"],
                "names": fair["spec"]["terms"],
            },
        }
    )
    cars = frame.drop_duplicates("listing_id", keep="last").iloc[:20][
        ["make", "model", "model_year", "mileage_km", "transmission", "city"]
    ]
    references = [
        {"car": car, **prediction.model_dump()}
        for car, prediction in zip(
            cars.to_dict("records"),
            predict_fair_price(cars, private),
            strict=True,
        )
    ]
    (destination / "fair-reference.json").write_text(
        json.dumps({"model": fair, "references": references}, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
