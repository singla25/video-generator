"""scripts/setup.py, Modal path: account steps, token pair, validation, secrecy (AC3, AC5, P4)."""

from __future__ import annotations

import stat

import pytest

from tests.unit.meta.conftest import DEMO_HASH, DEMO_TOKEN_ID, DEMO_TOKEN_SECRET, SECRETS, Harness
from tests.unit.meta.test_setup_installer import read_settings


@pytest.fixture
def modal(harness: Harness) -> Harness:
    """A harness that picks the modal mode."""
    harness.answers["mode"] = ["modal"]
    return harness


def validation_calls(h: Harness) -> list:
    """The subprocess calls that ran the modal package."""
    return [c for c in h.calls if "modal" in c.argv and "--with" in c.argv]


# --- positive ---------------------------------------------------------------------------------


def test_modal_mode_validates_the_token_pair_through_uv_run_with_modal(modal: Harness) -> None:
    assert modal.run_main() == 0
    (call,) = validation_calls(modal)
    assert call.argv[:2] == ["uv", "run"]
    assert call.argv[call.argv.index("--with") + 1].startswith("modal")


def test_token_pair_reaches_the_modal_subprocess_only_through_child_variables(
    modal: Harness,
) -> None:
    assert modal.run_main() == 0
    (call,) = validation_calls(modal)
    assert call.child_vars is not None
    assert call.child_vars["MODAL_TOKEN_ID"] == DEMO_TOKEN_ID
    assert call.child_vars["MODAL_TOKEN_SECRET"] == DEMO_TOKEN_SECRET
    for call in modal.calls:
        assert not any(s in part for part in call.argv for s in (DEMO_TOKEN_ID, DEMO_TOKEN_SECRET))
        assert call.input_text is None or DEMO_TOKEN_SECRET not in call.input_text


def test_both_tokens_are_read_with_hidden_input(modal: Harness) -> None:
    assert modal.run_main() == 0
    lowered = [p.lower() for p in modal.secret_prompts]
    assert any("token id" in p for p in lowered) and any("token secret" in p for p in lowered)
    assert not any("token" in p.lower() for p in modal.prompts)


def test_modal_settings_file_holds_mode_and_both_tokens_owner_only(modal: Harness) -> None:
    assert modal.run_main() == 0
    values = read_settings(modal.dotenv)
    assert values["VIDGEN_AI_MODE"] == "modal"
    assert values["MODAL_TOKEN_ID"] == DEMO_TOKEN_ID
    assert values["MODAL_TOKEN_SECRET"] == DEMO_TOKEN_SECRET
    assert stat.S_IMODE(modal.dotenv.stat().st_mode) == 0o600


def test_account_links_are_opened_in_the_browser_and_printed(modal: Harness) -> None:
    assert modal.run_main() == 0
    assert modal.opened, "sign-up / token page must be opened"
    assert all(url.startswith("https://") and "modal.com" in url for url in modal.opened)
    printed = "\n".join(modal.lines)
    assert all(url in printed for url in modal.opened), (
        "links are also printed in case no browser opens"
    )


def test_modal_steps_and_privacy_notice_are_printed(modal: Harness) -> None:
    assert modal.run_main() == 0
    text = "\n".join(modal.lines).lower()
    assert "sign up" in text and "token" in text
    assert "voices" in text and "faces" in text and "names" in text, "AC5: what is sent to Modal"


def test_tokens_are_asked_after_the_mode_choice_not_before(modal: Harness) -> None:
    assert modal.run_main() == 0
    assert modal.prompts, "mode prompt comes first"
    assert "mode" in modal.prompts[0].lower()


# --- negative ---------------------------------------------------------------------------------


@pytest.mark.parametrize("which_token", ["id", "secret"])
def test_empty_token_is_refused_without_calling_modal_and_writes_nothing(
    modal: Harness, which_token: str
) -> None:
    setattr(modal, {"id": "token_id", "secret": "token_secret"}[which_token], "   ")
    assert modal.run_main() != 0
    assert "token" in "\n".join(modal.lines).lower()
    assert validation_calls(modal) == []
    modal.assert_nothing_written()


def test_rejected_token_pair_gives_a_clear_message_and_writes_nothing(modal: Harness) -> None:
    modal.modal_rc = 1
    assert modal.run_main() != 0
    text = "\n".join(modal.lines).lower()
    assert "token" in text and ("invalid" in text or "rejected" in text or "could not" in text)
    modal.assert_nothing_written()


def test_rejected_token_pair_leaves_a_confirmed_existing_file_unchanged(modal: Harness) -> None:
    modal.dotenv.write_bytes(b"KEEP=me\n")
    modal.answers["overwrite"] = ["y"]
    modal.modal_rc = 1
    assert modal.run_main() != 0
    assert modal.dotenv.read_bytes() == b"KEEP=me\n"
    assert modal.top_level() == [modal.dotenv.name]


def test_missing_modal_package_or_network_is_reported_not_crashed(modal: Harness) -> None:
    modal.modal_rc = 127
    modal.modal_stderr = "No module named modal"
    assert modal.run_main() != 0
    modal.assert_nothing_written()


def test_failed_modal_validation_never_echoes_stderr_that_contains_a_token(
    modal: Harness, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(0)
    modal.modal_rc = 1
    modal.modal_stderr = f"auth failed for {DEMO_TOKEN_ID} / {DEMO_TOKEN_SECRET}"
    assert modal.run_main() != 0
    text = modal.all_text(capsys, caplog)
    assert DEMO_TOKEN_ID not in text and DEMO_TOKEN_SECRET not in text


# --- edge -------------------------------------------------------------------------------------


def test_tokens_with_surrounding_spaces_are_stripped_everywhere(modal: Harness) -> None:
    modal.token_id = f"  {DEMO_TOKEN_ID}  "
    modal.token_secret = f"\t{DEMO_TOKEN_SECRET} \n"
    assert modal.run_main() == 0
    (call,) = validation_calls(modal)
    assert call.child_vars is not None
    assert call.child_vars["MODAL_TOKEN_ID"] == DEMO_TOKEN_ID
    assert call.child_vars["MODAL_TOKEN_SECRET"] == DEMO_TOKEN_SECRET
    values = read_settings(modal.dotenv)
    assert values["MODAL_TOKEN_ID"] == DEMO_TOKEN_ID
    assert values["MODAL_TOKEN_SECRET"] == DEMO_TOKEN_SECRET


def test_modal_validation_runs_before_the_settings_file_is_written(modal: Harness) -> None:
    assert modal.run_main() == 0
    (call,) = validation_calls(modal)
    assert not call.dotenv_existed


def test_no_secret_is_ever_printed_or_logged_in_modal_mode(
    modal: Harness, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(0)
    modal.answers["migrat"] = ["y"]
    assert modal.run_main() == 0
    text = modal.all_text(capsys, caplog)
    assert not [s for s in SECRETS if s in text]
    assert DEMO_HASH not in text


def test_ctrl_c_while_validating_tokens_writes_nothing(
    modal: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupt(*_a: object, **_k: object) -> None:
        raise KeyboardInterrupt

    original = modal._run

    def run(argv, **kw):  # type: ignore[no-untyped-def]
        if "--with" in argv:
            interrupt()
        return original(argv, **kw)

    monkeypatch.setattr(modal, "_run", run)
    assert modal.run_main() == 130
    modal.assert_nothing_written()


def test_modal_rerun_with_overwrite_declined_keeps_tokens_file_byte_identical(
    modal: Harness,
) -> None:
    assert modal.run_main() == 0
    first = modal.dotenv.read_bytes()
    modal.answers.update({"overwrite": ["n"], "mode": ["modal"]})
    assert modal.run_main() == 0
    assert modal.dotenv.read_bytes() == first
