"""Compare Whisper model sizes on demo audio: is the typed name found, how long, how much memory.

Usage (offline; it never downloads, it only reads the sizes already in the folder):

    PYTHONPATH=backend python backend/scripts/whisper_size_test.py \
        --weights-root PATH --name Krishan --audio demo1.wav [--audio demo2.wav]

``--weights-root`` holds one sub-folder per size (``small/``, ``medium/``, ...). One table row per
size and audio file goes to stdout. Nothing is written and no setting is changed: you pick the
default. Exit code 2 for a missing folder or audio file, or no size sub-folder.
"""

from __future__ import annotations

import argparse
import os
import resource
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # no network, whatever the libraries would try

from vidgen.domain.name_match import closeness, select_name_slot  # noqa: E402
from vidgen.infrastructure.local_ai.loaders import load_whisper  # noqa: E402
from vidgen.infrastructure.local_ai.stt import FasterWhisperSpeechToText  # noqa: E402

Loader = Callable[[Path], Any]
EXIT_BAD_INPUT = 2
SIZE_ORDER = ("tiny", "base", "small", "medium", "large")
DEFAULT_CONFIDENCE = 0.6
DEFAULT_CLOSENESS = 0.8
BYTES_PER_MB = 1024 * 1024
HEADER = f"{'size':<10}{'audio':<24}{'found':<7}{'closeness':<11}{'seconds':<9}{'memory_mb':<11}heard"


def _size_folders(root: Path) -> list[Path]:
    """Size sub-folders, in model order (unknown names last, alphabetical)."""
    folders = [p for p in root.iterdir() if p.is_dir()]
    return sorted(
        folders,
        key=lambda p: (SIZE_ORDER.index(p.name) if p.name in SIZE_ORDER else len(SIZE_ORDER), p.name),
    )


def _peak_memory_mb() -> float:
    """Peak memory of this process so far (it only grows, so run small sizes first)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return (peak if sys.platform == "darwin" else peak * 1024) / BYTES_PER_MB  # Linux: KiB


def _row(size: Path, audio: Path, name: str, loader: Loader, confidence: float, near: float) -> str:
    """Transcribe one audio file with one model size and format the result row."""
    stt = FasterWhisperSpeechToText(size, loader=loader)
    started = time.perf_counter()
    words = stt.transcribe(audio, hint=name)
    seconds = time.perf_counter() - started
    stt.release()
    match = select_name_slot(
        words, name, confidence_threshold=confidence, closeness_threshold=near
    )
    best = max((closeness(name, w.text) for w in words), default=0.0)
    heard = [match.found.text] if match.found else [c.word.text for c in match.candidates]
    found = "yes" if match.found else "no"
    return (
        f"{size.name:<10}{audio.name:<24}{found:<7}{best:<11.2f}{seconds:<9.1f}"
        f"{_peak_memory_mb():<11.0f}{', '.join(heard)}"
    )


def main(argv: Sequence[str] | None = None, *, loader: Loader = load_whisper) -> int:
    """Run the comparison; return the exit code."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    parser.add_argument("--weights-root", type=Path, required=True)
    parser.add_argument("--name", required=True, help="the name as typed in the template")
    parser.add_argument("--audio", type=Path, action="append", required=True)
    parser.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE)
    parser.add_argument("--closeness", type=float, default=DEFAULT_CLOSENESS)
    args = parser.parse_args(argv)
    if not args.weights_root.is_dir():
        print(f"weights folder not found: {args.weights_root}", file=sys.stderr)
        return EXIT_BAD_INPUT
    missing = [a for a in args.audio if not a.is_file()]
    if missing:
        print(f"audio file not found: {missing[0]}", file=sys.stderr)
        return EXIT_BAD_INPUT
    sizes = _size_folders(args.weights_root)
    if not sizes:
        print(f"no size sub-folders in: {args.weights_root}", file=sys.stderr)
        return EXIT_BAD_INPUT
    print(HEADER)
    for size in sizes:
        for audio in args.audio:
            print(_row(size, audio, args.name, loader, args.confidence, args.closeness))
    return 0


if __name__ == "__main__":
    sys.exit(main())
