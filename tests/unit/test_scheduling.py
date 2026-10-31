"""Preview the native Windows task without registering or starting it."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Task Scheduler installer")
def test_schedule_preview_has_safe_paths_and_catchup(tmp_path):
    python = tmp_path / ".venv/Scripts/pythonw.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    config = tmp_path / "data/daily/config.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}")
    script = Path(__file__).resolve().parents[2] / "scripts/install_daily_task.ps1"
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(script),
            "-ProjectRoot",
            str(tmp_path),
            "-Preview",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    task = json.loads(result.stdout)
    assert task["Execute"] == str(python)
    assert task["DailyAt"] == "09:00" and task["TimeZone"] == "Asia/Karachi"
    assert task["CatchUpAtLogon"] and task["StartWhenAvailable"]
    assert task["RunOnlyWhenLoggedOn"]
    assert (
        task["Arguments"] == f'-m tracker.cli refresh --config "{config}" --scheduled'
    )
