"""AC3: the installer offers modal from the real Settings; C5 and the token pair stay required."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.meta.conftest import (
    BACKEND_SETTINGS,
    DEMO_TOKEN_ID,
    DEMO_TOKEN_SECRET,
    ROOT,
    Harness,
    load_setup,
)
from tests.unit.meta.test_setup_installer import read_settings


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    """The installer harness of the meta tests, rooted in a temp folder."""
    return Harness(load_setup(), tmp_path)


def real_settings(h: Harness) -> None:
    h.write_backend_settings((ROOT / BACKEND_SETTINGS).read_text(encoding="utf-8"))


def test_the_real_settings_annotation_lists_modal(harness: Harness) -> None:
    assert "modal" in harness.mod.accepted_modes(ROOT)


def test_the_prompt_offers_fake_local_and_modal(harness: Harness) -> None:
    real_settings(harness)
    harness.answers["mode"] = ["fake"]
    assert harness.run_main() == 0
    (prompt,) = [p for p in harness.prompts if "mode" in p.lower()]
    assert all(m in prompt.lower() for m in ("fake", "local", "modal"))


def test_modal_with_the_real_settings_still_needs_the_demo_data_yes_and_both_tokens(
    harness: Harness,
) -> None:
    real_settings(harness)
    harness.answers["mode"] = ["modal"]
    assert harness.run_main() == 0
    assert any("demo data" in p.lower() for p in harness.prompts)
    lowered = [p.lower() for p in harness.secret_prompts]
    assert any("token id" in p for p in lowered) and any("token secret" in p for p in lowered)
    values = read_settings(harness.dotenv)
    assert values["MODAL_TOKEN_ID"] == DEMO_TOKEN_ID
    assert values["MODAL_TOKEN_SECRET"] == DEMO_TOKEN_SECRET
    assert values["VIDGEN_AI_MODE"] == "modal"


def test_declining_the_demo_data_confirmation_writes_nothing(harness: Harness) -> None:
    real_settings(harness)
    harness.answers["mode"] = ["modal"]
    harness.answers["demo data"] = ["no"]
    assert harness.run_main() != 0
    assert not harness.dotenv.exists()
    assert harness.secret_prompts == [] and harness.opened == []


def test_empty_tokens_are_refused_with_the_real_settings(harness: Harness) -> None:
    real_settings(harness)
    harness.answers["mode"] = ["modal"]
    harness.token_secret = ""
    assert harness.run_main() != 0
    assert not harness.dotenv.exists()
