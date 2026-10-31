"""Bounded daily collection and local export with an OS-released worker lock."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field

CITY_PATHS = (
    "/used-cars/karachi/24857",
    "/used-cars/lahore/24858",
    "/used-cars/islamabad/24856",
    "/used-cars/rawalpindi/24831",
)


class DailySettings(BaseModel):
    """Local operator settings; permission records and contact stay private."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    contact_email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    source_permission_confirmed: bool
    limit_pages: int = Field(default=40, ge=4, le=100, multiple_of=4)
    max_new_details: int = Field(default=60, ge=0, le=300)


def _command(arguments: list[str], root: Path) -> int:
    with (root / "data/daily" / f"{arguments[0]}.log").open(
        "w", encoding="utf-8"
    ) as log:
        return subprocess.run(
            [sys.executable, "-m", "tracker.cli", *arguments],
            cwd=root,
            check=False,
            timeout=2700,
            stdout=log,
            stderr=subprocess.STDOUT,
        ).returncode


def _save(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def refresh(
    root: Path,
    settings: DailySettings,
    *,
    force: bool = False,
    scheduled: bool = False,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    command: Callable[[list[str], Path], int] = _command,
) -> str:
    """Export only after successful collection; keep the last good bundle on failure.

    The same Pakistan day/configuration is idempotent. A forced run can collect
    more pages, but SQLite still records at most one snapshot per listing/day.
    """
    if not settings.source_permission_confirmed:
        raise ValueError("Source permission must be confirmed before collection")
    root = root.resolve(strict=True)
    state = root / "data/daily"
    state.mkdir(parents=True, exist_ok=True)
    with FileLock(state / "worker.lock", timeout=0):
        stamp = now()
        if stamp.utcoffset() is None:
            raise ValueError("Clock must be timezone aware")
        if (
            scheduled
            and not force
            and stamp.astimezone(ZoneInfo("Asia/Karachi")).hour < 9
        ):
            return "not_due"
        day = stamp.astimezone(ZoneInfo("Asia/Karachi")).date().isoformat()
        digest = hashlib.sha256(settings.model_dump_json().encode()).hexdigest()
        path = state / "status.json"
        previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not force and previous.get("completed_key") == f"{day}:{digest}":
            return "already_completed"
        report: dict[str, object] = {
            "status": "running",
            "started_at": stamp.isoformat(),
            "last_success_at": previous.get("last_success_at"),
            "completed_key": previous.get("completed_key"),
            "step": "backup",
        }
        _save(path, report)
        arguments = [
            "scrape",
            "--contact-email",
            settings.contact_email,
            "--limit-pages",
            str(settings.limit_pages),
            "--max-new-details",
            str(settings.max_new_details),
        ]
        for city in CITY_PATHS:
            arguments.extend(["--model-path", city])
        try:
            if (root / "data/tracker.sqlite3").exists():
                if command(["backup"], root):
                    raise RuntimeError("backup")
            report["step"] = "scrape"
            _save(path, report)
            if command(arguments, root):
                raise RuntimeError("scrape")
            report["step"] = "export"
            _save(path, report)
            if command(["export"], root):
                raise RuntimeError("export")
            report["step"] = "photos"
            _save(path, report)
            report["photo_queue_status"] = (
                "failed"
                if command(
                    [
                        "photos",
                        "--contact-email",
                        settings.contact_email,
                        "--limit",
                        "12",
                    ],
                    root,
                )
                else "ok"
            )
        except Exception as exc:
            report.update(status="failed", error_type=type(exc).__name__)
            _save(path, report)
            raise
        report.update(
            status="ok",
            finished_at=now().isoformat(),
            last_success_at=now().isoformat(),
            completed_key=f"{day}:{digest}",
        )
        _save(path, report)
        # Retain a week of daily pre-collection backups, never arbitrary files.
        backups = sorted((root / "data/backups").glob("tracker-*.sqlite3"))
        for obsolete in backups[:-7]:
            obsolete.unlink()
        return "ok"
