"""AC7: the guard really blocks sockets, so a hidden live call would fail a test."""

from __future__ import annotations

import socket

import pytest

from tests.fixtures.network import NetworkUsedError


def test_connecting_a_socket_raises_in_modal_mode_tests() -> None:
    with pytest.raises(NetworkUsedError):
        socket.create_connection(("203.0.113.1", 443), timeout=0.1)


def test_a_name_lookup_raises_too() -> None:
    with pytest.raises(NetworkUsedError):
        socket.getaddrinfo("example.invalid", 443)


def test_a_raw_socket_connect_raises() -> None:
    with socket.socket() as raw, pytest.raises(NetworkUsedError):
        raw.connect(("203.0.113.1", 443))
