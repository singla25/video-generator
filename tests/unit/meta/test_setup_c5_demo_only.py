"""scripts/setup.py, Modal demo-only gate (Admin decision C5, 2026-11-16).

Modal mode is for demo and learning data only, never real voter data. Before any link opens or any
token is asked, the installer shows a notice and needs an explicit "yes" at a prompt containing
"demo data" (the harness routes it by that keyword). Made-up demo values only.
"""

from __future__ import annotations

import pytest

from tests.unit.meta.conftest import Harness
from tests.unit.meta.test_setup_modal import validation_calls

KEYWORD = "demo data"


@pytest.fixture
def modal(harness: Harness) -> Harness:
    """A harness that picks the modal mode (confirmation answered "yes" by default)."""
    harness.answers["mode"] = ["modal"]
    return harness


def confirm_prompts(h: Harness) -> list[str]:
    """Prompts that are the demo-data confirmation."""
    return [p for p in h.prompts if KEYWORD in p.lower()]


def assert_declined(h: Harness) -> None:
    """Nothing happened after the refused confirmation."""
    assert h.opened == []
    assert h.secret_prompts == []
    assert h.calls == []
    h.assert_nothing_written()


# --- positive ---------------------------------------------------------------------------------


def test_notice_names_demo_only_and_never_real_voter_data(modal: Harness) -> None:
    assert modal.run_main() == 0
    text = "\n".join(modal.lines).lower()
    assert "demo and learning data only" in text
    assert "never real voter data" in text
    assert "names" in text and "voices" in text and "faces" in text and "modal" in text


def test_notice_is_shown_before_any_link_opens_or_token_is_asked(modal: Harness) -> None:
    events: list[str] = []
    original_echo = modal.lines.append

    def echo(line: str) -> None:
        if "never real voter data" in line.lower():
            events.append("notice")
        original_echo(line)

    seams = modal.seams()
    seams.echo = echo
    seams.open_url = lambda url: events.append("open") or True
    original_getpass = seams.getpass
    seams.getpass = lambda prompt: events.append("getpass") or original_getpass(prompt)
    original_ask = seams.ask
    seams.ask = lambda prompt: (
        events.append("confirm" if KEYWORD in prompt.lower() else "ask") or original_ask(prompt)
    )
    assert modal.mod.main(["--root", str(modal.root)], seams) == 0
    assert events.index("notice") < events.index("confirm")
    assert events.index("confirm") < events.index("open")
    assert events.index("confirm") < events.index("getpass")


def test_confirmation_is_asked_exactly_once_through_ask(modal: Harness) -> None:
    assert modal.run_main() == 0
    assert len(confirm_prompts(modal)) == 1


@pytest.mark.parametrize("answer", ["yes", "YES", "  Yes  ", "yEs\n"])
def test_yes_in_any_case_or_spacing_continues_to_the_token_step(
    modal: Harness, answer: str
) -> None:
    modal.answers[KEYWORD] = [answer]
    assert modal.run_main() == 0
    assert modal.opened and len(validation_calls(modal)) == 1


# --- negative ---------------------------------------------------------------------------------


@pytest.mark.parametrize("answer", ["", "y", "no", "ok", "yes please", "yess", "  "])
def test_anything_but_yes_stops_before_links_tokens_calls_and_writing(
    modal: Harness, answer: str
) -> None:
    modal.answers[KEYWORD] = [answer]
    assert modal.run_main() != 0
    text = "\n".join(modal.lines).lower()
    assert "demo" in text and ("yes" in text or "stopp" in text or "cancel" in text)
    assert_declined(modal)


def test_declined_confirmation_leaves_an_existing_file_byte_identical(modal: Harness) -> None:
    modal.dotenv.write_bytes(b"KEEP=me\n")
    modal.answers.update({"overwrite": ["y"], KEYWORD: ["no"]})
    assert modal.run_main() != 0
    assert modal.dotenv.read_bytes() == b"KEEP=me\n"
    assert modal.top_level() == [modal.dotenv.name]
    assert modal.opened == [] and modal.secret_prompts == []
    assert validation_calls(modal) == []
    assert modal.calls_with("hash-password") == []


def test_declined_confirmation_is_not_asked_again(modal: Harness) -> None:
    modal.answers[KEYWORD] = ["no"]
    assert modal.run_main() != 0
    assert len(confirm_prompts(modal)) == 1


# --- edge -------------------------------------------------------------------------------------


def test_eof_at_the_confirmation_exits_cleanly_and_writes_nothing(
    modal: Harness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    original = modal._ask

    def ask(prompt: str) -> str:
        if KEYWORD in prompt.lower():
            raise EOFError
        return original(prompt)

    monkeypatch.setattr(modal, "_ask", ask)
    code = modal.run_main()
    seen = capsys.readouterr()
    assert code not in (0, 130)
    assert modal.lines, "a clear message is printed"
    assert "Traceback" not in "\n".join([*modal.lines, seen.out, seen.err])
    assert_declined(modal)


@pytest.mark.parametrize("mode", ["fake", "local"])
def test_fake_and_local_modes_never_show_the_notice_or_ask(harness: Harness, mode: str) -> None:
    harness.answers["mode"] = [mode]
    assert harness.run_main() == 0
    text = "\n".join(harness.lines).lower()
    assert "voter" not in text and "demo and learning" not in text
    assert [p for p in harness.prompts if KEYWORD in p.lower()] == []
