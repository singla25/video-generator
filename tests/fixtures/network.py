"""A guard that makes any network use fail loudly (plan modal-mode-offline, AC7)."""

from __future__ import annotations

import socket
from typing import Any

import pytest

NETWORK_MESSAGE = "network access is forbidden in the Modal-mode tests"


class NetworkUsedError(AssertionError):
    """A test tried to open a socket connection."""


def _refuse(*_args: Any, **_kwargs: Any) -> Any:
    raise NetworkUsedError(NETWORK_MESSAGE)


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every connect, name lookup or ``create_connection`` raises ``NetworkUsedError``."""
    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)
