"""scripts/setup.py: admin login, migrations, no-terminal refusal and secrecy (AC2, P3)."""

from __future__ import annotations

import pytest

from tests.unit.meta.conftest import DEMO_HASH, DEMO_PASSWORD, SECRETS, Harness
from tests.unit.meta.test_setup_installer import COMPOSE_COMMAND

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
