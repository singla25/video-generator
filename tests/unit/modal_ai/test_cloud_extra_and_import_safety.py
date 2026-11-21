"""The `cloud` extra is pinned and optional; the adapters never import modal (ADR-013 #8)."""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _pyproject() -> dict[str, object]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_cloud_extra_pins_modal_exactly() -> None:
    extras = _pyproject()["project"]["optional-dependencies"]  # type: ignore[index]
    pins = [d for d in extras["cloud"] if d.startswith("modal")]
    assert len(pins) == 1 and re.fullmatch(r"modal==\d+\.\d+\.\d+", pins[0])


def test_modal_is_not_a_base_dependency() -> None:
    base = _pyproject()["project"]["dependencies"]  # type: ignore[index]
    assert not any(d.lower().startswith("modal") for d in base)


def test_importing_the_adapters_does_not_import_modal() -> None:
    code = (
        "import sys\n"
        "sys.modules['modal'] = None\n"  # makes `import modal` raise ImportError
        "import vidgen.infrastructure.modal_ai.stt\n"
        "import vidgen.infrastructure.modal_ai.tts\n"
        "import vidgen.infrastructure.modal_ai.client\n"
        "import vidgen.infrastructure.modal_ai.errors\n"
        "print('ok')\n"
    )
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "backend")},
        check=False,
    )
    assert result.returncode == 0 and "ok" in result.stdout, result.stderr
