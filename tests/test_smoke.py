"""Phase 1 package and command-line smoke tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import tracker
from tracker.cli import app

runner = CliRunner()


def test_package_imports() -> None:
    """The installed package exposes its version."""
    assert tracker.__version__ == "0.1.0"


def test_tracker_help() -> None:
    """The installed console script renders help successfully."""
    executable_name = "tracker.exe" if os.name == "nt" else "tracker"
    executable = Path(sys.executable).with_name(executable_name)

    result = subprocess.run(
        [str(executable), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Collect and analyze Pakistan used-car asking prices" in result.stdout
    assert "scrape" in result.stdout
    assert "analyze" in result.stdout
    assert "export" in result.stdout


@pytest.mark.parametrize(
    ("command", "phase"),
    [("analyze", 5), ("export", 6)],
)
def test_future_phase_commands_are_explicit(command: str, phase: int) -> None:
    """Scaffold commands fail clearly until their implementation phase."""
    result = runner.invoke(app, [command])

    assert result.exit_code == 2
    assert f"'{command}' will be implemented in Phase {phase}." in result.output
