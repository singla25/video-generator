"""BL-8 SS-M*: the app never applies migrations by itself (static check of backend/vidgen)."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[3] / "backend" / "vidgen"
SOURCES = sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)
WRITE_COMMANDS = {"upgrade", "downgrade", "stamp", "revision"}


def test_no_runtime_module_calls_the_alembic_command_api() -> None:
    """SS-M-N1: no ``command.upgrade`` (or downgrade/stamp) and no import of it in vidgen."""
    offenders: list[str] = []
    for path in SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in WRITE_COMMANDS:
                base = ast.unparse(node.value)
                if base.endswith("command") or base == "alembic":
                    offenders.append(f"{path.name}:{node.lineno} {base}.{node.attr}")
            if isinstance(node, ast.ImportFrom) and node.module == "alembic.command":
                offenders.append(f"{path.name}:{node.lineno} from alembic.command import")
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "alembic"
                and any(a.name == "command" for a in node.names)
            ):
                offenders.append(f"{path.name}:{node.lineno} from alembic import command")
    assert not offenders, offenders


def test_no_runtime_module_shells_out_to_the_alembic_cli() -> None:
    """SS-M-N2: no code string that runs the alembic CLI (messages for the Admin are allowed)."""
    offenders: list[str] = []
    for path in SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.List | ast.Tuple):
                words = [e.value for e in node.elts if isinstance(e, ast.Constant)]
                if "alembic" in words and any(w in WRITE_COMMANDS for w in words):
                    offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, offenders


def test_the_schema_adapter_exists_and_stays_read_only() -> None:
    """SS-M-E1: the adapter file exists and holds no DDL or write keywords."""
    adapter = PACKAGE / "infrastructure" / "db" / "schema_reader.py"
    assert adapter.exists(), "schema_reader.py is missing"
    text = adapter.read_text(encoding="utf-8").upper()
    for word in ("CREATE TABLE", "ALTER TABLE", "DROP ", "INSERT ", "UPDATE ", "DELETE "):
        assert word not in text, word
