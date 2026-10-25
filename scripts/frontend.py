"""Run npm through the native host, including from Windows/MSYS Make."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_frontend(action: str, platform: str = sys.platform) -> int:
    if action not in {"ci", "check"}:
        raise ValueError("Supported frontend actions: ci, check")
    executable = shutil.which("npm.cmd" if platform == "win32" else "npm")
    if executable is None:
        raise RuntimeError("Install Node 20.19+ with npm before frontend setup/checks")
    arguments = [executable, "ci"] if action == "ci" else [executable, "run", "check"]
    return subprocess.run(arguments, cwd=ROOT / "web", check=False).returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("ci", "check"))
    return run_frontend(parser.parse_args(argv).action)


if __name__ == "__main__":
    raise SystemExit(main())
