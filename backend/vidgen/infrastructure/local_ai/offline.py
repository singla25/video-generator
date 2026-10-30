"""Block outgoing network access while models run (AC8: voter data never leaves the machine)."""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from vidgen.infrastructure.local_ai.errors import OfflineViolationError

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

_lock = threading.Lock()
_depth = 0
_saved: dict[str, Any] = {}


def _is_local(host: object) -> bool:
    """True for loopback names; the local Redis and database stay reachable."""
    return isinstance(host, str) and host in LOOPBACK_HOSTS


def _blocked(what: str) -> OfflineViolationError:
    return OfflineViolationError(f"network access blocked in local AI mode: {what}")


def _install() -> None:
    _saved["create_connection"] = socket.create_connection
    _saved["getaddrinfo"] = socket.getaddrinfo
    _saved["connect"] = socket.socket.connect
    original_gai: Callable[..., Any] = socket.getaddrinfo
    original_connect: Callable[..., Any] = socket.socket.connect

    def create_connection(address: tuple[str, int], *args: Any, **kwargs: Any) -> socket.socket:
        if not _is_local(address[0]):
            raise _blocked(f"connect to {address[0]}")
        result: socket.socket = _saved["create_connection"](address, *args, **kwargs)
        return result

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if not _is_local(host):
            raise _blocked(f"DNS lookup of {host!r}")
        return original_gai(host, *args, **kwargs)

    def connect(self: socket.socket, address: Any) -> None:
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(address[0]):
            raise _blocked(f"connect to {address[0]}")
        original_connect(self, address)

    socket.create_connection = create_connection  # type: ignore[assignment]
    socket.getaddrinfo = getaddrinfo
    socket.socket.connect = connect  # type: ignore[method-assign,assignment]


def _uninstall() -> None:
    socket.create_connection = _saved.pop("create_connection")
    socket.getaddrinfo = _saved.pop("getaddrinfo")
    socket.socket.connect = _saved.pop("connect")  # type: ignore[method-assign]


@contextmanager
def offline_only() -> Iterator[None]:
    """Refuse non-loopback connections and DNS lookups; always restored on exit (nestable)."""
    global _depth
    with _lock:
        if _depth == 0:
            _install()
        _depth += 1
    try:
        yield
    finally:
        with _lock:
            _depth -= 1
            if _depth == 0:
                _uninstall()
