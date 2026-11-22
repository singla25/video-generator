"""Rules that keep the backend suite safe under ``pytest -n N``.

See docs/test-tree/xdist-isolation.md.

Static and fast: no Docker, no database. Each xdist worker is its own pytest session, so anything
shared between workers (database names, compose project names, repo files, wall-clock bounds) must
be made per-worker or generous.
"""

from __future__ import annotations

import ast
import re
from functools import cache, lru_cache
from pathlib import Path

import pytest

from tests.unit.meta.conftest import ROOT

TESTS = ROOT / "tests"
REAL_DB_NAMES = ("vidgen", "vidgen_demo", "vidgen_test", "vidgen_migration_test")
# Files that may mention a real database name: they assert on the app's own defaults or on
# documented, protected names and never connect to them.
DB_NAME_ALLOW = {
    "tests/unit/meta/test_native_worker.py",  # asserts the default URL the installer writes
    "tests/unit/meta/test_xdist_isolation.py",  # this file
    "tests/integration/conftest.py",  # the protected-name list itself
    "tests/integration/db/test_migration_0003_providers.py",  # asserts the names are NOT used
    "tests/e2e/test_docker_stack_e2e.py",  # demo settings for the isolated compose stack
}
# Test files that legitimately point at a repo path for reading only are not listed here: the
# scan below flags writes, so the allow-list stays empty unless a real need appears.
REPO_WRITE_ALLOW: set[str] = set()
TIMING_MODULES = {
    "tests/unit/name_detection/test_sound_key.py": [
        "test_two_hundred_character_input_is_fast_and_exact"
    ],
    "tests/unit/name_detection/test_select_name_slot.py": [
        "test_two_thousand_words_are_matched_quickly"
    ],
    "tests/unit/domain/test_row_validation.py": [
        "test_ten_thousand_character_name_is_rejected_quickly",
        "test_duplicate_detection_scales_linearly",
    ],
    "tests/integration/ffmpeg/test_encoder_errors.py": [
        "test_hanging_ffmpeg_is_killed_and_reported_as_render_timeout"
    ],
    "tests/integration/ingest/test_sheet_scale.py": [
        "test_one_thousand_rows_read_and_validate_in_under_three_seconds",
        "test_thousand_rows_with_all_duplicate_ids_is_still_fast",
    ],
    "tests/integration/api/test_batches_extra.py": [
        "test_status_of_a_hundred_thousand_row_batch_is_answered_quickly"
    ],
    "tests/integration/api/test_batches_create.py": [
        "test_a_thousand_row_sheet_is_validated_quickly"
    ],
    "tests/integration/api/test_batches_control.py": [
        "test_cancelling_a_thousand_row_batch_is_a_bulk_operation"
    ],
}


SKIP_DIRS = {"frontend", "node_modules", "__pycache__", ".venv"}


@lru_cache(maxsize=1)
def repo_test_files() -> tuple[Path, ...]:
    """Every backend test module (the Playwright/Vitest tree is not run by pytest), cached."""
    return tuple(
        sorted(p for p in TESTS.rglob("*.py") if not SKIP_DIRS & set(p.relative_to(TESTS).parts))
    )


@cache
def parsed(path: Path) -> tuple[str, ast.Module]:
    """Source and syntax tree of one file, parsed once per run."""
    source = path.read_text(encoding="utf-8")
    return source, ast.parse(source)


def rel(path: Path) -> str:
    """Repo-relative POSIX path used in the allow-lists."""
    return path.relative_to(ROOT).as_posix()


# --- database names ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("worker", "expected"),
    [("gw0", "gw0"), ("gw13", "gw13"), (None, "master")],
)
def test_database_names_carry_the_xdist_worker_id(
    monkeypatch: pytest.MonkeyPatch, worker: str | None, expected: str
) -> None:
    from tests.integration import conftest as c

    if worker is None:
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    else:
        monkeypatch.setenv("PYTEST_XDIST_WORKER", worker)
    name = c._random_name("vidgen")
    assert re.fullmatch(rf"vidgen_{expected}_[0-9a-f]{{8}}_test", name), name
    mig = c._random_name("vidgen_mig")
    assert re.fullmatch(rf"vidgen_mig_{expected}_[0-9a-f]{{8}}_test", mig), mig


def test_generated_database_names_never_collide_with_protected_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.integration import conftest as c

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    names = {c._random_name(p) for p in ("vidgen", "vidgen_mig") for _ in range(50)}
    assert len(names) == 100
    assert not names & c.PROTECTED
    assert all(n.endswith("_test") for n in names)


def test_protected_names_include_every_real_database() -> None:
    from tests.integration import conftest as c

    assert {"vidgen", "vidgen_demo", "vidgen_test", "vidgen_migration_test", "postgres"} <= set(
        c.PROTECTED
    )


@pytest.mark.parametrize(
    "name", ["vidgen", "vidgen_demo", "vidgen_test", "vidgen_migration_test", "postgres"]
)
def test_cleanup_refuses_protected_database_names(name: str) -> None:
    from tests.integration import conftest as c

    url = f"postgresql+psycopg://u:p@127.0.0.1:5432/{name}"
    with pytest.raises(AssertionError, match="refusing to remove"):
        c._remove_database(url)  # the guard fires before any connection is opened


def test_cleanup_refuses_names_that_do_not_end_in_test() -> None:
    from tests.integration import conftest as c

    with pytest.raises(AssertionError, match="refusing to remove"):
        c._remove_database("postgresql+psycopg://u:p@127.0.0.1:5432/vidgen_gw0_abcd1234")


def test_no_test_module_hard_codes_a_real_database_name() -> None:
    pattern = re.compile(
        r"(?:127\.0\.0\.1|localhost|postgres)(?::\d+)?/(" + "|".join(REAL_DB_NAMES) + r")(?![\w])"
    )
    offenders = [
        f"{rel(p)}: {m.group(0)}"
        for p in repo_test_files()
        if rel(p) not in DB_NAME_ALLOW
        for m in pattern.finditer(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, offenders


# --- docker stack ------------------------------------------------------------------------------


@pytest.mark.parametrize(("worker", "expected"), [("gw0", "gw0"), ("gw7", "gw7"), (None, "master")])
def test_docker_stack_project_name_includes_the_worker_id(
    monkeypatch: pytest.MonkeyPatch, worker: str | None, expected: str
) -> None:
    from tests.e2e import test_docker_stack_e2e as stack_module

    if worker is None:
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    else:
        monkeypatch.setenv("PYTEST_XDIST_WORKER", worker)
    assert stack_module.project_name() == f"vidgen-t3test-{expected}"


def test_docker_stack_module_is_one_xdist_group() -> None:
    from tests.e2e import test_docker_stack_e2e as stack_module

    marks = [m for m in stack_module.pytestmark if m.name == "xdist_group"]
    assert marks, "tests/e2e/test_docker_stack_e2e.py needs pytest.mark.xdist_group('docker-stack')"
    assert marks[0].args == ("docker-stack",) or marks[0].kwargs.get("name") == "docker-stack"


# --- ports, repo writes, environment -----------------------------------------------------------


def test_no_test_binds_a_fixed_tcp_port() -> None:
    bind = re.compile(r"\.bind\(\s*\(\s*[^,()]+,\s*([1-9]\d*)\s*\)")
    offenders = [
        f"{rel(p)}: {m.group(0)}"
        for p in repo_test_files()
        for m in bind.finditer(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, offenders


WRITE_METHODS = {
    "write_text",
    "write_bytes",
    "mkdir",
    "touch",
    "unlink",
    "rmdir",
    "rename",
    "replace",
}
WRITE_FUNCS = {"copy", "copy2", "copyfile", "copytree", "move", "rmtree", "remove", "makedirs"}


def _mentions_repo(source: str, node: ast.AST) -> bool:
    segment = ast.get_source_segment(source, node) or ""
    return bool(re.search(r"\bROOT\b|__file__|\bparents\[", segment))


def test_no_test_writes_under_the_repository_tree_outside_tmp_path() -> None:
    offenders: list[str] = []
    for path in repo_test_files():
        if rel(path) in REPO_WRITE_ALLOW or path.name == "test_xdist_isolation.py":
            continue
        source, tree = parsed(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            hit = False
            if isinstance(func, ast.Attribute) and func.attr in WRITE_METHODS:
                hit = _mentions_repo(source, func.value)
            elif isinstance(func, ast.Attribute) and func.attr in WRITE_FUNCS:
                hit = any(_mentions_repo(source, a) for a in node.args)
            elif isinstance(func, ast.Name) and func.id == "open":
                mode = ast.get_source_segment(source, node) or ""
                hit = bool(re.search(r"[\"'][wax+]+b?[\"']", mode)) and any(
                    _mentions_repo(source, a) for a in node.args[:1]
                )
            if hit:
                offenders.append(f"{rel(path)}:{node.lineno}")
    assert not offenders, offenders


ENV_CALLS = {"update", "setdefault", "pop", "clear"}
ENV_FUNCS = {"putenv", "unsetenv"}


def _is_os_environ(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def env_mutations(tree: ast.Module) -> list[int]:
    """Line numbers of ``os.environ[...] = x``, ``os.environ.update(...)``, ``os.putenv(...)``."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign | ast.AugAssign | ast.Delete):
            targets = node.targets if hasattr(node, "targets") else [node.target]
            if any(isinstance(t, ast.Subscript) and _is_os_environ(t.value) for t in targets):
                lines.append(node.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            func = node.func
            if (_is_os_environ(func.value) and func.attr in ENV_CALLS) or (
                isinstance(func.value, ast.Name)
                and func.value.id == "os"
                and func.attr in ENV_FUNCS
            ):
                lines.append(node.lineno)
    return lines


def test_no_test_assigns_process_environment_without_monkeypatch() -> None:
    offenders = [
        f"{rel(path)}:{line}"
        for path in repo_test_files()
        if path.name != "test_xdist_isolation.py"
        for line in env_mutations(parsed(path)[1])
    ]
    assert not offenders, offenders


def test_the_environment_scan_catches_an_injected_violation(tmp_path: Path) -> None:
    bad = tmp_path / "test_bad.py"
    bad.write_text(
        "import os\nos.environ['X'] = '1'\nos.environ.update(A='b')\nos.putenv('A', 'b')\n"
        "def test_ok(monkeypatch):\n    monkeypatch.setenv('X', '1')\n    os.environ.get('X')\n",
        encoding="utf-8",
    )
    assert env_mutations(ast.parse(bad.read_text(encoding="utf-8"))) == [2, 3, 4]


def shared_temp_reads(tree: ast.Module) -> list[int]:
    """Lines of ``gettempdir()`` calls in functions that never redirect ``tempfile.tempdir``.

    The machine-wide temp folder is shared by every xdist worker, so listing it (or counting
    files in it) sees other workers' directories.
    """
    lines: set[int] = set()
    for func in ast.walk(tree):
        if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        reads = [
            n.lineno
            for n in ast.walk(func)
            if isinstance(n, ast.Call)
            and (
                (isinstance(n.func, ast.Attribute) and n.func.attr == "gettempdir")
                or (isinstance(n.func, ast.Name) and n.func.id == "gettempdir")
            )
        ]
        redirected = any(
            isinstance(n, ast.Constant) and n.value in ("tempdir", "TMPDIR") for n in ast.walk(func)
        )
        if reads and not redirected:
            lines.update(reads)
    return sorted(lines)


def test_no_test_reads_the_shared_temp_folder_without_redirecting_it() -> None:
    offenders = [
        f"{rel(path)}:{line}"
        for path in repo_test_files()
        if path.name != "test_xdist_isolation.py"
        for line in shared_temp_reads(parsed(path)[1])
    ]
    assert not offenders, offenders


def test_the_shared_temp_scan_catches_an_injected_violation() -> None:
    bad = (
        "import tempfile\n"
        "def test_a():\n    return set(tempfile.gettempdir())\n"
        "def test_b(monkeypatch):\n"
        "    monkeypatch.setattr(tempfile, 'tempdir', 'x')\n    return tempfile.gettempdir()\n"
    )
    assert shared_temp_reads(ast.parse(bad)) == [3]


# --- wall-clock assertions ---------------------------------------------------------------------


def _decorators(source: str, func_name: str) -> list[str]:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return [ast.get_source_segment(source, d) or "" for d in node.decorator_list]
    raise AssertionError(f"{func_name} not found")


@pytest.mark.parametrize(
    ("module", "name"), [(m, n) for m, names in TIMING_MODULES.items() for n in names]
)
def test_tests_with_wall_clock_bounds_are_in_the_timing_group(module: str, name: str) -> None:
    decorators = _decorators((ROOT / module).read_text(encoding="utf-8"), name)
    assert any(re.search(r"xdist_group\(\s*(name=)?[\"']timing[\"']", d) for d in decorators), (
        f"{module}::{name} needs @pytest.mark.xdist_group('timing')"
    )


def test_every_perf_counter_bound_is_listed_in_the_timing_table() -> None:
    """A new wall-clock assertion must be added to TIMING_MODULES (and tagged)."""
    users = {
        rel(p)
        for p in repo_test_files()
        if p.name != "test_xdist_isolation.py"
        and re.search(r"perf_counter\(\) - \w+\s*<|elapsed\s*<", p.read_text(encoding="utf-8"))
    }
    assert users <= set(TIMING_MODULES), sorted(users - set(TIMING_MODULES))
