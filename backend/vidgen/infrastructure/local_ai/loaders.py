"""Default model loaders. torch, transformers and friends are imported only inside these."""

from __future__ import annotations

import copy
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from vidgen.infrastructure.local_ai import musetalk_support as support
from vidgen.infrastructure.local_ai.compositing import composite_mouth
from vidgen.infrastructure.local_ai.errors import LocalAiError

WHISPER_COMPUTE_TYPE = "int8"
QWEN_MAX_NEW_TOKENS = 40
CHATTERBOX_LANGUAGE = "hi"
MUSETALK_REPO_DIR = "repo"  # the patched clone made by backend/scripts/setup_musetalk.py
MUSETALK_CROP = 256
MUSETALK_EXTRA_MARGIN = 10
MUSETALK_CHEEK_WIDTH = 90
MUSETALK_BATCH = 8
MUSETALK_AUDIO_PAD = 2
MUSETALK_PARSING_MODE = "jaw"


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


@contextmanager
def _working_dir(folder: Path) -> Iterator[None]:
    """MuseTalk reads ``./models/...``; run it from its clone, then go back."""
    previous = Path.cwd()
    os.chdir(folder)
    try:
        yield
    finally:
        os.chdir(previous)


class _MuseTalkModel:
    """``run(video, audio, out)`` around the vendored MuseTalk v1.5, loaded once, in-process.

    Peak memory is 16-18 GB (float32, MPS), so callers hold a ``SingleRenderGuard``.
    """

    def __init__(self, weights_dir: Path) -> None:
        self._repo = weights_dir.resolve() / MUSETALK_REPO_DIR
        if not (self._repo / "musetalk").is_dir():
            raise LocalAiError(
                "MuseTalk is not set up; run backend/scripts/setup_musetalk.py first"
            )
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        import torch  # type: ignore[import-not-found,unused-ignore]

        self._torch = torch
        self._device = torch.device(pick_device())
        self._cache = support.LandmarkCache(weights_dir.resolve() / support.CACHE_DIR_NAME)
        if str(self._repo) not in sys.path:
            sys.path.insert(0, str(self._repo))
        with _working_dir(self._repo):
            self._load_models()

    def _load_models(self) -> None:
        from musetalk.utils import preprocessing, utils  # type: ignore[import-not-found,unused-ignore]
        from musetalk.utils.audio_processor import AudioProcessor  # type: ignore[import-not-found,unused-ignore]
        from musetalk.utils.blending import get_image  # type: ignore[import-not-found,unused-ignore]
        from musetalk.utils.face_parsing import FaceParsing  # type: ignore[import-not-found,unused-ignore]
        from transformers import WhisperModel  # type: ignore[import-not-found,unused-ignore]

        self._utils, self._pre, self._get_image = utils, preprocessing, get_image
        models = Path("models")
        self._vae, self._unet, self._pe = utils.load_all_model(
            unet_model_path=str(models / "musetalkV15" / "unet.pth"),
            vae_type="sd-vae",
            unet_config=str(models / "musetalkV15" / "musetalk.json"),
            device=self._device,
        )
        self._pe = self._pe.to(self._device)
        self._vae.vae = self._vae.vae.to(self._device)
        self._unet.model = self._unet.model.to(self._device)
        self._dtype = self._unet.model.dtype
        whisper_dir = str(models / "whisper")
        self._audio = AudioProcessor(feature_extractor_path=whisper_dir)
        whisper = WhisperModel.from_pretrained(whisper_dir)
        self._whisper = whisper.to(device=self._device, dtype=self._dtype).eval()
        self._whisper.requires_grad_(False)
        self._parser = FaceParsing(
            left_cheek_width=MUSETALK_CHEEK_WIDTH, right_cheek_width=MUSETALK_CHEEK_WIDTH
        )
        self._timesteps = self._torch.tensor([0], device=self._device)

    def run(self, video: Path, audio: Path, out: Path) -> None:
        """Lip-sync the start of ``video`` to ``audio``; the rest of the video is kept as is."""
        video, audio, out = video.resolve(), audio.resolve(), out.resolve()
        try:
            with TemporaryDirectory(prefix="musetalk-") as folder, _working_dir(self._repo):
                work = Path(folder)
                frames_dir, blended = work / "frames", work / "blended"
                frames_dir.mkdir()
                blended.mkdir()
                with self._torch.no_grad():
                    chunks = self._whisper_chunks(audio)
                    paths = support.extract_frames(video, frames_dir, len(chunks))
                    self._blend(video, paths, chunks, blended)
                support.assemble_video(blended, len(chunks), video, out)
        finally:
            self._release_memory()

    def _whisper_chunks(self, audio: Path) -> Any:
        features, length = self._audio.get_audio_feature(str(audio))
        return self._audio.get_whisper_chunk(
            features,
            self._device,
            self._dtype,
            self._whisper,
            length,
            fps=support.MUSETALK_FPS,
            audio_padding_length_left=MUSETALK_AUDIO_PAD,
            audio_padding_length_right=MUSETALK_AUDIO_PAD,
        )

    def _boxes_and_frames(self, video: Path, paths: list[Path]) -> tuple[list[Any], list[Any]]:
        """Face boxes (cached per template, the slow part) and the decoded frames."""
        key = support.video_fingerprint(video)
        names = [str(p) for p in paths]
        cached = self._cache.get(key, len(paths))
        if cached is not None:
            return list(cached), self._pre.read_imgs(names)
        boxes, frames = self._pre.get_landmark_and_bbox(names, 0)
        self._cache.put(key, [(int(b[0]), int(b[1]), int(b[2]), int(b[3])) for b in boxes])
        return boxes, frames

    def _blend(self, video: Path, paths: list[Path], chunks: Any, blended: Path) -> None:
        """Generate the mouth for every audio chunk and paste it back into the frames."""
        import cv2  # type: ignore[import-not-found,unused-ignore]
        import numpy as np  # type: ignore[import-not-found,unused-ignore]

        placeholder = tuple(self._pre.coord_placeholder)
        boxes, frames = self._boxes_and_frames(video, paths)
        latents = []
        for box, frame in zip(boxes, frames, strict=False):
            if tuple(box) == placeholder:
                continue
            x1, y1, x2, y2 = box
            y2 = min(y2 + MUSETALK_EXTRA_MARGIN, frame.shape[0])
            crop = cv2.resize(
                frame[y1:y2, x1:x2],
                (MUSETALK_CROP, MUSETALK_CROP),
                interpolation=cv2.INTER_LANCZOS4,
            )
            latents.append(self._vae.get_latents_for_unet(crop))
        if not latents:
            raise LocalAiError("no face found in the template")
        frames_cycle, boxes_cycle = frames + frames[::-1], boxes + boxes[::-1]
        batches = self._utils.datagen(
            whisper_chunks=chunks,
            vae_encode_latents=latents + latents[::-1],
            batch_size=MUSETALK_BATCH,
            delay_frame=0,
            device=self._device,
        )
        index = 0
        for whisper_batch, latent_batch in batches:
            predicted = self._unet.model(
                latent_batch.to(dtype=self._dtype),
                self._timesteps,
                encoder_hidden_states=self._pe(whisper_batch),
            ).sample
            for result in self._vae.decode_latents(predicted):
                x1, y1, x2, y2 = boxes_cycle[index % len(boxes_cycle)]
                original = copy.deepcopy(frames_cycle[index % len(frames_cycle)])
                y2 = min(y2 + MUSETALK_EXTRA_MARGIN, original.shape[0])
                face = cv2.resize(result.astype(np.uint8), (x2 - x1, y2 - y1))
                merged = self._paste(original, face, (x1, y1, x2, y2))
                cv2.imwrite(str(blended / f"{index:08d}.png"), merged)
                index += 1
        if index != len(chunks):
            raise LocalAiError("lip sync produced an unexpected number of frames")

    def _paste(self, original: Any, face: Any, box: support.Box) -> Any:
        """Put the generated face into the frame: only the mouth changes (L8).

        MuseTalk's own blend replaces the whole lower face (beard comes out smooth and lighter),
        so real images go through ``composite_mouth``. Anything that is not an image array
        (the unit-test fakes) keeps MuseTalk's own blend.
        """
        if hasattr(original, "astype"):
            return composite_mouth(original, face, box)
        return self._get_image(
            original, face, list(box), mode=MUSETALK_PARSING_MODE, fp=self._parser
        )

    def _release_memory(self) -> None:
        """Give the MPS cache back between renders (the models stay loaded)."""
        if self._device.type == "mps":
            self._torch.mps.empty_cache()


def load_musetalk(weights_dir: Path) -> Any:
    """Local MuseTalk v1.5 runner; models load here, once, from the set-up clone."""
    return _MuseTalkModel(weights_dir)
