"""Read-only inspection and consistent, non-destructive online backups."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tracker.storage.operations import backup_database, inspect_database
from tracker.storage.repo import Repository
from tracker.storage.staging import StagingStore

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def test_status_and_backup_preserve_run_history_and_legacy_data(tmp_path: Path) -> None:
    path = tmp_path / "space folder" / "tracker.sqlite3"
    with StagingStore.open(path):
        pass
    with Repository.open(path) as repository:
        run_id = repository.start_run("pakwheels", NOW)
        repository.fail_run(run_id, NOW, "TimeoutException")
    before = inspect_database(path)
    assert before.schema_version == 1
    assert before.runs == 1 and before.total_errors == 1
    assert before.last_run.error_summary == "TimeoutException"
    backup = backup_database(path, tmp_path / "backup" / "copy.sqlite3")
    assert inspect_database(backup) == before
    with sqlite3.connect(backup) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert (
            connection.execute("SELECT COUNT(*) FROM raw_vehicles").fetchone()[0] == 0
        )
    assert inspect_database(path) == before


def test_status_of_unmigrated_staging_and_running_scrape(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with StagingStore.open(path):
        pass
    status = inspect_database(path)
    assert status.schema_version == 0 and status.last_run is None
    with Repository.open(path) as repository:
        run_id = repository.start_run("pakwheels", NOW)
        status = inspect_database(path)
        assert status.unfinished_run_id == run_id
        assert status.last_run.status == "running"


def test_online_backup_includes_committed_wal_records(tmp_path: Path) -> None:
    path = tmp_path / "wal.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("CREATE TABLE important (value TEXT)")
        connection.execute("INSERT INTO important VALUES ('committed in WAL')")
        connection.commit()
        assert Path(str(path) + "-wal").exists()
        backup = backup_database(path, tmp_path / "wal-backup.sqlite3")
        with sqlite3.connect(backup) as copied:
            assert (
                copied.execute("SELECT value FROM important").fetchone()[0]
                == "committed in WAL"
            )


def test_backup_refuses_overwrite_or_same_file(tmp_path: Path) -> None:
    path = tmp_path / "source.sqlite3"
    with Repository.open(path):
        pass
    with pytest.raises(ValueError, match="differ"):
        backup_database(path, path)
    destination = tmp_path / "existing.txt"
    destination.write_text("user content", encoding="utf-8")
    with pytest.raises(FileExistsError):
        backup_database(path, destination)
    assert destination.read_text(encoding="utf-8") == "user content"


def test_missing_invalid_or_directory_sources_do_not_create_valid_looking_backups(
    tmp_path: Path,
) -> None:
    absent = tmp_path / "absent.sqlite3"
    with pytest.raises(FileNotFoundError):
        inspect_database(absent)
    assert not absent.exists()
    with pytest.raises(ValueError, match="file"):
        inspect_database(tmp_path)
    invalid = tmp_path / "invalid.sqlite3"
    invalid.write_text("not a database", encoding="utf-8")
    backup = tmp_path / "invalid-backup.sqlite3"
    with pytest.raises(sqlite3.DatabaseError):
        backup_database(invalid, backup)
    assert not backup.exists()
    assert invalid.read_text(encoding="utf-8") == "not a database"


@pytest.mark.parametrize("version,message", [(1, "missing"), (2, "newer")])
def test_status_rejects_invalid_schema_version(
    tmp_path: Path, version: int, message: str
) -> None:
    path = tmp_path / "bad.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version = {version}")
    with pytest.raises(ValueError, match=message):
        inspect_database(path)
