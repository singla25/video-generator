"""The Modal app: faster-whisper speech-to-text and Chatterbox voice cloning on one warm GPU class.

Deployed with the Modal command line (never imported by the API or the worker). It holds no
secrets: Modal reads its own credentials from the caller's environment. Demo data only (C5).
The four module-level functions are what ``ModalRemoteClient`` looks up by name; they hand the
heavy work to the single ``Engine`` class, which loads both models once per container.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import modal

from vidgen.infrastructure.modal_ai.protocol import (
    DEFAULT_APP_NAME,
    FN_HAS_SAMPLE,
    FN_SYNTHESIZE,
    FN_TRANSCRIBE,
    FN_UPLOAD_SAMPLE,
)

logger = logging.getLogger(__name__)

TIMEOUT_S = 900
CPU_CORES = 4
MEM_MIB = 16 * 1024
SCALEDOWN_S = 60
MODELS_DIR = "/models"
SAMPLES_DIR = "/samples"
VOLUME_NAME = "vidgen-voice-samples"
WHISPER_REPO = "Systran/faster-whisper-small"
CHATTERBOX_REPO = "ResembleAI/chatterbox"
CHATTERBOX_FILES = [
    "ve.pt",
    "t3_mtl23ls_v2.safetensors",
    "s3gen.pt",
    "grapheme_mtl_merged_expanded_v1.json",
    "conds.pt",
    "Cangjie5_TC.json",
]
LANGUAGE = "hi"
GPU = os.environ.get("VIDGEN_MODAL_GPU", "L4")
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")  # a hash is used as a file name: never trust it

# Copied from the P2-S spike; every entry is an exact pin (the tests check this).
PINS = [
    "torch==2.14.1",
    "torchaudio==2.11.0",
    "transformers==5.20.2",
    "accelerate==1.15.0",
    "faster-whisper==1.2.1",
    "librosa==0.11.0",
    "s3tokenizer==0.3.0",
    "diffusers==0.29.0",
    "resemble-perth==1.0.1",
    "conformer==0.3.2",
    "safetensors==0.8.0",
    "pykakasi==2.3.0",
    "pyloudnorm==0.2.0",
    "omegaconf==2.0.6",
    "numpy==1.26.4",
    "soundfile==0.14.0",
    "setuptools==80.10.2",
    "huggingface_hub==2.3.0",  # the version the project lockfile resolved with these pins
]


def download_models() -> None:
    """Build-time step: fetch the public model weights into the image."""
    from huggingface_hub import snapshot_download

    snapshot_download(WHISPER_REPO, local_dir=f"{MODELS_DIR}/whisper")
    snapshot_download(
        CHATTERBOX_REPO, local_dir=f"{MODELS_DIR}/chatterbox", allow_patterns=CHATTERBOX_FILES
    )


image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libsndfile1", "ffmpeg")
    .uv_pip_install(*PINS)
    .run_commands("uv pip install --system --no-deps chatterbox-tts==0.1.7")
    .run_function(download_models)
    .add_local_python_source("vidgen")  # last step: Modal requires local sources last
)

app = modal.App(DEFAULT_APP_NAME)
samples = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


@app.cls(
    image=image,
    gpu=GPU,
    timeout=TIMEOUT_S,
    cpu=CPU_CORES,
    memory=MEM_MIB,
    scaledown_window=SCALEDOWN_S,
)
class Engine:
    """One warm container: faster-whisper and Chatterbox are loaded once in ``load``."""

    @modal.enter()
    def load(self) -> None:
        """Load both models onto the GPU once per container."""
        import sysconfig

        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        from faster_whisper import WhisperModel

        # CTranslate2 needs the cuDNN / cuBLAS libraries that the torch wheels ship.
        libs = sorted(Path(sysconfig.get_paths()["purelib"]).glob("nvidia/*/lib"))
        os.environ["LD_LIBRARY_PATH"] = ":".join(
            [str(p) for p in libs] + [os.environ.get("LD_LIBRARY_PATH", "")]
        )
        self.whisper = WhisperModel(f"{MODELS_DIR}/whisper", device="cuda", compute_type="float16")
        self.tts = ChatterboxMultilingualTTS.from_local(
            f"{MODELS_DIR}/chatterbox", torch.device("cuda")
        )

    @modal.method()
    def run_transcribe(self, audio: bytes, hint: str | None) -> list[dict[str, Any]]:
        """Words with timestamps; ``hint`` (a name) goes to faster-whisper as ``hotwords``."""
        path = Path("/tmp/in.wav")  # noqa: S108 - container-local scratch
        path.write_bytes(audio)
        segments, _ = self.whisper.transcribe(
            str(path), language=LANGUAGE, word_timestamps=True, hotwords=hint or None
        )
        return [
            {
                "text": w.word.strip(),
                "start_s": float(w.start),
                "end_s": float(w.end),
                "confidence": float(w.probability),
            }
            for s in segments
            for w in (s.words or [])
        ]

    @modal.method()
    def run_synthesize(self, text: str, sample: bytes) -> bytes:
        """Speak ``text`` in the voice of ``sample``; returns 16-bit WAV bytes."""
        import io

        import soundfile as sf
        import torch

        prompt = Path("/tmp/sample.wav")  # noqa: S108 - container-local scratch
        prompt.write_bytes(sample)
        started = time.time()
        wav = self.tts.generate(text, language_id=LANGUAGE, audio_prompt_path=str(prompt))
        torch.cuda.synchronize()
        logger.info("synthesize done", extra={"seconds": round(time.time() - started, 2)})
        buffer = io.BytesIO()
        sf.write(
            buffer, wav.cpu().squeeze().numpy(), int(self.tts.sr), format="WAV", subtype="PCM_16"
        )
        return buffer.getvalue()


def _sample_path(sample_hash: str) -> Path:
    """The volume path of a sample; anything but a SHA-256 hex digest is refused."""
    if not SHA256_HEX.match(sample_hash):
        raise ValueError("sample_hash must be a SHA-256 hex digest")
    return Path(SAMPLES_DIR) / f"{sample_hash}.wav"


@app.function(image=image, volumes={SAMPLES_DIR: samples}, timeout=TIMEOUT_S)
def transcribe(audio: bytes, hint: str | None = None) -> list[dict[str, Any]]:
    """Remote speech-to-text; the client calls this by name."""
    return Engine().run_transcribe.remote(audio, hint)  # type: ignore[no-any-return]


@app.function(image=image, volumes={SAMPLES_DIR: samples}, timeout=TIMEOUT_S)
def has_sample(sample_hash: str) -> bool:
    """True if the voice sample with this SHA-256 is stored."""
    samples.reload()
    return _sample_path(sample_hash).is_file()


@app.function(image=image, volumes={SAMPLES_DIR: samples}, timeout=TIMEOUT_S)
def upload_sample(sample_hash: str, data: bytes) -> None:
    """Store the voice sample under its SHA-256."""
    path = _sample_path(sample_hash)
    path.write_bytes(data)
    samples.commit()


@app.function(image=image, volumes={SAMPLES_DIR: samples}, timeout=TIMEOUT_S)
def synthesize(text: str, sample_hash: str) -> bytes:
    """Remote voice cloning from a stored sample; returns WAV bytes."""
    samples.reload()
    sample = _sample_path(sample_hash).read_bytes()
    return Engine().run_synthesize.remote(text, sample)  # type: ignore[no-any-return]


# The function names are the shared contract; fail at import time if they drift from protocol.
if [transcribe.__name__, has_sample.__name__, upload_sample.__name__, synthesize.__name__] != [
    FN_TRANSCRIBE,
    FN_HAS_SAMPLE,
    FN_UPLOAD_SAMPLE,
    FN_SYNTHESIZE,
]:
    raise RuntimeError("remote function names differ from vidgen.infrastructure.modal_ai.protocol")
