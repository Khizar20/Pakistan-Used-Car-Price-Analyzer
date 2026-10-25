"""Daily operation is tested without network calls or a real scheduler."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from filelock import FileLock, Timeout

from tracker.daily import CITY_PATHS, DailySettings, refresh

NOW = datetime(2026, 10, 25, 21, tzinfo=timezone.utc)


def settings(**changes):
    return DailySettings(
        contact_email="research@example.com",
        source_permission_confirmed=True,
        **changes,
    )


def test_daily_scope_backup_idempotence_and_next_pakistan_day(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/tracker.sqlite3").touch()
    calls = []

    def command(args, root):
        assert root == tmp_path
        calls.append(args)
        return 0

    assert refresh(tmp_path, settings(), now=lambda: NOW, command=command) == "ok"
    assert [call[0] for call in calls] == ["backup", "scrape", "export", "photos"]
    assert all(path in calls[1] for path in CITY_PATHS)
    assert calls[1][calls[1].index("--limit-pages") + 1] == "40"
    assert (
        refresh(tmp_path, settings(), now=lambda: NOW, command=command)
        == "already_completed"
    )
    assert len(calls) == 4
    assert (
        refresh(tmp_path, settings(), force=True, now=lambda: NOW, command=command)
        == "ok"
    )
    assert (
        refresh(
            tmp_path, settings(), now=lambda: NOW + timedelta(days=1), command=command
        )
        == "ok"
    )
    report = json.loads((tmp_path / "data/daily/status.json").read_text())
    assert report["completed_key"].startswith("2026-10-27:")
    assert "research@example.com" not in json.dumps(report)


@pytest.mark.parametrize("failed", ["backup", "scrape", "export"])
def test_failure_preserves_last_success_and_can_retry(tmp_path, failed):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/tracker.sqlite3").touch()
    refresh(tmp_path, settings(), now=lambda: NOW, command=lambda *_: 0)
    calls = []

    def command(args, _root):
        calls.append(args[0])
        return int(args[0] == failed)

    with pytest.raises(RuntimeError):
        refresh(tmp_path, settings(), force=True, now=lambda: NOW, command=command)
    report = json.loads((tmp_path / "data/daily/status.json").read_text())
    assert report["status"] == "failed" and report["step"] == failed
    assert report["last_success_at"] == NOW.isoformat()
    if failed != "export":
        assert "export" not in calls
    assert (
        refresh(
            tmp_path,
            settings(),
            now=lambda: NOW + timedelta(days=1),
            command=lambda *_: 0,
        )
        == "ok"
    )


def test_permission_lock_clock_and_retention(tmp_path):
    with pytest.raises(ValueError, match="permission"):
        refresh(
            tmp_path,
            DailySettings(
                contact_email="a@example.com", source_permission_confirmed=False
            ),
        )
    state = tmp_path / "data/daily"
    state.mkdir(parents=True)
    with FileLock(state / "worker.lock"):
        with pytest.raises(Timeout):
            refresh(tmp_path, settings())
    with pytest.raises(ValueError, match="aware"):
        refresh(tmp_path, settings(), now=lambda: datetime(2026, 10, 25))
    backups = tmp_path / "data/backups"
    backups.mkdir()
    for i in range(10):
        (backups / f"tracker-{i:02}.sqlite3").touch()
    (backups / "manual.sqlite3").touch()
    refresh(tmp_path, settings(), now=lambda: NOW, command=lambda *_: 0)
    assert len(list(backups.glob("tracker-*.sqlite3"))) == 7
    assert (backups / "manual.sqlite3").exists()


@pytest.mark.parametrize("pages", [0, 3, 41, 104])
def test_daily_scope_is_balanced_and_bounded(pages):
    with pytest.raises(ValueError):
        settings(limit_pages=pages)


def test_photo_failure_keeps_prices_and_reports_separate_failure(tmp_path):
    assert (
        refresh(
            tmp_path,
            settings(),
            now=lambda: NOW,
            command=lambda args, _: int(args[0] == "photos"),
        )
        == "ok"
    )
    report = json.loads((tmp_path / "data/daily/status.json").read_text())
    assert report["photo_queue_status"] == "failed" and report["status"] == "ok"


def test_command_logs_and_uses_current_venv(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from tracker.daily import _command

    (tmp_path / "data/daily").mkdir(parents=True)

    def run(args, **kwargs):
        assert args[:3] == [sys.executable, "-m", "tracker.cli"]
        assert kwargs["timeout"] == 2700 and kwargs["cwd"] == tmp_path
        kwargs["stdout"].write("bounded collection output")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("tracker.daily.subprocess.run", run)
    assert _command(["scrape"], tmp_path) == 0
    assert "bounded collection" in (tmp_path / "data/daily/scrape.log").read_text()
