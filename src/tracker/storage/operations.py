"""Read-only database status and non-overwriting SQLite online backups."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from tracker.storage.schema import SCHEMA_VERSION


@dataclass(frozen=True)
class RunStatus:
    id: int
    status: str
    started_at: str
    finished_at: str | None
    pages_fetched: int
    listings_seen: int
    errors: int
    error_summary: str | None


@dataclass(frozen=True)
class DatabaseStatus:
    schema_version: int
    listings: int
    active_listings: int
    snapshots: int
    runs: int
    raw_listings: int
    total_errors: int
    unfinished_run_id: int | None
    last_run: RunStatus | None


def _readonly(path: Path) -> sqlite3.Connection:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("Database path must be a file")
    return sqlite3.connect(resolved.as_uri() + "?mode=ro", uri=True, timeout=30)


def inspect_database(path: Path) -> DatabaseStatus:
    """Inspect normalized or legacy staging databases without creating/migrating."""
    connection = _readonly(path)
    try:
        connection.execute("BEGIN")
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version > SCHEMA_VERSION:
            raise ValueError("Database schema is newer than this tracker supports")
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        normalized = {"listings", "snapshots", "scrape_runs"}
        if version == SCHEMA_VERSION and not normalized <= tables:
            raise ValueError("Versioned database is missing normalized tables")
        counts = {
            name: int(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            if name in tables
            else 0
            for name in ("listings", "snapshots", "scrape_runs", "raw_vehicles")
        }
        active = (
            int(
                connection.execute(
                    "SELECT COUNT(*) FROM listings WHERE is_active = 1"
                ).fetchone()[0]
            )
            if "listings" in tables
            else 0
        )
        last = unfinished = None
        total_errors = 0
        if "scrape_runs" in tables:
            row = connection.execute(
                "SELECT id, status, started_at, finished_at, pages_fetched, "
                "listings_seen, errors, error_summary FROM scrape_runs "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row:
                last = RunStatus(
                    int(row[0]),
                    str(row[1]),
                    str(row[2]),
                    row[3],
                    int(row[4]),
                    int(row[5]),
                    int(row[6]),
                    row[7],
                )
            running = connection.execute(
                "SELECT id FROM scrape_runs WHERE status = 'running'"
            ).fetchone()
            unfinished = int(running[0]) if running else None
            total_errors = int(
                connection.execute(
                    "SELECT COALESCE(SUM(errors), 0) FROM scrape_runs"
                ).fetchone()[0]
            )
        return DatabaseStatus(
            version,
            counts["listings"],
            active,
            counts["snapshots"],
            counts["scrape_runs"],
            counts["raw_vehicles"],
            total_errors,
            unfinished,
            last,
        )
    finally:
        connection.close()


def backup_database(source: Path, destination: Path) -> Path:
    """Copy a consistent online SQLite snapshot; refuse existing destinations."""
    source_path = source.resolve(strict=True)
    destination_path = destination.resolve()
    if source_path == destination_path:
        raise ValueError("Backup destination must differ from the source")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(destination_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(handle)
    try:
        original = _readonly(source_path)
        try:
            copy = sqlite3.connect(destination_path)
            try:
                original.backup(copy)
                if copy.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Backup integrity check failed")
            finally:
                copy.close()
        finally:
            original.close()
    except BaseException:
        # Only the destination just created exclusively by this function is removed.
        destination_path.unlink(missing_ok=True)
        raise
    return destination_path
