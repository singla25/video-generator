"""AC1: one dependency-free module holds the remote names; client and app share it."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from tests.unit.modal_mode.conftest import ROOT, VIDGEN_DIR

MODAL_AI = VIDGEN_DIR / "infrastructure" / "modal_ai"
EXPECTED = {
    "DEFAULT_APP_NAME": "vidgen-ai",
    "FN_TRANSCRIBE": "transcribe",
    "FN_HAS_SAMPLE": "has_sample",
    "FN_UPLOAD_SAMPLE": "upload_sample",
    "FN_SYNTHESIZE": "synthesize",
}


def test_protocol_module_defines_the_agreed_names() -> None:
    from vidgen.infrastructure.modal_ai import protocol

    for name, value in EXPECTED.items():
        assert getattr(protocol, name) == value


def test_the_four_function_names_are_distinct() -> None:
    from vidgen.infrastructure.modal_ai import protocol

    names = [protocol.FN_TRANSCRIBE, protocol.FN_HAS_SAMPLE, protocol.FN_UPLOAD_SAMPLE]
    names.append(protocol.FN_SYNTHESIZE)
    assert len(set(names)) == 4


def test_importing_protocol_pulls_in_no_third_party_package() -> None:
    code = (
        "import sys\n"
        "import vidgen.infrastructure.modal_ai.protocol\n"
        "bad = [m for m in ('modal', 'torch', 'sqlalchemy', 'pydantic') if m in sys.modules]\n"
        "raise SystemExit(','.join(bad))\n"
    )
    done = subprocess.run(  # noqa: S603 - fixed argv, no network
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, check=False
    )
    assert done.returncode == 0, done.stderr or done.stdout


def test_modal_client_uses_the_constants_from_protocol() -> None:
    from vidgen.infrastructure.modal_ai import modal_client, protocol

    for name in EXPECTED:
        if name.startswith("FN_"):
            assert getattr(modal_client, name) is getattr(protocol, name)


def _assigned_string_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id.startswith("FN_")
    ]


def test_modal_client_does_not_define_the_names_a_second_time() -> None:
    assert _assigned_string_constants(MODAL_AI / "modal_client.py") == []


@pytest.mark.parametrize("name", ["transcribe", "has_sample", "upload_sample", "synthesize"])
def test_function_name_literals_live_only_in_protocol(name: str) -> None:
    """The client may have a method of that name, but never the quoted string."""
    source = (MODAL_AI / "modal_client.py").read_text(encoding="utf-8")
    assert f'"{name}"' not in source and f"'{name}'" not in source
