"""Status, backup, migration and recovery commands operate safely offline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.integration.test_scrape import NOW, Source
from tracker import cli
from tracker.storage.operations import inspect_database
from tracker.storage.repo import Repository
from tracker.storage.staging import StagingStore

runner = CliRunner()


def test_migrate_status_json_and_backup_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "tracker.sqlite3"
    monkeypatch.setattr(cli, "_now", lambda: NOW)
    assert runner.invoke(cli.app, ["migrate", "--database", str(path)]).exit_code == 0
    with Repository.open(path) as repository:
        run_id = repository.start_run("pakwheels", NOW)
    result = runner.invoke(cli.app, ["status", "--database", str(path)])
    assert result.exit_code == 0 and "Unfinished run:" in result.output
    recovered = runner.invoke(
        cli.app, ["recover-run", str(run_id), "--database", str(path)]
    )
    assert recovered.exit_code == 0, recovered.output
    result = runner.invoke(cli.app, ["status", "--database", str(path), "--json"])
    payload = json.loads(result.output)
    assert payload["last_run"]["status"] == "interrupted"
    assert payload["total_errors"] == 1
    assert (
        "Last error:"
        in runner.invoke(cli.app, ["status", "--database", str(path)]).output
    )
    backup = runner.invoke(cli.app, ["backup", "--database", str(path)])
    assert backup.exit_code == 0, backup.output
    copied = list((tmp_path / "backups").glob("*.sqlite3"))
    assert len(copied) == 1 and inspect_database(copied[0]) == inspect_database(path)
    assert runner.invoke(cli.app, ["backup", "--database", str(path)]).exit_code == 1
    assert (
        runner.invoke(
            cli.app, ["recover-run", str(run_id), "--database", str(path)]
        ).exit_code
        == 1
    )


def test_status_and_recovery_do_not_initialize_missing_or_legacy_database(
    tmp_path: Path,
) -> None:
    path = tmp_path / "absent.sqlite3"
    assert runner.invoke(cli.app, ["status", "--database", str(path)]).exit_code == 1
    assert not path.exists()
    assert runner.invoke(cli.app, ["backup", "--database", str(path)]).exit_code == 1
    with StagingStore.open(path):
        pass
    result = runner.invoke(cli.app, ["status", "--database", str(path)])
    assert "Raw staging only" in result.output
    assert (
        runner.invoke(cli.app, ["recover-run", "1", "--database", str(path)]).exit_code
        == 1
    )
    assert inspect_database(path).schema_version == 0


def test_migration_rejects_invalid_database(tmp_path: Path) -> None:
    path = tmp_path / "bad.sqlite3"
    path.write_text("not a database", encoding="utf-8")
    assert runner.invoke(cli.app, ["migrate", "--database", str(path)]).exit_code == 1
    assert path.read_text(encoding="utf-8") == "not a database"


def test_cli_scrape_publishes_normalized_rows_and_reports_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = Source()
    path = tmp_path / "tracker.sqlite3"
    monkeypatch.setattr(cli, "_now", lambda: NOW)
    monkeypatch.setattr(
        cli, "PoliteClient", lambda **kwargs: source.client(kwargs["cache_dir"])
    )
    result = runner.invoke(
        cli.app,
        [
            "scrape",
            "--database",
            str(path),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--contact-email",
            "research@example.com",
            "--limit-pages",
            "1",
            "--model-path",
            "/used-cars/toyota-corolla/688",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "normalized listings. Run 1." in result.output
    assert inspect_database(path).snapshots == 1
    assert inspect_database(path).last_run.status == "success"
