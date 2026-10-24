"""A clean setup must install the pinned build and runtime requirements."""

from __future__ import annotations

from pathlib import Path

import tomli
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def test_lock_contains_runtime_and_build_requirements() -> None:
    root = Path(__file__).parents[2]
    config = tomli.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    locked = {
        canonicalize_name(requirement.name): requirement
        for line in (root / "requirements.lock")
        .read_text(encoding="utf-8")
        .splitlines()
        if line and not line.startswith("#")
        for requirement in [Requirement(line)]
    }
    for spec in config["project"]["dependencies"] + config["build-system"]["requires"]:
        requirement = Requirement(spec)
        assert (
            locked[canonicalize_name(requirement.name)].specifier
            == requirement.specifier
        )
