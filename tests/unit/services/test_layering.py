"""Layering (CLAUDE.md section 4): services depend on ports and domain, never on adapters."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[3] / "backend" / "vidgen"


def imported_modules(path: Path) -> set[str]:
    """Every module named in an import statement of ``path`` (also inside `if TYPE_CHECKING`)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def offenders(folder: str, forbidden: tuple[str, ...]) -> list[str]:
    """Files in ``folder`` that import any module starting with a forbidden prefix."""
    result = []
    for path in sorted((BACKEND / folder).glob("*.py")):
        for module in imported_modules(path):
            if module.startswith(forbidden):
                result.append(f"{path.name}: {module}")
    return result


def test_services_never_import_infrastructure() -> None:
    """DD-10: the services layer is wired to adapters from the outside."""
    assert offenders("services", ("vidgen.infrastructure",)) == []


def test_services_never_import_the_api_layer() -> None:
    """api -> services -> domain, never the other way."""
    assert offenders("services", ("vidgen.api",)) == []


def test_domain_imports_neither_services_adapters_nor_the_api() -> None:
    """The domain stays pure (ADR-008)."""
    forbidden = ("vidgen.services", "vidgen.infrastructure", "vidgen.api", "vidgen.worker")
    assert offenders("domain", forbidden) == []


@pytest.mark.parametrize("folder", ["services", "domain"])
def test_the_layer_folders_exist_and_are_scanned(folder: str) -> None:
    """Guards the test itself: an empty glob would make the checks above pass vacuously."""
    assert list((BACKEND / folder).glob("*.py"))
