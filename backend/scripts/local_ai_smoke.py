"""Smoke run of AI_MODE=local on this Mac: renders a few real videos with the app's own adapters.

Usage (one process only, a render peaks at 16-18 GB; do not start the app meanwhile):

    PYTHONPATH=backend .venv-m2/bin/python backend/scripts/local_ai_smoke.py [--rows 2]
        [--template PATH] [--slot START END] [--sheet PATH.csv] [--out-name NAME]

Pipeline per sheet row: transcribe the template once -> find the name slot (or take --slot) ->
pre-fill the spoken name (Qwen) -> clone the voice (Chatterbox) -> lip sync (MuseTalk) -> splice,
add the AI label (FFmpeg encoder). Models run one stage at a time and are released in between
so they fit in RAM. Only row indexes are printed, never names or ids. Outputs go to the
git-ignored work folder (or its sub-folder NAME). Pilot weights, this Mac only (DD-31): nothing
leaves the machine.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import resource
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "backend" / "spikes" / "m2_mac" / "work"
SAMPLES = ROOT / "samples"
WEIGHTS = WORK / "local_ai_weights"
OUT_DIR = WORK / "local_out"
SAMPLE_RATE = 16000
VOICE_SAMPLE_START_S, VOICE_SAMPLE_LEN_S = 2.0, 10.0
HONORIFIC = "जी"  # the template says "<name> ji"
DEFAULT_PAUSE_S = 0.3
CSV_HEADER = ["Name", "VID"]
BYTES_PER_GB = 1024**3
# Placeholder values only: the smoke run never uses secrets, but Settings insists on them.
PLACEHOLDER_ENV = {
    "VIDGEN_CREATOR_ENTITY": "Local smoke test",
    "VIDGEN_ENCRYPTION_KEY": "x" * 32,
    "VIDGEN_INDEX_KEY": "x" * 32,
    "VIDGEN_SESSION_SECRET": "x" * 32,
    "VIDGEN_ADMIN_PASSWORD_HASH": "x",
}


def _prepare_environment() -> None:
    """Point the app settings at the local weights; torch's cache stays inside the project."""
    os.environ.update({k: v for k, v in PLACEHOLDER_ENV.items() if k not in os.environ})
    os.environ["VIDGEN_AI_MODE"] = "local"
    os.environ["VIDGEN_LOCAL_AI_WEIGHTS_DIR"] = str(WEIGHTS)
    os.environ.setdefault("TORCH_HOME", str(WORK / "torch"))
    # .venv-m2 has the models but not the web stack; borrow pure helpers from .venv, last in line.
    for site in (ROOT / ".venv" / "lib").glob("python3.*/site-packages"):
        sys.path.append(str(site))


def _peak_rss_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / BYTES_PER_GB  # bytes on macOS


def _mps_gb() -> float:
    import torch  # type: ignore[import-not-found,unused-ignore]

    return (
        float(torch.mps.driver_allocated_memory()) / BYTES_PER_GB
        if torch.mps.is_available()
        else 0.0
    )


def _run(*command: str) -> str:
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout  # noqa: S603


def _probe(path: Path) -> dict[str, float]:
    """Duration, width and height of the first video stream."""
    data = json.loads(
        _run(
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "json",
            str(path),
        )
    )
    stream = data["streams"][0]
    return {
        "duration": float(data["format"]["duration"]),
        "width": float(stream["width"]),
        "height": float(stream["height"]),
    }


def _fidelity_report(template: Path, synced: Path, tmp: Path, start_s: float) -> str:
    """Lower-face (without the mouth) similarity of the lip-synced frames to the template."""
    import cv2  # type: ignore[import-not-found,unused-ignore]

    from vidgen.infrastructure.local_ai import musetalk_support as support
    from vidgen.infrastructure.local_ai.fidelity import frame_fidelity, mean_fidelity

    key = support.landmark_key(support.video_fingerprint(template), start_s)
    cached = WEIGHTS / "musetalk" / support.CACHE_DIR_NAME / f"{key}.json"
    boxes = [tuple(int(v) for v in box) for box in json.loads(cached.read_text())]
    folders = {}
    for name, video in (("orig", template), ("sync", synced)):
        folders[name] = tmp / f"fid_{name}"
        folders[name].mkdir(exist_ok=True)
        support.extract_frames(video, folders[name], len(boxes))
    scores = [
        frame_fidelity(
            cv2.imread(str(folders["orig"] / f"{i:08d}.png")),
            cv2.imread(str(folders["sync"] / f"{i:08d}.png")),
            box,
        )
        for i, box in enumerate(boxes)
    ]
    mean = mean_fidelity(scores)
    return (
        f"lower-face (mouth excluded, {len(scores)} frames): SSIM {mean.ssim:.3f}, "
        f"mean abs diff {mean.mean_abs_diff:.2f}/255, texture retention {mean.texture_ratio:.2f} "
        f"(target >= 0.85)"
    )


class Timer:
    """Prints how long each stage took and the memory high-water marks so far."""

    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.stages: dict[str, float] = {}

    def stage(self, name: str, since: float) -> None:
        seconds = time.perf_counter() - since
        self.stages[name] = self.stages.get(name, 0.0) + seconds
        print(
            f"[{name}] {seconds:6.1f}s  peak RSS {_peak_rss_gb():5.1f} GB  MPS {_mps_gb():4.1f} GB",
            flush=True,
        )


def _template_slot(  # type: ignore[no-untyped-def]
    adapters,
    template: Path,
    tmp: Path,
    timer: Timer,
    manual: tuple[float, float] | None,
):
    """Transcribe the template and return (slot, pause_s, voice_sample).

    The transcript always gives the pause after the name; the slot itself is the manual one
    when ``manual`` is given, otherwise the first word that matches the opening name.
    """
    from vidgen.infrastructure.local_ai.name_slot import detect_name_slot

    audio = tmp / "template16k.wav"
    _run(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        str(template),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        str(audio),
    )
    sample = tmp / "voice_sample.wav"
    start, length = str(VOICE_SAMPLE_START_S), str(VOICE_SAMPLE_LEN_S)
    _run("ffmpeg", "-v", "error", "-y", "-ss", start, "-t", length, "-i", str(audio), str(sample))
    started = time.perf_counter()
    words = adapters.stt.transcribe(audio)
    adapters.stt.release()
    timer.stage("stt", started)
    if not words:
        raise SystemExit("no speech found in the template")
    slot = detect_name_slot(words, words[0].text, manual=manual)  # default: opening name
    following = [w.start_s for w in words if w.start_s >= slot.end_s]
    pause = (following[0] - slot.end_s) if following else DEFAULT_PAUSE_S
    print(
        f"slot {slot.start_s:.2f}-{slot.end_s:.2f}s, ambiguous={slot.ambiguous}, pause {pause:.2f}s"
    )
    return slot, max(pause, 0.0), sample


def _names(sheet: Path, count: int) -> list[tuple[str, str]]:
    """The first ``count`` (name, id) pairs of the sample sheet."""
    from vidgen.infrastructure.sheets.reader import FileSheetReader

    rows = FileSheetReader().numbered_rows(sheet)
    return [
        (r.cells[0].strip(), r.cells[1].strip()) for _, r in zip(range(count), rows, strict=False)
    ]


def _csv_names(sheet: Path, count: int) -> list[tuple[str, str]]:
    """The first ``count`` (name, id) pairs of a csv sheet whose header row is ``Name,VID``.

    Blank lines are skipped. Errors name the line number only, never the content of a row.
    """
    with sheet.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = [cell.strip() for cell in next(reader, [])]
        if header != CSV_HEADER:
            raise SystemExit(f"the sheet header must be {','.join(CSV_HEADER)}")
        pairs: list[tuple[str, str]] = []
        for line_no, row in enumerate(reader, start=2):
            if len(pairs) == count:
                break
            if not any(cell.strip() for cell in row):
                continue
            if len(row) != len(CSV_HEADER):
                raise SystemExit(f"csv line {line_no} must have exactly two cells")
            pairs.append((row[0].strip(), row[1].strip()))
    return pairs


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Command line options; every option keeps the old default when omitted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=2)
    parser.add_argument("--template", type=Path, default=SAMPLES / "template_video.mp4")
    parser.add_argument(
        "--slot",
        nargs=2,
        type=float,
        metavar=("START", "END"),
        help="manual name slot in seconds; skips the transcript-based slot search",
    )
    parser.add_argument("--sheet", type=Path, help="csv sheet with header Name,VID")
    parser.add_argument("--out-name", help="sub-folder of local_out/ for the outputs")
    args = parser.parse_args(argv)
    if args.slot is not None and not 0 <= args.slot[0] < args.slot[1]:
        parser.error("--slot needs START >= 0 and END > START")
    if args.out_name is not None and Path(args.out_name).name != args.out_name:
        parser.error("--out-name must be a plain folder name")
    return args


def main() -> int:
    """Run the smoke test; returns the process exit code."""
    args = _parse_args(None)
    _prepare_environment()

    from vidgen.domain.timing import TimingRules, plan_timing
    from vidgen.infrastructure.ffmpeg.encoder import FfmpegVideoEncoder
    from vidgen.infrastructure.ffmpeg.label import build_label_renderer, label_band_height
    from vidgen.infrastructure.local_ai.factory import build_ai_adapters
    from vidgen.services.spoken_text import spoken_text
    from vidgen.settings import Settings
    from vidgen.worker.runner import DEVANAGARI_FONT, FONT_DIR, LATIN_FONT

    settings = Settings()  # type: ignore[call-arg]  # secrets come from the placeholder env
    adapters: Any = build_ai_adapters(settings)  # the real classes also have release()
    template = args.template.resolve()
    if args.sheet is not None:
        people = _csv_names(args.sheet.resolve(), args.rows)
    else:
        people = _names(SAMPLES / "source_list.xlsx", args.rows)
    out_dir = OUT_DIR / args.out_name if args.out_name else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "_tmp"
    tmp.mkdir(exist_ok=True)
    timer, info = Timer(), _probe(template)
    manual = (args.slot[0], args.slot[1]) if args.slot is not None else None
    slot, pause, sample = _template_slot(adapters, template, tmp, timer, manual)

    started = time.perf_counter()
    spoken = [adapters.transliterator.transliterate(name, "Devanagari") for name, _ in people]
    adapters.transliterator.release()
    timer.stage("transliterate", started)

    speech: list[tuple[Path, float]] = []
    started = time.perf_counter()
    for index, text in enumerate(spoken):
        wav = tmp / f"speech{index}.wav"
        seconds = adapters.voice.synthesize(spoken_text(text, HONORIFIC), sample, wav)
        speech.append((wav, seconds))
        print(f"row {index}: speech {seconds:.2f}s")
    adapters.voice.release()
    timer.stage("voice", started)

    labels = build_label_renderer(
        settings.label_style, FONT_DIR / DEVANAGARI_FONT, FONT_DIR / LATIN_FONT
    )
    encoder = FfmpegVideoEncoder("ffmpeg", crossfade_ms=settings.crossfade_ms)
    band = label_band_height(int(info["height"]))
    label = tmp / "label.png"
    bubble = settings.label_style == "bubble"  # the bubble renderer takes the frame height
    labels.render_label(int(info["width"]), int(info["height"]) if bubble else band, label)
    print(f"label style: {settings.label_style}")
    failures = 0
    metadata = {
        "creator_entity": "Local smoke test",
        "generated_on": date.today().isoformat(),
        "batch_id": "local-smoke",
    }
    for index, ((_, voter_id), (wav, seconds)) in enumerate(zip(people, speech, strict=True)):
        started = time.perf_counter()
        synced = tmp / f"synced{index}.mp4"
        adapters.lipsync.sync(template, wav, synced, start_s=slot.start_s)
        timer.stage("lipsync", started)
        print(f"row {index}: {_fidelity_report(template, synced, tmp, slot.start_s)}")
        started = time.perf_counter()
        out = out_dir / f"{voter_id}.mp4"
        out.unlink(missing_ok=True)
        plan = plan_timing(
            slot.end_s - slot.start_s,
            pause,
            seconds,
            TimingRules(crossfade_ms=settings.crossfade_ms),
            gap_s=settings.name_gap_s,
        )
        encoder.render(
            synced,
            wav,
            (slot.start_s, slot.end_s),
            plan,
            label,
            metadata,
            out,
        )
        timer.stage("encode", started)
        result = _probe(out)
        ok = abs(result["duration"] - info["duration"] - plan.duration_delta_s) < 0.1 and (
            bubble or band / result["height"] >= 0.10
        )
        failures += 0 if ok else 1
        share = band / result["height"]
        print(
            f"row {index}: {result['duration']:.2f}s (template {info['duration']:.2f}s) "
            f"{int(result['width'])}x{int(result['height'])} label band {share:.1%} "
            f"{'OK' if ok else 'CHECK FAILED'}"
        )
    adapters.lipsync.release()
    stages = {k: round(v, 1) for k, v in timer.stages.items()}
    print(
        f"total {time.perf_counter() - timer.started:.0f}s; peak RSS {_peak_rss_gb():.1f} GB; "
        f"stage seconds {json.dumps(stages)}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
