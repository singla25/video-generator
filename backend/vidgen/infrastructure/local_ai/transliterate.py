"""Name transliteration with a small local LLM (Qwen). Pre-fills the spoken name only (ADR-012)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vidgen.infrastructure.local_ai._common import LazyModel, Loader
from vidgen.infrastructure.local_ai.loaders import load_qwen

INSTRUCTION = (
    "Transliterate Indian names into {script}. Output only the name in {script}, nothing else. "
    "Keep the pronunciation as spoken in Hindi."
)
DEVANAGARI_EXAMPLES = (
    "\nExamples:\nSuresh Patel -> सुरेश पटेल\nGeeta Rani -> गीता रानी\n"
    "Harpreet Singh -> हरप्रीत सिंह\nVishal Chauhan -> विशाल चौहान\nKishan Lal -> किशन लाल\n"
)


def build_prompt(text: str, target_script: str) -> str:
    """The instruction, few-shot examples (Devanagari only) and the name to convert."""
    examples = DEVANAGARI_EXAMPLES if target_script.casefold() == "devanagari" else "\n"
    return INSTRUCTION.format(script=target_script) + examples + f"{text} ->"


def clean_answer(raw: str) -> str:
    """Keep only the first non-empty line and drop any echoed arrow."""
    for line in raw.splitlines():
        cleaned = line.replace("->", "").strip()
        if cleaned:
            return cleaned
    return ""


class QwenTransliterator:
    """``Transliterator`` port backed by a lazily loaded instruction-tuned LLM."""

    def __init__(self, weights_dir: Path, loader: Loader[Any] = load_qwen) -> None:
        self._model = LazyModel("transliteration", weights_dir, loader)

    def transliterate(self, text: str, target_script: str) -> str:
        """Return ``text`` in ``target_script``; blank input gives "" without using the model."""
        if not text.strip():
            return ""
        return clean_answer(self._model.get().generate(build_prompt(text.strip(), target_script)))

    def release(self) -> None:
        """Unload the model to free memory; it loads again on the next use."""
        self._model.release()
