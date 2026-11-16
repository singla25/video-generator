"""scripts/setup.py real seams, exercised with harmless Python subprocesses only."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import ModuleType

from tests.unit.meta.conftest import ROOT


def test_real_run_passes_extra_vars_and_stdin_and_captures_output(setup_mod: ModuleType) -> None:
    code = "import os,sys; print(os.environ['DEMO_VAR'] + sys.stdin.read())"
    done = setup_mod._real_run(
        [sys.executable, "-c", code], extra_vars={"DEMO_VAR": "x"}, input_text="y"
    )
    assert done.returncode == 0 and done.stdout.strip() == "xy"


def test_real_run_reports_a_failing_command_without_raising(setup_mod: ModuleType) -> None:
    done = setup_mod._real_run([sys.executable, "-c", "raise SystemExit(3)"])
    assert done.returncode == 3


def test_real_seams_use_the_real_tool_lookup_and_runner(setup_mod: ModuleType) -> None:
    seams = setup_mod.real_seams()
    assert seams.which("definitely-not-a-real-tool-xyz") is None
    assert seams.run is setup_mod._real_run


def test_script_run_without_a_terminal_exits_non_zero_and_writes_nothing(tmp_path: Path) -> None:
    done = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts" / "setup.py"), "--root", str(tmp_path)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode != 0
    assert "terminal" in (done.stdout + done.stderr).lower()
    assert list(tmp_path.iterdir()) == []
