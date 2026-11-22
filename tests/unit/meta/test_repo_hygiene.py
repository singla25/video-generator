"""Static checks that sensitive file types stay out of git and out of the Docker build context.

Database dumps and key files can hold encrypted personal data or secrets, so both ignore files
must list them. No Docker or git process is needed.
"""

from __future__ import annotations

import pytest

from tests.unit.meta.conftest import ROOT

SENSITIVE_PATTERNS = ("*.sql", "*.dump", "*.pem", "*.key")


def _active_lines(name: str) -> set[str]:
    """Non-empty, non-comment lines of an ignore file."""
    text = (ROOT / name).read_text(encoding="utf-8")
    return {line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")}


@pytest.mark.parametrize("ignore_file", [".gitignore", ".dockerignore"])
@pytest.mark.parametrize("pattern", SENSITIVE_PATTERNS)
def test_sensitive_pattern_is_ignored(ignore_file: str, pattern: str) -> None:
    """Dumps and key files are never committed and never copied into an image."""
    lines = _active_lines(ignore_file)
    assert pattern in lines or f"**/{pattern}" in lines, f"{ignore_file} must ignore {pattern}"


def test_env_example_stays_trackable() -> None:
    """The placeholder file is still allowed through the .env rules."""
    assert "!.env.example" in _active_lines(".gitignore")
