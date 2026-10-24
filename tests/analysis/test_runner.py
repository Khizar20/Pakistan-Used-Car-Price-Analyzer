"""Read-only fixture-DB acceptance, typed output and complete bundle orchestration."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from typer.testing import CliRunner

from tests.analysis.synthetic import market
from tests.integration.test_scrape import NOW, Source
from tests.integration.test_storage_pipeline import collect
from tracker.analysis.runner import (
    AnalysisReport,
    analyze_frame,
    load_observations,
    write_analysis,
)
from tracker.cli import app
from tracker.storage.operations import inspect_database
from tracker.storage.repo import Repository

runner = CliRunner()


def test_cli_analyzes_two_day_fixture_without_writing_source(tmp_path, monkeypatch):
    path = tmp_path / "tracker.sqlite3"
    source = Source()
    collect(source, path, tmp_path / "cache1")
    source.html = source.html.replace('"price": 5900000', '"price": 5800000')
    source.html = source.html.replace("PKR 59", "PKR 58")
    collect(source, path, tmp_path / "cache2", 1)
    before = inspect_database(path)
    contents = path.read_bytes()
    monkeypatch.setattr("tracker.cli._now", lambda: NOW)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["analyze", "--database", str(path)])
    assert result.exit_code == 0, result.output
    output = tmp_path / "data/analysis" / f"{NOW:%Y%m%dT%H%M%S%fZ}" / "analysis.json"
    report = AnalysisReport.model_validate_json(output.read_text(encoding="utf-8"))
    assert report.observations == 2 and report.listings == 1
    assert report.observed_runs == 2 and report.observed_scopes == 1
    assert report.date_start == NOW.date().isoformat()
    assert report.drops.events[0].drop_pkr == 100000
    assert report.index.status == report.drivers.status == "insufficient_data"
    assert report.seasonality.seasonal.status == "insufficient_data"
    assert report.seasonal_series_basis == "unavailable"
    assert report.generated_at == NOW
    assert inspect_database(path) == before and path.read_bytes() == contents
    frame = load_observations(path)
    assert frame.features.iloc[0] and isinstance(frame.quality_flag.iloc[0], list)
    assert frame.price_pkr.tolist() == [5900000, 5800000]
    assert "source_listing_id" not in frame and "url_hash" not in frame
    assert "index: insufficient_data" in result.output
    repeated = runner.invoke(app, ["analyze", "--database", str(path)])
    assert repeated.exit_code == 1 and "FileExistsError" in repeated.output
    assert path.read_bytes() == contents


def test_orchestration_is_pure_and_selects_supported_quality_index(tmp_path):
    frame = market(240, 3)
    original = frame.copy(deep=True)
    report = analyze_frame(frame, generated_at=NOW)
    assert_frame_equal(frame, original)
    assert report.index.status == report.drivers.status == "ok"
    assert report.seasonal_series_basis == "quality_adjusted_index"
    assert report.seasonality.seasonal.weeks_available == 3
    output = write_analysis(report, tmp_path / "bundle")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert set(("index", "drops", "seasonality", "drivers")) <= payload.keys()
    assert AnalysisReport.model_validate(payload) == report
    with pytest.raises(FileExistsError):
        write_analysis(report, output.parent)
    with pytest.raises(ValueError, match="timezone-aware"):
        analyze_frame(frame, generated_at=datetime(2025, 1, 1))


def test_orchestration_falls_back_to_matched_cohorts():
    frame = market(240, 3).drop(columns="engine_cc")
    report = analyze_frame(frame, generated_at=NOW)
    assert report.index.raw.status == "ok"
    assert report.seasonal_series_basis == "matched_cohort_index"
    assert report.seasonality.seasonal.weeks_available == 3


def test_empty_database_and_invalid_frame_have_finite_typed_results(tmp_path):
    path = tmp_path / "empty.sqlite3"
    with Repository.open(path):
        pass
    result = runner.invoke(
        app, ["analyze", "--database", str(path), "--output", str(tmp_path / "empty")]
    )
    assert result.exit_code == 0, result.output
    report = AnalysisReport.model_validate_json(
        (tmp_path / "empty/analysis.json").read_text(encoding="utf-8")
    )
    assert report.observations == report.listings == report.observed_runs == 0
    assert report.date_start is report.date_end is None
    for name in ("index", "drops", "seasonality", "drivers"):
        assert getattr(report, name).status == "insufficient_data"
    invalid = analyze_frame(pd.DataFrame({"price_pkr": [1000000]}), generated_at=NOW)
    assert invalid.listings == 0 and invalid.date_start is None


@pytest.mark.parametrize("mode", ["missing", "corrupt", "schema"])
def test_cli_errors_do_not_create_or_modify_database(tmp_path: Path, mode: str):
    path = tmp_path / "bad.sqlite3"
    if mode == "corrupt":
        path.write_text("not SQLite", encoding="utf-8")
    elif mode == "schema":
        with sqlite3.connect(path) as connection:
            connection.execute("PRAGMA user_version = 99")
    before = path.read_bytes() if path.exists() else None
    result = runner.invoke(
        app, ["analyze", "--database", str(path), "--output", str(tmp_path / "result")]
    )
    assert result.exit_code == 1 and "Analysis failed" in result.output
    assert (path.read_bytes() if path.exists() else None) == before
    assert not (tmp_path / "result").exists()


@pytest.mark.parametrize("column", ["features", "quality_flag"])
def test_bad_json_is_rejected_and_unpublished_runs_are_excluded(tmp_path, column):
    path = tmp_path / "tracker.sqlite3"
    collect(Source(), path, tmp_path / "cache")
    table = "listings" if column == "features" else "snapshots"
    with sqlite3.connect(path) as connection:
        connection.execute(f"UPDATE {table} SET {column} = ?", ("[1]",))
    with pytest.raises(ValueError, match="Invalid normalized"):
        load_observations(path)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE scrape_runs SET status = 'failed'")
    assert load_observations(path).empty


def test_nullable_features_and_partial_runs_are_supported(tmp_path):
    path = tmp_path / "tracker.sqlite3"
    collect(Source(), path, tmp_path / "cache")
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE listings SET features = 'null'")
        connection.execute("UPDATE scrape_runs SET status = 'partial'")
    assert load_observations(path).features.iloc[0] is None
    stamp = NOW.astimezone(timezone.utc)
    assert analyze_frame(load_observations(path), generated_at=stamp).observations == 1
