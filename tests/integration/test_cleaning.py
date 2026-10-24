"""Phase 3 acceptance: a raw batch matches an independently authored golden frame."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from tracker.cleaning.batch import clean_batch
from tracker.cleaning.models import CleanListing
from tracker.models import RawListing

FIXTURES = Path(__file__).parents[1] / "fixtures/cleaning"


def test_raw_fixture_batch_matches_golden_typed_frame() -> None:
    raw = json.loads((FIXTURES / "raw_batch.json").read_text(encoding="utf-8"))
    golden = json.loads((FIXTURES / "expected_batch.json").read_text(encoding="utf-8"))
    inputs = [RawListing.model_validate(row) for row in raw]
    expected = pd.DataFrame(
        [CleanListing.model_validate(row).model_dump() for row in golden["rows"]]
    ).astype(golden["dtypes"])
    actual = clean_batch(inputs)
    assert_frame_equal(actual, expected, check_dtype=True)
    assert_frame_equal(clean_batch(actual), expected, check_dtype=True)
    assert len(actual) == len(raw)
    assert inputs[0].make == " toyotta "
