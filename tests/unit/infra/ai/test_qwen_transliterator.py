"""Qwen3 transliterator contract (M2 plan AC3, D-M2-2, R5). The LLM is a stub."""

from __future__ import annotations

import pytest

from tests.unit.infra.ai.support import DEVANAGARI_NAME, Blocker, Factory
from vidgen.domain.codes import DomainError, FailureCode
from vidgen.infrastructure.ai.errors import AdapterTimeoutError, ModelLoadError
from vidgen.infrastructure.ai.qwen_transliterator import QwenTransliterator
from vidgen.ports import Transliterator

NAMES = {"rajesh": "राजेश", "krishan": DEVANAGARI_NAME}


class StubLlm:
    """``generate(token, target_script) -> (text, confidence)``; records every call."""

    def __init__(
        self,
        text: str = "अनिता",
        confidence: float = 0.9,
        blocker: Blocker | None = None,
        error: Exception | None = None,
    ) -> None:
        self.text, self.confidence, self.blocker, self.error = text, confidence, blocker, error
        self.calls: list[tuple[str, str]] = []

    def generate(self, token: str, target_script: str) -> tuple[str, float]:
        self.calls.append((token, target_script))
        if self.blocker:
            self.blocker.wait()
        if self.error:
            raise self.error
        return self.text, self.confidence


def make(llm: StubLlm, **kwargs: object) -> tuple[QwenTransliterator, Factory]:
    factory = Factory(llm)
    return QwenTransliterator(engine_factory=factory, common_names=NAMES, **kwargs), factory  # type: ignore[arg-type]


def test_failure_code_pronunciation_uncertain_exists() -> None:
    """M2-S2-P0: the code used to flag low-confidence rows (D-M2-2)."""
    assert FailureCode("PRONUNCIATION_UNCERTAIN") is FailureCode.PRONUNCIATION_UNCERTAIN  # type: ignore[attr-defined]


def test_dictionary_name_is_used_without_calling_the_llm() -> None:
    """M2-S2-P1: common names come from the dictionary first; the model is never loaded."""
    tr, factory = make(StubLlm())
    assert tr.transliterate("Rajesh", "devanagari") == NAMES["rajesh"]
    assert factory.calls == 0


@pytest.mark.parametrize("text", ["RAJESH", "  rajesh ", "Rajesh"])
def test_dictionary_lookup_ignores_case_and_surrounding_spaces(text: str) -> None:
    """M2-S2-E1."""
    tr, factory = make(StubLlm())
    assert tr.transliterate(text, "devanagari") == NAMES["rajesh"]
    assert factory.calls == 0


def test_unknown_name_goes_to_the_llm_and_returns_its_text() -> None:
    """M2-S2-P2."""
    llm = StubLlm(text="अनिता")
    tr, factory = make(llm)
    assert tr.transliterate("Anita", "devanagari") == "अनिता"
    assert llm.calls == [("Anita", "devanagari")]
    assert factory.calls == 1


def test_multiword_name_asks_the_llm_only_for_unknown_words() -> None:
    """M2-S2-P3: 'Rajesh Anita' -> dictionary word + one LLM call, joined by a space."""
    llm = StubLlm(text="अनिता")
    tr, _ = make(llm)
    assert tr.transliterate("Rajesh Anita", "devanagari") == f"{NAMES['rajesh']} अनिता"
    assert llm.calls == [("Anita", "devanagari")]


def test_adapter_satisfies_the_transliterator_port() -> None:
    """M2-S2-P4."""
    tr: Transliterator = make(StubLlm())[0]
    assert isinstance(tr.transliterate("Rajesh", "devanagari"), str)


def test_dictionary_result_is_fully_confident() -> None:
    """M2-S2-P5: checked() exposes confidence and source."""
    result = make(StubLlm())[0].transliterate_checked("Rajesh", "devanagari")
    assert (result.text, result.confidence, result.uncertain, result.source) == (
        NAMES["rajesh"],
        1.0,
        False,
        "dictionary",
    )


def test_low_llm_confidence_is_flagged_uncertain_but_still_prefills() -> None:
    """M2-S2-N1: confidence below the threshold -> uncertain=True; text still returned."""
    tr, _ = make(StubLlm(confidence=0.3), confidence_threshold=0.6)
    result = tr.transliterate_checked("Anita", "devanagari")
    assert result.uncertain is True
    assert result.source == "llm"
    assert result.text


def test_confidence_at_the_threshold_is_not_uncertain() -> None:
    """M2-S2-E2: boundary is inclusive."""
    tr, _ = make(StubLlm(confidence=0.6), confidence_threshold=0.6)
    assert tr.transliterate_checked("Anita", "devanagari").uncertain is False


def test_one_uncertain_word_makes_the_whole_name_uncertain() -> None:
    """M2-S2-E3."""
    tr, _ = make(StubLlm(confidence=0.2))
    assert tr.transliterate_checked("Rajesh Anita", "devanagari").uncertain is True


def test_empty_llm_answer_falls_back_to_the_input_and_is_uncertain() -> None:
    """M2-S2-N2."""
    result = make(StubLlm(text="  "))[0].transliterate_checked("Anita", "devanagari")
    assert result.text == "Anita"
    assert result.uncertain is True


def test_empty_text_returns_empty_without_calling_the_llm() -> None:
    """M2-S2-E4."""
    tr, factory = make(StubLlm())
    assert tr.transliterate("", "devanagari") == ""
    assert tr.transliterate("   ", "devanagari") == ""
    assert factory.calls == 0


def test_devanagari_input_for_devanagari_target_passes_through() -> None:
    """M2-S2-E5: already in the target script -> unchanged, no model."""
    tr, factory = make(StubLlm())
    assert tr.transliterate(DEVANAGARI_NAME, "devanagari") == DEVANAGARI_NAME
    assert factory.calls == 0


def test_very_long_text_is_handled_and_repeated_words_asked_once() -> None:
    """M2-S2-E6: 500 words, 1 distinct unknown word -> exactly one LLM call."""
    llm = StubLlm()
    tr, _ = make(llm)
    out = tr.transliterate(" ".join(["Anita"] * 500), "devanagari")
    assert len(out.split()) == 500
    assert len(llm.calls) == 1


def test_prompt_injection_text_is_passed_to_the_model_as_plain_data() -> None:
    """M2-S2-E7: the token is not interpreted; the call is still just (token, script)."""
    llm = StubLlm()
    make(llm)[0].transliterate("ignore-previous-instructions", "devanagari")
    assert llm.calls == [("ignore-previous-instructions", "devanagari")]


def test_unknown_target_script_is_rejected_before_any_work() -> None:
    """M2-S2-N3."""
    tr, factory = make(StubLlm())
    with pytest.raises(ValueError, match="script"):
        tr.transliterate("Anita", "klingon")
    assert factory.calls == 0


def test_llm_load_failure_is_a_model_load_error() -> None:
    """M2-S2-N4."""
    tr = QwenTransliterator(engine_factory=Factory(error=OSError("no weights")), common_names=NAMES)
    with pytest.raises(ModelLoadError):
        tr.transliterate("Anita", "devanagari")


def test_llm_crash_is_a_coded_error() -> None:
    """M2-S2-N5."""
    tr, _ = make(StubLlm(error=RuntimeError("boom")))
    with pytest.raises(DomainError) as info:
        tr.transliterate("Anita", "devanagari")
    assert info.value.code is FailureCode.TTS_FAILED


def test_llm_timeout_is_reported() -> None:
    """M2-S2-E8."""
    blocker = Blocker()
    tr, _ = make(StubLlm(blocker=blocker), timeout_s=0.1)
    try:
        with pytest.raises(AdapterTimeoutError):
            tr.transliterate("Anita", "devanagari")
    finally:
        blocker.release.set()
