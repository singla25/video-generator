"""Default model loaders. torch, transformers and friends are imported only inside these."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vidgen.infrastructure.local_ai.errors import LocalAiError

WHISPER_COMPUTE_TYPE = "int8"
QWEN_MAX_NEW_TOKENS = 40
CHATTERBOX_LANGUAGE = "hi"


def pick_device() -> str:
    """``mps`` on Apple silicon when available, else ``cpu``."""
    import torch  # type: ignore[import-not-found,unused-ignore]

    return "mps" if torch.backends.mps.is_available() else "cpu"


def load_whisper(weights_dir: Path) -> Any:
    """faster-whisper model from a local folder (CPU, int8)."""
    from faster_whisper import WhisperModel  # type: ignore[import-not-found,unused-ignore]

    return WhisperModel(
        str(weights_dir), device="cpu", compute_type=WHISPER_COMPUTE_TYPE, local_files_only=True
    )


class _QwenModel:
    """``generate(prompt) -> text`` around a transformers causal LM."""

    def __init__(self, weights_dir: Path) -> None:
        import torch  # type: ignore[import-not-found,unused-ignore]
        from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore[import-not-found,unused-ignore]

        self._torch = torch
        self._device = pick_device()
        self._tok = AutoTokenizer.from_pretrained(str(weights_dir), local_files_only=True)
        self._lm = (
            AutoModelForCausalLM.from_pretrained(
                str(weights_dir), dtype=torch.bfloat16, local_files_only=True
            )
            .to(self._device)
            .eval()
        )

    def generate(self, prompt: str) -> str:
        """Greedy answer to a single user message."""
        ids = self._tok.apply_chat_template(
            [{"role": "user", "content": prompt}],
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        ).to(self._device)
        with self._torch.no_grad():
            out = self._lm.generate(**ids, max_new_tokens=QWEN_MAX_NEW_TOKENS, do_sample=False)
        return str(self._tok.decode(out[0, ids["input_ids"].shape[-1] :], skip_special_tokens=True))


def load_qwen(weights_dir: Path) -> Any:
    """Local Qwen instruction model."""
    return _QwenModel(weights_dir)


class _ChatterboxModel:
    """``generate(text, voice_sample) -> (samples, rate)`` around Chatterbox-Multilingual."""

    def __init__(self, weights_dir: Path) -> None:
        import torch  # type: ignore[import-not-found,unused-ignore]
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # type: ignore[import-not-found,unused-ignore]

        device = torch.device(pick_device())
        original = torch.load
        # Checkpoints were saved on CUDA; map them onto this machine's device while loading.
        torch.load = lambda *a, **k: original(*a, **{**k, "map_location": device})
        try:
            self._tts = ChatterboxMultilingualTTS.from_local(str(weights_dir), device)
        finally:
            torch.load = original

    def generate(self, text: str, voice_sample: Path) -> tuple[list[float], int]:
        """Speech cloned from ``voice_sample`` as float samples in [-1, 1]."""
        wav = self._tts.generate(
            text, language_id=CHATTERBOX_LANGUAGE, audio_prompt_path=str(voice_sample)
        )
        return wav.cpu().squeeze().numpy().tolist(), int(self._tts.sr)


def load_chatterbox(weights_dir: Path) -> Any:
    """Local Chatterbox-Multilingual model."""
    return _ChatterboxModel(weights_dir)


def load_musetalk(weights_dir: Path) -> Any:
    """MuseTalk runner (subprocess around the vendored scripts) arrives with task L4."""
    raise LocalAiError("MuseTalk runtime is not wired yet (task L4)")
