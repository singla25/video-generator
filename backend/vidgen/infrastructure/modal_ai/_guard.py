"""Shared handling of remote-call failures."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from vidgen.infrastructure.modal_ai.errors import RemoteAuthError

T = TypeVar("T")


def call_remote(fn: Callable[[], T]) -> T:
    """Run a remote call; replace an auth error by a clean one (drops message, cause, context)."""
    try:
        return fn()
    except RemoteAuthError:
        pass  # re-raised below, outside the except block, so no cause/context is kept
    raise RemoteAuthError() from None
