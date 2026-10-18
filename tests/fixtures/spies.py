"""Test spies for subprocess calls."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

import pytest


@dataclass(frozen=True)
class PopenCall:
    """One recorded ``subprocess.Popen`` invocation."""

    args: Any
    kwargs: dict[str, Any]


def record_popen(monkeypatch: pytest.MonkeyPatch) -> list[PopenCall]:
    """Record every ``subprocess.Popen`` call (``subprocess.run`` goes through it)."""
    calls: list[PopenCall] = []
    real = subprocess.Popen

    def factory(args: Any, *rest: Any, **kwargs: Any) -> Any:
        calls.append(PopenCall(args, dict(kwargs)))
        return real(args, *rest, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", factory)
    return calls
