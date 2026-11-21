"""AC2: the Modal app lives outside the package and nothing in the package imports it."""

from __future__ import annotations

import ast

from tests.unit.modal_mode.conftest import APP_FILE, ROOT, VIDGEN_DIR


def test_the_app_file_exists_outside_the_vidgen_package() -> None:
    assert APP_FILE.is_file()
    assert VIDGEN_DIR not in APP_FILE.parents


def test_nothing_under_vidgen_imports_modal_app() -> None:
    offenders = []
    for path in VIDGEN_DIR.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            if any(n == "modal_app" or n.startswith("modal_app.") for n in names):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_no_module_under_vidgen_imports_modal_at_the_top_level() -> None:
    """``modal`` may only be imported inside functions (the optional ``cloud`` extra)."""
    offenders = []
    for path in VIDGEN_DIR.rglob("*.py"):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            if any(n == "modal" or n.startswith("modal.") for n in names):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
