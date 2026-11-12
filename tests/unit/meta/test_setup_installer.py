"""scripts/setup.py: prerequisites, mode choice, settings file, admin login, migrations (AC2, P3).

Every outside effect (subprocess, hidden input, prompts, browser, tools) is a conftest fake.
"""

from __future__ import annotations

import ast
import os
import re
import stat
import sys
from pathlib import Path

import pytest

from tests.unit.meta.conftest import DEMO_HASH, DEMO_PASSWORD, ROOT, SECRETS, Harness

COMPOSE_COMMAND = "docker compose --profile app up -d"


def read_settings(path: Path) -> dict[str, str]:
    """Parse KEY=value lines (quotes stripped) from a generated settings file."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key] = value.strip("'\"")
    return values


# --- stdlib only ------------------------------------------------------------------------------


def test_installer_imports_only_the_standard_library() -> None:
    """P3: the installer must run on a bare python3, before any dependency is installed."""
    tree = ast.parse((ROOT / "scripts" / "setup.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    assert imported - set(sys.stdlib_module_names) == set()


# --- prerequisites ----------------------------------------------------------------------------


def test_prerequisites_pass_when_every_tool_is_present_and_docker_runs(harness: Harness) -> None:
    assert harness.run_main() == 0
    assert harness.calls[0].argv[:2] == ["docker", "info"]


@pytest.mark.parametrize(
    ("missing", "word"),
    [("docker", "docker"), ("uv", "uv"), ("node", "node"), ("ffmpeg", "ffmpeg")],
)
def test_missing_tool_is_named_and_nothing_is_written(
    harness: Harness, missing: str, word: str
) -> None:
    harness.missing_tools = {missing}
    assert harness.run_main() != 0
    assert word in "\n".join(harness.lines).lower()
    harness.assert_nothing_written()
    assert harness.prompts == [] and harness.secret_prompts == []


def test_several_missing_tools_are_all_named_in_one_run(harness: Harness) -> None:
    harness.missing_tools = {"uv", "ffmpeg", "node"}
    assert harness.run_main() != 0
    text = "\n".join(harness.lines).lower()
    assert all(word in text for word in ("uv", "ffmpeg", "node"))
    harness.assert_nothing_written()


def test_docker_installed_but_not_running_says_docker_is_not_running(harness: Harness) -> None:
    harness.docker_rc = 1
    assert harness.run_main() != 0
    text = "\n".join(harness.lines).lower()
    assert "docker" in text and "running" in text
    harness.assert_nothing_written()


# --- mode choice ------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["fake", "local"])
def test_chosen_mode_is_written_as_ai_mode(harness: Harness, mode: str) -> None:
    harness.answers["mode"] = [mode]
    assert harness.run_main() == 0
    assert read_settings(harness.dotenv)["VIDGEN_AI_MODE"] == mode


@pytest.mark.parametrize("typed", ["FAKE", "  Local  "])
def test_mode_answer_ignores_case_and_surrounding_spaces(harness: Harness, typed: str) -> None:
    harness.answers["mode"] = [typed]
    assert harness.run_main() == 0
    assert read_settings(harness.dotenv)["VIDGEN_AI_MODE"] == typed.strip().lower()


def test_invalid_mode_answers_are_asked_again_until_valid(harness: Harness) -> None:
    harness.answers["mode"] = ["", "gpu", "9", "fake"]
    assert harness.run_main() == 0
    assert len([p for p in harness.prompts if "mode" in p.lower()]) == 4
    assert read_settings(harness.dotenv)["VIDGEN_AI_MODE"] == "fake"


def test_fake_mode_never_asks_for_modal_tokens(harness: Harness) -> None:
    assert harness.run_main() == 0
    assert not any("token" in p.lower() for p in harness.secret_prompts)
    assert harness.opened == []
    assert not any("modal" in c.argv for c in harness.calls)
    assert "MODAL_TOKEN_ID" not in harness.dotenv.read_text(encoding="utf-8")


def test_local_mode_never_asks_for_modal_tokens(harness: Harness) -> None:
    harness.answers["mode"] = ["local"]
    assert harness.run_main() == 0
    assert not any("token" in p.lower() for p in harness.secret_prompts)
    assert harness.opened == []


# --- settings file ----------------------------------------------------------------------------


def test_settings_file_is_owner_only(harness: Harness) -> None:
    assert harness.run_main() == 0
    assert stat.S_IMODE(harness.dotenv.stat().st_mode) == 0o600


def test_settings_file_has_fresh_random_secrets_and_local_services(harness: Harness) -> None:
    assert harness.run_main() == 0
    values = read_settings(harness.dotenv)
    for key in ("VIDGEN_ENCRYPTION_KEY", "VIDGEN_INDEX_KEY", "VIDGEN_SESSION_SECRET"):
        assert len(values[key]) >= 32, key
    assert re.fullmatch(r"[0-9a-f]{64}", values["VIDGEN_ENCRYPTION_KEY"])
    assert values["VIDGEN_DATABASE_URL"].startswith("postgresql")
    assert values["VIDGEN_REDIS_URL"].startswith("redis://")


def test_two_installs_generate_different_secrets(harness: Harness, tmp_path: Path) -> None:
    other = tmp_path / "second"
    other.mkdir()
    assert harness.run_main() == 0
    second = Harness(harness.mod, other)
    assert second.run_main() == 0
    assert (
        read_settings(harness.dotenv)["VIDGEN_ENCRYPTION_KEY"]
        != read_settings(second.dotenv)["VIDGEN_ENCRYPTION_KEY"]
    )


def test_settings_file_is_written_atomically_with_a_same_folder_temp_file(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_replace = os.replace
    seen: list[tuple[Path, Path]] = []

    def spy(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        seen.append((Path(src), Path(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    assert harness.run_main() == 0
    final = [pair for pair in seen if pair[1] == harness.dotenv]
    assert len(final) == 1
    assert final[0][0].parent == harness.dotenv.parent
    assert final[0][0] != harness.dotenv
    assert [p.name for p in harness.root.iterdir()] == [harness.dotenv.name]


def test_ctrl_c_during_the_final_swap_leaves_no_settings_file_and_no_temp_file(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupt(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", interrupt)
    assert harness.run_main() == 130
    harness.assert_nothing_written()


def test_ctrl_c_at_a_prompt_writes_nothing(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupt(prompt: str) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(harness, "_getpass", interrupt)
    assert harness.run_main() == 130
    harness.assert_nothing_written()


def test_existing_settings_file_is_not_overwritten_when_the_user_declines(harness: Harness) -> None:
    original = b"VIDGEN_AI_MODE=local\nKEEP=me\n"
    harness.dotenv.write_bytes(original)
    harness.dotenv.chmod(0o640)
    harness.answers["overwrite"] = ["n"]
    assert harness.run_main() == 0
    assert harness.dotenv.read_bytes() == original
    assert stat.S_IMODE(harness.dotenv.stat().st_mode) == 0o640
    assert harness.secret_prompts == []
    assert harness.calls_with("hash-password") == []
    assert [p.name for p in harness.root.iterdir()] == [harness.dotenv.name]


@pytest.mark.parametrize("answer", ["", "no", "maybe", "  "])
def test_anything_but_y_keeps_an_existing_settings_file(harness: Harness, answer: str) -> None:
    harness.dotenv.write_bytes(b"KEEP=me\n")
    harness.answers["overwrite"] = [answer]
    harness.run_main()
    assert harness.dotenv.read_bytes() == b"KEEP=me\n"


def test_existing_settings_file_is_replaced_only_after_an_explicit_y(harness: Harness) -> None:
    harness.dotenv.write_bytes(b"KEEP=me\n")
    harness.answers["overwrite"] = ["y"]
    assert harness.run_main() == 0
    values = read_settings(harness.dotenv)
    assert "KEEP" not in values and values["VIDGEN_AI_MODE"] == "fake"
    assert stat.S_IMODE(harness.dotenv.stat().st_mode) == 0o600


def test_rerun_with_overwrite_declined_is_idempotent(harness: Harness) -> None:
    assert harness.run_main() == 0
    first = harness.dotenv.read_bytes()
    harness.answers.update({"overwrite": ["n"], "mode": ["fake"]})
    assert harness.run_main() == 0
    assert harness.dotenv.read_bytes() == first


def test_unicode_project_path_works_end_to_end(setup_mod: object, tmp_path: Path) -> None:
    root = tmp_path / "проект 日本語 🎬"
    root.mkdir()
    h = Harness(setup_mod, root)  # type: ignore[arg-type]
    assert h.run_main() == 0
    assert read_settings(h.dotenv)["VIDGEN_AI_MODE"] == "fake"
    assert "VIDGEN_ADMIN_PASSWORD_HASH" in h.dotenv.read_text(encoding="utf-8")


# --- admin login ------------------------------------------------------------------------------


def test_admin_hash_is_delegated_to_dev_setup_through_uv_run_with_password_on_stdin(
    harness: Harness,
) -> None:
    assert harness.run_main() == 0
    (call,) = harness.calls_with("hash-password")
    assert call.argv[:2] == ["uv", "run"]
    assert any(part.endswith("dev_setup.py") for part in call.argv)
    assert call.input_text is not None and DEMO_PASSWORD in call.input_text


def test_password_never_appears_in_any_argv_or_child_variable(harness: Harness) -> None:
    assert harness.run_main() == 0
    for call in harness.calls:
        assert not any(DEMO_PASSWORD in part for part in call.argv)
        assert not any(DEMO_PASSWORD in v for v in (call.child_vars or {}).values())


def test_hash_returned_by_dev_setup_is_stored_single_quoted_not_the_password(
    harness: Harness,
) -> None:
    assert harness.run_main() == 0
    text = harness.dotenv.read_text(encoding="utf-8")
    assert f"VIDGEN_ADMIN_PASSWORD_HASH='{DEMO_HASH}'" in text
    assert DEMO_PASSWORD not in text


def test_password_is_read_with_hidden_input_only(harness: Harness) -> None:
    assert harness.run_main() == 0
    assert any("password" in p.lower() for p in harness.secret_prompts)
    assert not any("password" in p.lower() for p in harness.prompts)


@pytest.mark.parametrize("password", ["short", "", "elevenchars"])
def test_too_short_password_is_refused_and_nothing_is_written(
    harness: Harness, password: str
) -> None:
    harness.password = password
    assert harness.run_main() != 0
    assert "12" in "\n".join(harness.lines)
    harness.assert_nothing_written()
    assert harness.calls_with("hash-password") == []


def test_mismatched_confirmation_is_refused_and_nothing_is_written(harness: Harness) -> None:
    harness.password_again = "DemoPass-456"  # noqa: S105
    assert harness.run_main() != 0
    assert "differ" in "\n".join(harness.lines).lower()
    harness.assert_nothing_written()


def test_failed_hashing_reports_clearly_and_writes_nothing(harness: Harness) -> None:
    harness.hash_rc = 1
    assert harness.run_main() != 0
    assert "password" in "\n".join(harness.lines).lower()
    harness.assert_nothing_written()


# --- migrations -------------------------------------------------------------------------------


@pytest.mark.parametrize("answer", ["y", "Y", " y "])
def test_migrations_run_once_only_after_an_explicit_y_and_after_the_settings_exist(
    harness: Harness, answer: str
) -> None:
    harness.answers["migrat"] = [answer]
    assert harness.run_main() == 0
    (call,) = harness.calls_with("alembic")
    assert "upgrade" in call.argv and call.argv[:2] == ["uv", "run"]
    assert call.dotenv_existed


@pytest.mark.parametrize("answer", ["n", "N", "", "  ", "yes", "maybe", "ok", "1"])
def test_any_other_answer_applies_no_migration(harness: Harness, answer: str) -> None:
    harness.answers["migrat"] = [answer]
    assert harness.run_main() == 0
    assert harness.calls_with("alembic") == []
    assert harness.calls_with("upgrade") == []


def test_failed_migration_is_reported_and_keeps_the_settings_file(harness: Harness) -> None:
    harness.answers["migrat"] = ["y"]
    harness.migrate_rc = 1
    assert harness.run_main() != 0
    assert "migrat" in "\n".join(harness.lines).lower()
    assert harness.dotenv.exists()


def test_next_commands_are_printed_at_the_end(harness: Harness) -> None:
    assert harness.run_main() == 0
    assert COMPOSE_COMMAND in "\n".join(harness.lines)


# --- no terminal ------------------------------------------------------------------------------


def test_without_a_terminal_the_installer_refuses_and_writes_nothing(harness: Harness) -> None:
    harness.interactive = False
    assert harness.run_main() != 0
    assert "terminal" in "\n".join(harness.lines).lower()
    harness.assert_nothing_written()
    assert harness.calls == [] and harness.prompts == [] and harness.secret_prompts == []


def test_clean_run_prints_and_logs_no_secret(
    harness: Harness, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(0)
    harness.answers["migrat"] = ["y"]
    assert harness.run_main() == 0
    text = harness.all_text(capsys, caplog)
    assert not [s for s in SECRETS if s in text]
    assert DEMO_HASH not in text
