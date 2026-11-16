"""scripts/setup.py offers only the AI modes the backend accepts (gap 1, ADR-013).

The accepted modes come from ``ai_mode: Literal[...]`` in <root>/backend/vidgen/settings.py,
parsed with ``ast`` (the backend is never imported). Offered modes = MODES intersected with them.
"""

from __future__ import annotations

import pytest

from tests.unit.meta.conftest import BACKEND_SETTINGS, ROOT, Harness, settings_source
from tests.unit.meta.test_setup_installer import read_settings

NO_MODAL = settings_source(("fake", "local"))


def mode_prompts(h: Harness) -> list[str]:
    """The prompt texts that asked for the mode."""
    return [p for p in h.prompts if "mode" in p.lower()]


def assert_modal_refused(h: Harness, *, asked: int = 2) -> None:
    """Modal was typed, refused clearly, and nothing modal-related happened."""
    text = "\n".join(h.lines)
    assert "not available yet" in text and "ADR-013" in text
    assert len(mode_prompts(h)) == asked, "the mode is asked again after the refusal"
    assert not any("token" in p.lower() for p in h.secret_prompts)
    assert h.opened == []
    assert h.calls_with("--with") == []


def test_modal_is_refused_with_a_clear_message_and_the_mode_is_asked_again(
    harness: Harness,
) -> None:
    harness.write_backend_settings(NO_MODAL)
    harness.answers["mode"] = ["modal", "fake"]
    assert harness.run_main() == 0
    assert_modal_refused(harness)
    assert read_settings(harness.dotenv)["VIDGEN_AI_MODE"] == "fake"
    assert "MODAL_TOKEN_ID" not in harness.dotenv.read_text(encoding="utf-8")


def test_the_prompt_lists_only_the_available_modes(harness: Harness) -> None:
    harness.write_backend_settings(NO_MODAL)
    harness.answers["mode"] = ["modal", "local"]
    assert harness.run_main() == 0
    for prompt in mode_prompts(harness):
        low = prompt.lower()
        assert "fake" in low and "local" in low and "modal" not in low


def test_repeated_modal_answers_never_reach_the_token_step(harness: Harness) -> None:
    harness.write_backend_settings(NO_MODAL)
    harness.answers["mode"] = ["modal", " MODAL ", "modal", "fake"]
    assert harness.run_main() == 0
    assert harness.secret_prompts and not any("token" in p.lower() for p in harness.secret_prompts)
    assert harness.opened == [] and harness.calls_with("--with") == []


def test_modal_works_as_before_when_the_backend_accepts_it(harness: Harness) -> None:
    harness.write_backend_settings(settings_source(("fake", "local", "modal")))
    harness.answers["mode"] = ["modal"]
    assert harness.run_main() == 0
    assert read_settings(harness.dotenv)["VIDGEN_AI_MODE"] == "modal"
    assert len(mode_prompts(harness)) == 1 and "modal" in mode_prompts(harness)[0].lower()


# --- the real repository file ----------------------------------------------------------------


def test_real_backend_settings_refuse_modal_today(harness: Harness) -> None:
    """T4 flips this test on purpose: once the real Literal accepts "modal", expect acceptance."""
    harness.write_backend_settings((ROOT / BACKEND_SETTINGS).read_text(encoding="utf-8"))
    harness.answers["mode"] = ["modal", "fake"]
    assert harness.run_main() == 0
    assert_modal_refused(harness)


# --- edge: how the Literal is written ---------------------------------------------------------


def test_literal_written_across_several_lines_is_understood(harness: Harness) -> None:
    harness.write_backend_settings(
        "from typing import Literal\n\nclass Settings:\n"
        '    ai_backend: Literal["fake", "real"] = "fake"\n'
        "    ai_mode: Literal[\n"
        '        "fake",\n'
        '        "local",\n'
        '        "modal",\n'
        '    ] = "fake"\n'
    )
    harness.answers["mode"] = ["modal"]
    assert harness.run_main() == 0
    assert read_settings(harness.dotenv)["VIDGEN_AI_MODE"] == "modal"


def test_single_quoted_literal_without_modal_refuses_modal(harness: Harness) -> None:
    harness.write_backend_settings(
        "from typing import Literal\n\nclass Settings:\n"
        "    ai_mode: Literal['fake', 'local'] = 'fake'\n"
    )
    harness.answers["mode"] = ["modal", "fake"]
    assert harness.run_main() == 0
    assert_modal_refused(harness)


def test_single_quoted_literal_with_modal_accepts_modal(harness: Harness) -> None:
    harness.write_backend_settings(
        "from typing import Literal\n\nclass Settings:\n"
        "    ai_mode: Literal['fake', 'local', 'modal'] = 'fake'\n"
    )
    harness.answers["mode"] = ["modal"]
    assert harness.run_main() == 0


def test_modal_in_ai_backend_does_not_make_ai_mode_accept_it(harness: Harness) -> None:
    harness.write_backend_settings(
        settings_source(("fake", "local"), backend_modes=("fake", "real", "modal"))
    )
    harness.answers["mode"] = ["modal", "fake"]
    assert harness.run_main() == 0
    assert_modal_refused(harness)


@pytest.mark.parametrize("ai_backend_first", [True, False])
def test_modal_in_ai_mode_is_accepted_whatever_ai_backend_says_or_where_it_sits(
    harness: Harness, ai_backend_first: bool
) -> None:
    backend = '    ai_backend: Literal["fake", "real"] = "fake"\n'
    mode = '    ai_mode: Literal["fake", "local", "modal"] = "fake"\n'
    body = backend + mode if ai_backend_first else mode + backend
    harness.write_backend_settings("from typing import Literal\n\nclass Settings:\n" + body)
    harness.answers["mode"] = ["modal"]
    assert harness.run_main() == 0
    assert read_settings(harness.dotenv)["VIDGEN_AI_MODE"] == "modal"


def test_settings_file_is_parsed_not_imported(harness: Harness) -> None:
    harness.write_backend_settings(
        settings_source(("fake", "local")) + '\nraise RuntimeError("imported")\n'
    )
    harness.answers["mode"] = ["fake"]
    assert harness.run_main() == 0


# --- edge: fallbacks and intersection ---------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        None,
        "this is not python (((",
        "class Settings:\n    other: int = 1\n",
        "class Settings:\n    ai_mode: str = 'fake'\n",
    ],
    ids=["missing", "syntax-error", "no-ai-mode", "not-a-literal"],
)
def test_missing_or_unusable_settings_fall_back_to_fake_and_local_only(
    harness: Harness, text: str | None
) -> None:
    harness.write_backend_settings(text)
    harness.answers["mode"] = ["modal", "local"]
    assert harness.run_main() == 0
    assert_modal_refused(harness)
    assert read_settings(harness.dotenv)["VIDGEN_AI_MODE"] == "local"


def test_a_mode_the_installer_does_not_know_is_never_offered(harness: Harness) -> None:
    harness.write_backend_settings(settings_source(("fake", "local", "cuda")))
    harness.answers["mode"] = ["cuda", "fake"]
    assert harness.run_main() == 0
    assert len(mode_prompts(harness)) == 2
    assert all("cuda" not in p.lower() for p in mode_prompts(harness))


def test_a_mode_the_backend_does_not_accept_is_not_offered_even_if_fake(harness: Harness) -> None:
    harness.write_backend_settings(settings_source(("local",)))
    harness.answers["mode"] = ["fake", "local"]
    assert harness.run_main() == 0
    assert len(mode_prompts(harness)) == 2
    assert read_settings(harness.dotenv)["VIDGEN_AI_MODE"] == "local"
