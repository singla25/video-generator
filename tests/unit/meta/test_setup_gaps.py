"""scripts/setup.py review gaps: keep data keys, Ctrl-D, malformed tokens (AC2, AC3)."""

from __future__ import annotations

import pytest

from tests.unit.meta.conftest import Harness
from tests.unit.meta.test_setup_installer import read_settings

OLD_ENCRYPTION_KEY = "a1" * 32
OLD_INDEX_KEY = "b2" * 32
OLD_SESSION_SECRET = "old-session-secret"  # noqa: S105


def write_existing(h: Harness, *, with_keys: bool = True) -> bytes:
    """Create a previous settings file with made-up keys; returns its bytes."""
    lines = ["VIDGEN_AI_MODE=local", f"VIDGEN_SESSION_SECRET={OLD_SESSION_SECRET}"]
    if with_keys:
        lines += [
            f"VIDGEN_ENCRYPTION_KEY={OLD_ENCRYPTION_KEY}",
            f"VIDGEN_INDEX_KEY={OLD_INDEX_KEY}",
        ]
    h.dotenv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return h.dotenv.read_bytes()


# --- 1. confirmed overwrite keeps the keys that protect existing data -------------------------


def test_confirmed_overwrite_keeps_the_existing_encryption_and_index_keys(harness: Harness) -> None:
    write_existing(harness)
    harness.answers["overwrite"] = ["y"]
    assert harness.run_main() == 0
    values = read_settings(harness.dotenv)
    assert values["VIDGEN_ENCRYPTION_KEY"] == OLD_ENCRYPTION_KEY
    assert values["VIDGEN_INDEX_KEY"] == OLD_INDEX_KEY
    assert values["VIDGEN_AI_MODE"] == "fake", "other values follow the new answers"


def test_confirmed_overwrite_may_regenerate_the_session_secret(harness: Harness) -> None:
    write_existing(harness)
    harness.answers["overwrite"] = ["y"]
    assert harness.run_main() == 0
    assert read_settings(harness.dotenv)["VIDGEN_SESSION_SECRET"] != OLD_SESSION_SECRET


def test_confirmed_overwrite_generates_keys_when_the_old_file_has_none(harness: Harness) -> None:
    write_existing(harness, with_keys=False)
    harness.answers["overwrite"] = ["y"]
    assert harness.run_main() == 0
    values = read_settings(harness.dotenv)
    assert len(values["VIDGEN_ENCRYPTION_KEY"]) == 64 and len(values["VIDGEN_INDEX_KEY"]) == 64
    assert OLD_ENCRYPTION_KEY not in values.values()


def test_old_keys_are_kept_also_when_switching_to_modal_mode(harness: Harness) -> None:
    write_existing(harness)
    harness.answers.update({"overwrite": ["y"], "mode": ["modal"]})
    assert harness.run_main() == 0
    values = read_settings(harness.dotenv)
    assert values["VIDGEN_ENCRYPTION_KEY"] == OLD_ENCRYPTION_KEY
    assert values["VIDGEN_AI_MODE"] == "modal"


# --- 2. Ctrl-D (EOFError) at any prompt -------------------------------------------------------


def raise_eof(*_args: object, **_kwargs: object) -> str:
    """A prompt seam that behaves like closed input."""
    raise EOFError


def assert_clean_exit(h: Harness, capsys: pytest.CaptureFixture[str]) -> None:
    """Non-zero exit with a message and no traceback."""
    code = h.run_main()
    seen = capsys.readouterr()
    text = "\n".join([*h.lines, seen.out, seen.err])
    assert code not in (0, 130) or "cancel" in text.lower() or "input" in text.lower()
    assert code != 0
    assert h.lines, "a clear message is printed"
    assert "Traceback" not in text


def test_ctrl_d_at_the_mode_prompt_exits_cleanly_and_writes_nothing(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(harness, "_ask", raise_eof)
    assert_clean_exit(harness, capsys)
    harness.assert_nothing_written()


def test_ctrl_d_at_the_password_prompt_exits_cleanly_and_writes_nothing(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(harness, "_getpass", raise_eof)
    assert_clean_exit(harness, capsys)
    harness.assert_nothing_written()


def test_ctrl_d_at_the_token_prompt_exits_cleanly_and_writes_nothing(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    harness.answers["mode"] = ["modal"]
    original = harness._getpass

    def getpass(prompt: str) -> str:
        if "token" in prompt.lower():
            raise EOFError
        return original(prompt)

    monkeypatch.setattr(harness, "_getpass", getpass)
    assert_clean_exit(harness, capsys)
    harness.assert_nothing_written()


def test_ctrl_d_at_the_overwrite_prompt_leaves_the_existing_file_unchanged(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    before = write_existing(harness)
    monkeypatch.setattr(harness, "_ask", raise_eof)
    assert_clean_exit(harness, capsys)
    assert harness.dotenv.read_bytes() == before
    assert [p.name for p in harness.root.iterdir()] == [harness.dotenv.name]


def test_ctrl_d_at_the_migration_prompt_applies_no_migration(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    original = harness._ask

    def ask(prompt: str) -> str:
        if "migrat" in prompt.lower():
            raise EOFError
        return original(prompt)

    monkeypatch.setattr(harness, "_ask", ask)
    assert_clean_exit(harness, capsys)
    assert harness.calls_with("alembic") == []


# --- 3. Modal token with a quote or whitespace inside -----------------------------------------


@pytest.mark.parametrize("bad", ["de mo", "de'mo", 'de"mo', "de\tmo", "de`mo"])
@pytest.mark.parametrize("field", ["token_id", "token_secret"])
def test_token_with_inner_space_or_quote_is_named_as_such_and_nothing_is_written(
    harness: Harness, capsys: pytest.CaptureFixture[str], bad: str, field: str
) -> None:
    harness.answers["mode"] = ["modal"]
    setattr(harness, field, bad)
    assert harness.run_main() != 0
    seen = capsys.readouterr()
    text = "\n".join([*harness.lines, seen.out, seen.err])
    assert "spaces or quotes" in text.lower()
    assert "must both be filled in" not in text
    assert bad not in text
    assert harness.calls_with("--with") == []
    harness.assert_nothing_written()
