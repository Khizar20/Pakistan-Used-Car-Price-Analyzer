"""Windows npm selection, stable working directory and quality-gate failures."""

import subprocess

import pytest

from scripts import frontend


@pytest.mark.parametrize(
    "platform,expected,action",
    [
        ("win32", "npm.cmd", "check"),
        ("linux", "npm", "ci"),
    ],
)
def test_native_npm_runs_in_web_and_preserves_failed_exit(
    monkeypatch,
    tmp_path,
    platform,
    expected,
    action,
):
    lookups = []

    def which(command):
        lookups.append(command)
        return command

    calls = []

    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return subprocess.CompletedProcess(arguments, 7)

    monkeypatch.setattr(frontend.shutil, "which", which)
    monkeypatch.setattr(frontend.subprocess, "run", run)
    monkeypatch.chdir(tmp_path)
    assert frontend.run_frontend(action, platform) == 7
    assert lookups == [expected]
    assert calls[0][1] == {"cwd": frontend.ROOT / "web", "check": False}
    assert calls[0][0] == (
        [expected, "ci"] if action == "ci" else [expected, "run", "check"]
    )


def test_missing_npm_and_unknown_actions_fail_explicitly(monkeypatch):
    monkeypatch.setattr(frontend.shutil, "which", lambda command: None)
    with pytest.raises(RuntimeError, match="Node 20.19"):
        frontend.main(["check"])
    with pytest.raises(ValueError):
        frontend.run_frontend("unexpected")
