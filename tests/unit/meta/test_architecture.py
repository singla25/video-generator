"""Code-quality rules from CLAUDE.md section 4, checked on the source tree (AC19)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[3] / "backend"
PACKAGE = BACKEND / "vidgen"
SOURCES = sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)
MAX_LINES = 300
DOMAIN_FORBIDDEN = (
    "sqlalchemy", "fastapi", "starlette", "pydantic", "psycopg", "dramatiq", "redis",
    "openpyxl", "PIL", "cryptography", "argon2", "itsdangerous", "uvicorn", "httpx",
    "subprocess", "socket", "requests",
)  # fmt: skip
HOME_FOLDERS = ("Users", "home", "tmp")


def parse(path: Path) -> ast.Module:
    """Parse a source file."""
    return ast.parse(path.read_text(encoding="utf-8"))


def relative(path: Path) -> str:
    """Path relative to backend/ for messages."""
    return path.relative_to(BACKEND).as_posix()


def test_sources_were_found() -> None:
    """Guards the checks below against an empty glob."""
    assert len(SOURCES) > 50


def test_domain_imports_no_framework_or_io_modules() -> None:
    """TT-AC19-E1 (ADR-008)."""
    bad = []
    for path in (PACKAGE / "domain").glob("*.py"):
        for node in ast.walk(parse(path)):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            bad += [f"{path.name}: {n}" for n in names if n.split(".")[0] in DOMAIN_FORBIDDEN]
    assert bad == []


@pytest.mark.parametrize("path", SOURCES, ids=relative)
def test_no_print_and_no_bare_except(path: Path) -> None:
    """TT-AC19-E2: logging module only; errors are never swallowed anonymously."""
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print":
            pytest.fail(f"{relative(path)}:{node.lineno} uses print()")
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            pytest.fail(f"{relative(path)}:{node.lineno} has a bare except")


ABSOLUTE_PATH = re.compile(rf"""["']/(?:{"|".join(HOME_FOLDERS)})/""")
LITERAL_URL = re.compile(r"""["']https?://(?!127\.0\.0\.1|localhost)""")
SECRET_ASSIGNMENT = re.compile(
    r"""(?i)(password|secret|api_key|token)\s*(?::[^=]+)?=\s*["'][^"']{6,}["']"""
)


@pytest.mark.parametrize("path", SOURCES, ids=relative)
def test_no_hard_coded_absolute_paths_external_urls_or_secrets(path: Path) -> None:
    """TT-AC19-E3: configuration comes from settings."""
    source = path.read_text(encoding="utf-8")
    assert not ABSOLUTE_PATH.search(source), f"{relative(path)} has an absolute path"
    assert not LITERAL_URL.search(source), f"{relative(path)} has an external URL"
    if path.name != "settings.py":
        assert not SECRET_ASSIGNMENT.search(source), f"{relative(path)} looks like a secret"


@pytest.mark.parametrize("path", SOURCES, ids=relative)
def test_files_stay_short(path: Path) -> None:
    """TT-AC19-E4: about 300 lines at most."""
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines <= MAX_LINES, f"{relative(path)} has {lines} lines"


def public_definitions(
    tree: ast.Module,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]:
    """Public functions and classes at module level, and public methods of public classes."""
    found: list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if node.name.startswith("_"):
                continue
            found.append(node)
            if isinstance(node, ast.ClassDef):
                found += [
                    child
                    for child in node.body
                    if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
                    and not child.name.startswith("_")
                ]
    return found


@pytest.mark.parametrize("path", SOURCES, ids=relative)
def test_public_modules_classes_and_functions_have_docstrings(path: Path) -> None:
    """TT-AC19-E4."""
    tree = parse(path)
    if tree.body:
        assert ast.get_docstring(tree), f"{relative(path)} has no module docstring"
    missing = [
        f"{node.name}:{node.lineno}"
        for node in public_definitions(tree)
        if not ast.get_docstring(node)
    ]
    assert missing == [], f"{relative(path)} lacks docstrings: {missing}"


def test_no_test_reads_the_samples_folder() -> None:
    """TT-AC19-E5: automated tests use synthetic data only."""
    tests_root = Path(__file__).resolve().parents[2]
    offenders = []
    for path in tests_root.rglob("*.py"):
        if path.name == "test_architecture.py":
            continue
        if re.search(r"""["']samples[/"']""", path.read_text(encoding="utf-8")):
            offenders.append(path.name)
    assert offenders == []
