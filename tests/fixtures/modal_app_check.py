"""Checks on the source of a Modal app file, used on the real app and on made-up bad ones."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from tests.fixtures.modal_stub import Recorder, load_app

PIN = re.compile(r"^[A-Za-z0-9_.\-\[\]]+==[0-9][A-Za-z0-9_.!+\-]*$")
SECRET_PATTERNS = (
    re.compile(r"\bak-[A-Za-z0-9]{10,}"),  # Modal token id
    re.compile(r"\bas-[A-Za-z0-9]{10,}"),  # Modal token secret
    re.compile(r"\bhf_[A-Za-z0-9]{20,}"),  # Hugging Face token
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    re.compile(r"MODAL_TOKEN_(ID|SECRET)\s*=\s*['\"][^'\"]+['\"]"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
EMPTY = inspect.Parameter.empty


def secret_findings(source: str) -> list[str]:
    """Patterns of secret-looking text found in ``source`` (the text itself is not returned)."""
    return [p.pattern for p in SECRET_PATTERNS if p.search(source)]


def unpinned(pins: list[str]) -> list[str]:
    """Image entries without an exact ``==`` version."""
    return [p for p in pins if not PIN.match(p)]


def app_problems(path: Path, names: dict[str, list[tuple[str, object]]]) -> list[str]:
    """Everything wrong with the app at ``path``: names, signatures, pins, secrets."""
    problems: list[str] = []
    problems += [f"secret-like text: {p}" for p in secret_findings(path.read_text("utf-8"))]
    rec: Recorder = load_app(path)
    for fn, expected in names.items():
        if fn not in rec.functions:
            problems.append(f"missing function {fn}")
        elif rec.signature(fn) != expected:
            problems.append(f"wrong signature for {fn}")
    problems += [f"unpinned image entry {p}" for p in unpinned(rec.pins)]
    problems += [f"modal in image: {p}" for p in rec.pins if p.lower().startswith("modal")]
    return problems
