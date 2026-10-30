"""Timing variants (DD-33): re-splice one already lip-synced row with other pause/crossfade values.

Usage (one process at a time, models are loaded only for Whisper, no new TTS or lip sync):

    VIDGEN_PAUSE_SECONDS=0.7 VIDGEN_CROSSFADE_MS=40 PYTHONPATH=backend \
        .venv-m2/bin/python backend/spikes/m2_mac/timing_variants.py render B
    PYTHONPATH=backend .venv-m2/bin/python backend/spikes/m2_mac/timing_variants.py measure A B C

``render`` re-uses speech0.wav, synced0.mp4 and label.png left by backend/scripts/local_ai_smoke.py
and splices with the app's FfmpegVideoEncoder and plan_timing. ``measure`` transcribes each output
with the app's Whisper adapter and prints name end / next word start / gap.
Only timings are printed.
Set VIDGEN_SPIKE_ROW_ID to the real row id (kept out of git) to find your local outputs.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend" / "scripts"))
import local_ai_smoke as smoke  # noqa: E402

OUT = smoke.OUT_DIR
TIMING = OUT / "timing"
TMP = OUT / "_tmp"
ROW_ID = os.environ.get("VIDGEN_SPIKE_ROW_ID", "row-1")


def _adapters():  # type: ignore[no-untyped-def]
    from vidgen.infrastructure.local_ai.factory import build_ai_adapters
    from vidgen.settings import Settings

    settings = Settings()  # type: ignore[call-arg]
    return settings, build_ai_adapters(settings)


def _words(adapters, video: Path):  # type: ignore[no-untyped-def]
    audio = TMP / f"{video.stem}_16k.wav"
    smoke._run(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        str(video),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(audio),
    )
    words = adapters.stt.transcribe(audio)
    adapters.stt.release()
    return words


def _slot() -> dict[str, float]:
    """Name slot and next-word start of the template, cached after the first Whisper run."""
    cache = TIMING / "slot.json"
    if cache.exists():
        return json.loads(cache.read_text())
    from vidgen.infrastructure.local_ai.name_slot import detect_name_slot

    _, adapters = _adapters()
    words = _words(adapters, smoke.SAMPLES / "template_video.mp4")
    slot = detect_name_slot(words, words[0].text)
    nxt = min(w.start_s for w in words if w.start_s >= slot.end_s)
    data = {"start": slot.start_s, "end": slot.end_s, "next": nxt}
    cache.write_text(json.dumps(data))
    return data


def render(name: str) -> None:
    """Splice variant ``name`` using the pause/crossfade from the environment."""
    from vidgen.domain.timing import TimingRules, plan_timing
    from vidgen.infrastructure.ffmpeg.encoder import FfmpegVideoEncoder

    smoke._prepare_environment()
    settings, _ = None, None
    from vidgen.settings import Settings

    settings = Settings()  # type: ignore[call-arg]
    TIMING.mkdir(parents=True, exist_ok=True)
    slot = _slot()
    wav = TMP / "speech0.wav"
    import wave

    with wave.open(str(wav)) as f:
        seconds = f.getnframes() / f.getframerate()
    plan = plan_timing(
        slot["end"] - slot["start"],
        settings.pause_seconds,
        seconds,
        TimingRules(crossfade_ms=settings.crossfade_ms),
        gap_s=settings.name_gap_s,
    )
    out = TIMING / f"{ROW_ID}_{name}.mp4"
    out.unlink(missing_ok=True)
    meta = {
        "creator_entity": "Local smoke test",
        "generated_on": date.today().isoformat(),
        "batch_id": "local-smoke",
    }
    FfmpegVideoEncoder("ffmpeg", crossfade_ms=settings.crossfade_ms).render(
        TMP / "synced0.mp4", wav, (slot["start"], slot["end"]), plan, TMP / "label.png", meta, out
    )
    print(
        f"{name}: pause {settings.pause_seconds}, crossfade {settings.crossfade_ms} ms, "
        f"gap {settings.name_gap_s}, "
        f"speech {seconds:.3f}s, slot {slot['start']:.2f}-{slot['end']:.2f}, plan {plan}"
    )


def measure(names: list[str]) -> None:
    """Print duration/size/fps and the name-end to next-word gap for each output."""
    smoke._prepare_environment()
    _, adapters = _adapters()
    _slot()  # called for its side effect: fills the slot cache if it is missing
    for name in names:
        video = TIMING / f"{ROW_ID}_{name}.mp4"
        info = smoke._probe(video)
        fps = smoke._run(
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=r_frame_rate",
            "-of",
            "csv=p=0",
            str(video),
        ).strip()
        words = _words(adapters, video)
        print(
            name, info, fps, [(w.text, round(w.start_s, 2), round(w.end_s, 2)) for w in words[:4]]
        )


if __name__ == "__main__":
    if sys.argv[1] == "render":
        render(sys.argv[2])
    elif sys.argv[1] == "copy":
        TIMING.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUT / f"{ROW_ID}.mp4", TIMING / f"{ROW_ID}_A.mp4")
    else:
        measure(sys.argv[2:])
