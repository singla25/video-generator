"""AC2: ``backend/modal_app/app.py`` imported under a stub ``modal`` (no network, no install)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from tests.fixtures.modal_app_check import EMPTY, app_problems, secret_findings, unpinned
from tests.fixtures.modal_stub import load_app
from tests.unit.modal_mode.conftest import APP_FILE

NAMES = {  # literal on purpose: the contract strings, independent of the protocol module
    "transcribe": [("audio", EMPTY), ("hint", None)],
    "has_sample": [("sample_hash", EMPTY)],
    "upload_sample": [("sample_hash", EMPTY), ("data", EMPTY)],
    "synthesize": [("text", EMPTY), ("sample_hash", EMPTY)],
}
GOOD = """
import modal

app = modal.App("vidgen-ai")
image = modal.Image.debian_slim().uv_pip_install("numpy==1.26.4", "faster-whisper==1.2.1")

@app.function(image=image)
def transcribe(audio: bytes, hint: str | None = None) -> list: return []
@app.function(image=image)
def has_sample(sample_hash: str) -> bool: return False
@app.function(image=image)
def upload_sample(sample_hash: str, data: bytes) -> None: return None
@app.function(image=image)
def synthesize(text: str, sample_hash: str) -> bytes: return b""
"""


def write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "fake_app.py"
    path.write_text(source, encoding="utf-8")
    return path


# --- the real app -----------------------------------------------------------------------------


def test_the_real_app_has_no_problem() -> None:
    assert app_problems(APP_FILE, NAMES) == []


def test_the_app_is_named_with_the_default_app_name() -> None:
    assert load_app(APP_FILE).app_names == ["vidgen-ai"]


def test_the_app_takes_its_names_from_the_protocol_module() -> None:
    """AC1: imported, not retyped, so the client and the app cannot drift apart."""
    tree = ast.parse(APP_FILE.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "vidgen.infrastructure.modal_ai.protocol"
        for alias in node.names
    }
    assert {"DEFAULT_APP_NAME", "FN_TRANSCRIBE", "FN_HAS_SAMPLE"} <= imported
    assert {"FN_UPLOAD_SAMPLE", "FN_SYNTHESIZE"} <= imported


def test_the_four_remote_functions_exist_with_the_client_signatures() -> None:
    rec = load_app(APP_FILE)
    for name, expected in NAMES.items():
        assert rec.signature(name) == expected, name


def test_the_image_pins_every_package_and_leaves_modal_out() -> None:
    rec = load_app(APP_FILE)
    assert rec.pins, "the image installs something"
    assert unpinned(rec.pins) == []
    assert not [p for p in rec.pins if p.lower().startswith("modal")]


def test_the_image_pins_include_the_two_models() -> None:
    pins = " ".join(load_app(APP_FILE).pins)
    assert "faster-whisper==" in pins
    assert "chatterbox" in pins.lower() or "chatterbox" in APP_FILE.read_text("utf-8").lower()


def test_one_warm_container_class_loads_the_models_once() -> None:
    rec = load_app(APP_FILE)
    assert len(rec.classes) == 1
    text = APP_FILE.read_text(encoding="utf-8")
    node = next(
        n
        for n in ast.walk(ast.parse(text))
        if isinstance(n, ast.ClassDef) and n.name == rec.classes[0].__name__
    )
    source = ast.get_source_segment(text, node) or ""
    assert "faster_whisper" in source and "chatterbox" in source.lower()


def test_the_source_has_no_secret_like_text() -> None:
    assert secret_findings(APP_FILE.read_text(encoding="utf-8")) == []


def test_importing_the_app_reads_no_token_from_the_environment_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODAL_TOKEN_ID", "ak-ENV-SHOULD-NOT-MATTER-0000")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "as-ENV-SHOULD-NOT-MATTER-0000")
    assert app_problems(APP_FILE, NAMES) == []


def test_the_stub_is_removed_from_sys_modules_after_loading() -> None:
    before = sys.modules.get("modal")
    load_app(APP_FILE)
    assert sys.modules.get("modal") is before


# --- the checker itself (negative: it must catch each fault) ------------------------------------


def test_checker_accepts_a_good_app(tmp_path: Path) -> None:
    assert app_problems(write(tmp_path, GOOD), NAMES) == []


def test_checker_reports_a_missing_function(tmp_path: Path) -> None:
    source = GOOD.replace("def has_sample(", "def has_sample_removed(")
    assert "missing function has_sample" in app_problems(write(tmp_path, source), NAMES)


def test_checker_reports_a_renamed_function(tmp_path: Path) -> None:
    source = GOOD.replace("def synthesize(", "def synthesise(")
    assert "missing function synthesize" in app_problems(write(tmp_path, source), NAMES)


def test_checker_reports_a_missing_hint_parameter(tmp_path: Path) -> None:
    source = GOOD.replace("hint: str | None = None", "")
    assert "wrong signature for transcribe" in app_problems(write(tmp_path, source), NAMES)


def test_checker_reports_an_unpinned_image_entry(tmp_path: Path) -> None:
    source = GOOD.replace('"numpy==1.26.4"', '"numpy"')
    assert "unpinned image entry numpy" in app_problems(write(tmp_path, source), NAMES)


def test_checker_reports_a_range_instead_of_a_pin(tmp_path: Path) -> None:
    source = GOOD.replace('"numpy==1.26.4"', '"numpy>=1.26"')
    assert "unpinned image entry numpy>=1.26" in app_problems(write(tmp_path, source), NAMES)


def test_checker_reports_modal_inside_the_image(tmp_path: Path) -> None:
    source = GOOD.replace('"numpy==1.26.4"', '"modal==1.6.4"')
    assert "modal in image: modal==1.6.4" in app_problems(write(tmp_path, source), NAMES)


@pytest.mark.parametrize(
    "line",
    [
        'TOKEN = "ak-' + "a1B2c3D4e5F6g7" + '"',
        'SECRET = "as-' + "a1B2c3D4e5F6g7" + '"',
        'MODAL_TOKEN_SECRET = "abc123"',
        'HF = "hf_' + "x" * 24 + '"',
    ],
)
def test_checker_reports_a_secret_looking_string(tmp_path: Path, line: str) -> None:
    problems = app_problems(write(tmp_path, GOOD + "\n" + line + "\n"), NAMES)
    assert any(p.startswith("secret-like text") for p in problems)


def test_a_broken_app_file_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(SyntaxError):
        load_app(write(tmp_path, "def broken(:\n"))


def test_the_image_chain_ends_with_the_local_vidgen_package_and_adds_no_other_path() -> None:
    """The container must import vidgen...protocol, so the image has to carry the package."""
    steps = load_app(APP_FILE).image_steps
    local = [s for s in steps if s[0].startswith("add_local")]
    assert local == [("add_local_python_source", ("vidgen",))]
    assert steps[-1] == ("add_local_python_source", ("vidgen",))
