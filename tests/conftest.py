"""Network access is prohibited unless a test explicitly carries the live marker."""

from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def offline_by_default(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    if request.node.get_closest_marker("live"):
        return

    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("Network access is disabled in default tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
