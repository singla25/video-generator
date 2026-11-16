"""Spike (DD-39): a synthetic marketing template with the name spoken in the middle of a sentence.

Usage (one process at a time: a lip sync peaks at 16-18 GB of the 24 GB; do not start the app):

    PYTHONPATH=backend .venv-m2/bin/python backend/spikes/m2_mac/make_marketing_template.py
    ... make_marketing_template.py --slot-only   (re-times the name; no say, lip sync or compose)
    ... make_marketing_template.py --two-names   (the name is said twice: a slot near the start
                                                 and one near the end; writes *_2names files)
    ... make_marketing_template.py --slot-only --two-names   (re-times the two-name template)

Steps: macOS ``say`` (Lekha) makes the Hindi audio; the app's MuseTalk adapter lip syncs a stock
face clip to the whole audio; FFmpeg composes a 1080x1300 template with a Pillow headline. The
app's Whisper adapter gives the word times of the final audio; the name slot is the speech run
that ffmpeg silencedetect finds around the name, rounded to one decimal. ``--slot-only`` re-times
the name in the existing template without re-rendering it. Everything is synthetic: no sample
data is read. Outputs go to the git-ignored work folder. Pilot weights, this Mac only (DD-31):
nothing leaves the machine.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import itertools
import json
import math
import re
import string
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageDraw, ImageFont, features

if TYPE_CHECKING:
    from vidgen.domain.values import Word

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "backend" / "spikes" / "m2_mac" / "work"
MARKETING = WORK / "marketing_demo"
TMP = MARKETING / "_tmp"
TEMPLATE = MARKETING / "marketing_template.mp4"
TEMPLATE_2NAMES = MARKETING / "marketing_template_2names.mp4"
README_2NAMES = MARKETING / "README_2names.txt"
TMP_2NAMES = TMP / "two_names"
FACE_CLIP = WORK / "musetalk" / "data" / "video" / "sun.mp4"
FONT = ROOT / "backend" / "vidgen" / "assets" / "fonts" / "NotoSansDevanagari-Bold.ttf"
sys.path.insert(0, str(ROOT / "backend" / "scripts"))
import local_ai_smoke as smoke  # noqa: E402

# The script is built from parts; SCRIPT_TEXT is their join.
BEFORE_NAME = "हाय दोस्तो, आज बजाज की नई बाइक सिंगला टीवीएस पर आ गई है।"
NAME_LEAD = "मैं"
NAME = "सलमान खान"
AFTER_NAME = (
    "आपसे कहता हूँ कि सबको इसी दुकान से बाइक और सामान लेने के लिए कहूँगा, मेरा पूरा भरोसा सिंगला टीवीएस पर है।"
)
SCRIPT_PARTS = (BEFORE_NAME, NAME_LEAD, NAME, AFTER_NAME)
SCRIPT_TEXT = " ".join(SCRIPT_PARTS)
FIRST_NAME, LAST_NAME = "सलमान", "खान"
WORD_TO_REPLACE = FIRST_NAME  # the template form replaces the first word; the slot covers both
# --two-names: the same name again at the end, in the same voice style as the rest of the script.
SECOND_NAME_SENTENCE = "आख़िर में फिर कहूँगा, मैं सलमान खान, आप सब सिंगला टीवीएस पर ज़रूर आइए।"
SCRIPT_TEXT_2NAMES = f"{SCRIPT_TEXT} {SECOND_NAME_SENTENCE}"
TWO_NAME_MIN_GAP_S = 1.0  # "well above" the app's 0.2 s minimum gap between two slots

VOICE = "Lekha"  # the Hindi voice from the earlier spikes
SAMPLE_RATE = 16000
HEADLINE = ("सिंगला टीवीएस", "बजाज बाइक्स")
HEADLINE_SIZES = (96, 60)
HEADLINE_MARGIN_PX = 60
CANVAS_W, CANVAS_H = 1080, 1300
BANNER_H = 240
FPS = 60
MUSETALK_FPS = 25  # the rate MuseTalk v1.5 works at
TAIL_S = 0.5  # the face clip runs a little past the audio so every audio frame has a face
BACKGROUND = (11, 31, 75)
BANNER = (6, 20, 50)
TEXT_COLOUR = (255, 255, 255)
ACCENT_COLOUR = (255, 196, 60)
SILENCE_NOISE_DB = -32
SILENCE_MIN_S = 0.06
SILENCE_EVENT = re.compile(r"silence_(start|end): (-?\d+(?:\.\d+)?)")
NAME_MATCH_RATIO = 0.6  # SequenceMatcher similarity for the misspelt first name (सल्मान)
WIDEN_S = 0.05  # only used for the printed comparison with the raw Whisper span
SLOT_DECIMALS = 1
SLOT_SCALE = 10**SLOT_DECIMALS
SHEET = (
    ("Rahul Verma", "MKT0001"),
    ("Priya Sharma", "MKT0002"),
    ("Gurpreet Singh", "MKT0003"),
    ("Amit Yadav", "MKT0004"),
    ("Sunita Devi", "MKT0005"),
    ("Mohit Bajaj", "MKT0006"),
)
PUNCTUATION = string.punctuation + "।॥"


@dataclass(frozen=True)
class SlotChoice:
    """The slot to enter, with the measurements it was chosen from (all in seconds)."""

    start: float
    end: float
    whisper: tuple[float, float]
    run: tuple[float, float]
    widened: tuple[float, float]


@dataclass(frozen=True)
class NameSlot:
    """One name slot of the two-name template: the rounded outward span and its sources."""

    start: float
    end: float
    whisper: tuple[float, float]
    run: tuple[float, float]


@dataclass(frozen=True)
class Variant:
    """One template to build: its script, the video it is written to and its scratch folder."""

    script: str
    template: Path
    scratch: Path


ONE_NAME = Variant(SCRIPT_TEXT, TEMPLATE, TMP)
TWO_NAMES = Variant(SCRIPT_TEXT_2NAMES, TEMPLATE_2NAMES, TMP_2NAMES)


def _execute(*command: str) -> subprocess.CompletedProcess[str]:
    """Run a tool; on failure stop with the tool's own error line."""
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        raise SystemExit(f"{command[0]} failed: {result.stderr.strip()[-300:]}")
    return result


def _run(*command: str) -> str:
    """Run a tool and return its stdout."""
    return _execute(*command).stdout


def _duration(path: Path) -> float:
    """Length of a media file in seconds."""
    return float(
        _run(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        )
    )


def _say(text: str, wav: Path) -> float:
    """Synthesize ``text`` with the Lekha voice as a 16 kHz mono wav; return its length."""
    aiff = wav.with_suffix(".aiff")
    _run("say", "-v", VOICE, "-o", str(aiff), text)
    _run(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        str(aiff),
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        str(wav),
    )
    return _duration(wav)


def trim_face(length_s: float, out: Path) -> None:
    """Loop the stock face clip if needed, cut it just past the audio, drop its audio, 25 fps."""
    _run(
        "ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", str(FACE_CLIP),
        "-t", f"{length_s + TAIL_S:.3f}", "-an", "-r", str(MUSETALK_FPS),
        "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(out),
    )  # fmt: skip


def normal(text: str) -> str:
    """Lower-case a transcript word and strip the surrounding punctuation."""
    return text.strip().strip(PUNCTUATION).casefold()


def _name_similarity(heard: str, wanted: str) -> float:
    """Similarity of a transcript word to a name, 0 to 1 (Whisper misspells Hindi names)."""
    return difflib.SequenceMatcher(None, normal(heard), normal(wanted)).ratio()


def _similar(heard: str, wanted: str) -> bool:
    """Whisper often misspells a Hindi name (सल्मान for सलमान), so compare by similarity."""
    return _name_similarity(heard, wanted) >= NAME_MATCH_RATIO


def name_span_from_words(words: Sequence[Word]) -> tuple[float, float] | None:
    """Start of the first name word to the end of the last, or None if the name is not heard.

    The surname must match exactly; the first name may be misspelt but must be similar.
    """
    for this, following in itertools.pairwise(words):
        if _similar(this.text, FIRST_NAME) and normal(following.text) == normal(LAST_NAME):
            return this.start_s, following.end_s
    return None


def silence_runs(wav: Path, length_s: float) -> list[tuple[float, float]]:
    """Speech runs (start, end) between the silences ffmpeg silencedetect reports."""
    log = _execute(
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(wav),
        "-af", f"silencedetect=noise={SILENCE_NOISE_DB}dB:d={SILENCE_MIN_S}",
        "-f", "null", "-",
    ).stderr  # fmt: skip
    events = SILENCE_EVENT.findall(log)
    starts = [float(value) for kind, value in events if kind == "start"]
    ends = [float(value) for kind, value in events if kind == "end"]
    silences = [(s, ends[i] if i < len(ends) else length_s) for i, s in enumerate(starts)]
    runs: list[tuple[float, float]] = []
    cursor = 0.0
    for silence_start, silence_end in silences:
        if silence_start > cursor:
            runs.append((cursor, silence_start))
        cursor = silence_end
    if cursor < length_s:
        runs.append((cursor, length_s))
    return runs


def choose_slot(words: Sequence[Word], runs: Sequence[tuple[float, float]]) -> SlotChoice:
    """The speech run that holds the name's Whisper span, rounded to one decimal.

    The raw span widened by 0.05 s is kept for comparison: it ends before the speech does,
    so it would cut the end of the name. The silence-bounded run is the real extent.
    """
    span = name_span_from_words(words)
    if span is None:
        raise SystemExit("the name is not in the transcript; mark the slot by hand")
    middle = (span[0] + span[1]) / 2
    run = next(((s, e) for s, e in runs if s <= middle <= e), None)
    if run is None:
        raise SystemExit("no silence-bounded speech run holds the name; mark the slot by hand")
    widened = (round(span[0] - WIDEN_S, SLOT_DECIMALS), round(span[1] + WIDEN_S, SLOT_DECIMALS))
    return SlotChoice(
        start=round(run[0], SLOT_DECIMALS),
        end=round(run[1], SLOT_DECIMALS),
        whisper=span,
        run=run,
        widened=widened,
    )


def name_candidates(words: Sequence[Word]) -> list[tuple[float, tuple[float, float]]]:
    """Every similar first name followed by the exact surname: (similarity, span), in time order."""
    found: list[tuple[float, tuple[float, float]]] = []
    for this, following in itertools.pairwise(words):
        if normal(following.text) != normal(LAST_NAME):
            continue
        ratio = _name_similarity(this.text, FIRST_NAME)
        if ratio >= NAME_MATCH_RATIO:
            found.append((ratio, (this.start_s, following.end_s)))
    return found


def best_name_spans(words: Sequence[Word], count: int) -> list[tuple[float, float]]:
    """The ``count`` best-matching name spans, in time order; fails if the name is heard less."""
    best = sorted(name_candidates(words), key=lambda candidate: candidate[0], reverse=True)[:count]
    if len(best) < count:
        raise SystemExit(
            f"the name is heard {len(best)} time(s), need {count}; mark the slots by hand"
        )
    return sorted(span for _, span in best)


def _floor_slot(value: float) -> float:
    """Round down to one decimal; the 6-digit rounding first removes float noise (50.9999999)."""
    return math.floor(round(value * SLOT_SCALE, 6)) / SLOT_SCALE


def _ceil_slot(value: float) -> float:
    """Round up to one decimal; the 6-digit rounding first removes float noise (50.0000001)."""
    return math.ceil(round(value * SLOT_SCALE, 6)) / SLOT_SCALE


def slot_for_span(
    span: tuple[float, float], runs: Sequence[tuple[float, float]], length_s: float
) -> NameSlot:
    """The silence-bounded run that holds a name span, rounded outwards to one decimal.

    Start rounds down and end rounds up, so the slot never cuts the speech. The end is capped at
    the video length (a slot may not run past the video).
    """
    middle = (span[0] + span[1]) / 2
    run = next(((s, e) for s, e in runs if s <= middle <= e), None)
    if run is None:
        raise SystemExit("no silence-bounded speech run holds a name; mark the slots by hand")
    end = min(_ceil_slot(run[1]), _floor_slot(length_s))
    return NameSlot(start=_floor_slot(run[0]), end=end, whisper=span, run=run)


def choose_two_slots(
    words: Sequence[Word], runs: Sequence[tuple[float, float]], length_s: float
) -> tuple[NameSlot, NameSlot]:
    """The two name slots of the two-name template, in time order."""
    first_span, second_span = best_name_spans(words, 2)
    if first_span[1] >= second_span[0]:
        raise SystemExit("the two name spans overlap in the transcript; mark the slots by hand")
    return (
        slot_for_span(first_span, runs, length_s),
        slot_for_span(second_span, runs, length_s),
    )


def check_two_slots(first: NameSlot, second: NameSlot, length_s: float) -> None:
    """Slot 1 must lie in the first half, slot 2 in the last third, and the gap must be clear."""
    if not (0 <= first.start < first.end <= length_s / 2):
        raise SystemExit(f"name slot 1 {first.start:.1f}-{first.end:.1f}s is not in the first half")
    if not (2 * length_s / 3 <= second.start < second.end <= length_s):
        raise SystemExit(
            f"name slot 2 {second.start:.1f}-{second.end:.1f}s is not in the last third"
        )
    gap = second.start - first.end
    if gap < TWO_NAME_MIN_GAP_S:
        raise SystemExit(f"gap {gap:.1f}s between the name slots is below {TWO_NAME_MIN_GAP_S}s")


def draw_background(out: Path) -> None:
    """Solid background with the two-line headline in the top band (bubble corner left clear)."""
    if not features.check("raqm"):
        raise SystemExit("Pillow needs raqm to shape Devanagari; the headline would be broken")
    image = Image.new("RGB", (CANVAS_W, CANVAS_H), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, CANVAS_W, BANNER_H), fill=BANNER)
    colours = (TEXT_COLOUR, ACCENT_COLOUR)
    centres = (BANNER_H * 0.36, BANNER_H * 0.76)
    for line, size, colour, centre in zip(HEADLINE, HEADLINE_SIZES, colours, centres, strict=True):
        font = ImageFont.truetype(str(FONT), size)
        if draw.textlength(line, font=font) > CANVAS_W - 2 * HEADLINE_MARGIN_PX:
            raise SystemExit(f"headline line does not fit the canvas: {line}")
        draw.text((CANVAS_W / 2, centre), line, font=font, fill=colour, anchor="mm")
    image.save(out)


def compose(background: Path, face: Path, speech: Path, length_s: float, out: Path) -> None:
    """Scale the lip-synced face under the banner, add the audio, encode 1080x1300 at 60 fps."""
    graph = (
        f"[1:v]fps={FPS},scale=-2:{CANVAS_H - BANNER_H}:flags=lanczos,format=yuv420p[face];"
        f"[0:v][face]overlay=x=(W-w)/2:y={BANNER_H},format=yuv420p[v]"
    )
    _run(
        "ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS),
        "-i", str(background), "-i", str(face), "-i", str(speech),
        "-filter_complex", graph, "-map", "[v]", "-map", "2:a",
        "-t", f"{length_s:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out),
    )  # fmt: skip


def describe(path: Path) -> dict[str, Any]:
    """Size, frame rate, codecs and length of the first video stream and the audio presence."""
    data = json.loads(
        _run(
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,pix_fmt,avg_frame_rate",
            "-of", "json", str(path),
        )
    )  # fmt: skip
    streams = data["streams"]
    video = next(s for s in streams if s["codec_type"] == "video")
    audio = [s["codec_name"] for s in streams if s["codec_type"] == "audio"]
    return {
        "width": video["width"],
        "height": video["height"],
        "fps": video["avg_frame_rate"],
        "codec": video["codec_name"],
        "pix_fmt": video["pix_fmt"],
        "audio": audio[0] if audio else "none",
        "duration_s": float(data["format"]["duration"]),
    }


def extract_frame(video: Path, second: float, out: Path) -> None:
    """One PNG frame at ``second``."""
    _run(
        "ffmpeg", "-v", "error", "-y", "-i", str(video), "-ss", f"{second:.3f}",
        "-frames:v", "1", str(out),
    )  # fmt: skip


def write_sheet(out: Path) -> None:
    """The synthetic name sheet: header ``Name,VID`` and six made-up rows."""
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["Name", "VID"])
        writer.writerows(SHEET)


def write_readme(out: Path, length_s: float, slot: SlotChoice) -> None:
    """Plain-text notes for the Admin: the script, the clip used and the slot to enter."""
    method = (
        f"ffmpeg silencedetect speech run {slot.run[0]:.3f}-{slot.run[1]:.3f} s "
        f"(noise {SILENCE_NOISE_DB} dB, {SILENCE_MIN_S} s) that holds the Whisper span of the "
        f"misspelt name ({slot.whisper[0]:.2f}-{slot.whisper[1]:.2f} s), rounded to one decimal. "
        f"Widening the Whisper span by {WIDEN_S} s each side gives "
        f"{slot.widened[0]}-{slot.widened[1]} s; the silence-bounded run is used because it "
        "matches where the speech stops."
    )
    text = (
        "Synthetic marketing template (DD-39). Spike output, not campaign data.\n\n"
        f"Script text (Hindi, macOS Lekha voice):\n{SCRIPT_TEXT}\n\n"
        f"Video: marketing_template.mp4, {length_s:.1f} s, 1080x1300, 60 fps, H.264 + AAC.\n"
        "Headline (top banner, whole video): सिंगला टीवीएस / बजाज बाइक्स\n"
        f"Face clip: {FACE_CLIP.name} (front-facing stock clip from the MuseTalk test set), "
        "lip synced to the whole script.\n\n"
        "Enter in the template form:\n"
        f"  Word to replace: {WORD_TO_REPLACE}\n"
        f"  Slot start (s): {slot.start:.1f}\n"
        f"  Slot end (s): {slot.end:.1f}\n\n"
        f"Slot method: {method}\n"
        "Sheet: names_marketing.csv (6 synthetic rows, MKT0001 to MKT0006).\n"
    )
    out.write_text(text, encoding="utf-8")


def write_readme_2names(out: Path, length_s: float, first: NameSlot, second: NameSlot) -> None:
    """Plain-text notes for the Admin on the two-name template: both slots and how to enter them."""
    method = (
        f"ffmpeg silencedetect speech runs (noise {SILENCE_NOISE_DB} dB, {SILENCE_MIN_S} s) that "
        "hold the two Whisper spans of the misspelt name. Each run is rounded outwards to one "
        "decimal (start down, end up; the end is capped at the video length). "
        f"Slot 1: Whisper {first.whisper[0]:.2f}-{first.whisper[1]:.2f} s in run "
        f"{first.run[0]:.3f}-{first.run[1]:.3f} s. "
        f"Slot 2: Whisper {second.whisper[0]:.2f}-{second.whisper[1]:.2f} s in run "
        f"{second.run[0]:.3f}-{second.run[1]:.3f} s. "
        f"Gap between the slots: {second.start - first.end:.1f} s."
    )
    text = (
        "Synthetic marketing template, name spoken twice (DD-40). Spike output, not campaign "
        "data.\n\n"
        f"Script text (Hindi, macOS Lekha voice):\n{SCRIPT_TEXT_2NAMES}\n\n"
        f"Video: marketing_template_2names.mp4, {length_s:.1f} s, 1080x1300, 60 fps, H.264 + AAC.\n"
        "Headline (top banner, whole video): सिंगला टीवीएस / बजाज बाइक्स\n"
        f"Face clip: {FACE_CLIP.name} (front-facing stock clip from the MuseTalk test set), "
        "lip synced to the whole script.\n\n"
        "Enter in the template form:\n"
        f"  Word to replace: {WORD_TO_REPLACE}\n"
        f"  Slot 1 start/end (s): {first.start:.1f} / {first.end:.1f}  (main slot)\n"
        f"  Slot 2 start/end (s): {second.start:.1f} / {second.end:.1f}  "
        "(enter with 'Add another name slot')\n\n"
        f"Slot method: {method}\n"
        "Sheet: names_marketing.csv (6 synthetic rows, MKT0001 to MKT0006), unchanged.\n"
    )
    out.write_text(text, encoding="utf-8")


def _report_transcript(words: Sequence[Word]) -> None:
    """Print every word with its times, so the Admin can check the Hindi by eye."""
    for word in words:
        print(f"  {word.text!r} {word.start_s:.2f}-{word.end_s:.2f}s conf {word.confidence:.2f}")


def _check_middle_third(start: float, end: float, length: float) -> None:
    """The name must sit in the middle third of the video, or the slot is in the wrong place."""
    if not (length / 3 <= start and end <= 2 * length / 3):
        raise SystemExit(f"name slot {start:.2f}-{end:.2f}s is outside the middle third")


def build_template(adapters: Any, timer: smoke.Timer, variant: Variant) -> float:
    """Say, lip sync and compose the template; returns the audio length in seconds."""
    started = time.perf_counter()
    speech = variant.scratch / "speech.wav"
    length = _say(variant.script, speech)
    timer.stage("say", started)
    print(f"speech {length:.2f}s (Lekha, {VOICE})")

    face = variant.scratch / "face_trimmed.mp4"
    trim_face(length, face)
    synced = variant.scratch / "face_synced.mp4"
    started = time.perf_counter()
    adapters.lipsync.sync(face, speech, synced)  # the adapter output carries no audio
    adapters.lipsync.release()
    timer.stage("lipsync", started)

    background = variant.scratch / "background.png"
    draw_background(background)
    variant.template.unlink(missing_ok=True)
    compose(background, synced, speech, length, variant.template)
    timer.stage("compose", started)
    return length


def _print_two_slots(first: NameSlot, second: NameSlot) -> None:
    """Print both name slots with their Whisper spans and silencedetect runs."""
    for number, slot in enumerate((first, second), start=1):
        print(
            f"name {number}: whisper {slot.whisper[0]:.2f}-{slot.whisper[1]:.2f}s; "
            f"silencedetect run {slot.run[0]:.3f}-{slot.run[1]:.3f}s; "
            f"CHOSEN slot {slot.start:.1f}-{slot.end:.1f}s"
        )
    print(f"gap between the slots {second.start - first.end:.1f}s")


def main() -> int:
    """Build (or re-time) the template and its outputs; returns the process exit code."""
    parser = argparse.ArgumentParser(description="Build the synthetic marketing template.")
    parser.add_argument(
        "--slot-only", action="store_true", help="re-time the name in the existing template"
    )
    parser.add_argument(
        "--two-names", action="store_true", help="say the name twice: a second slot near the end"
    )
    args = parser.parse_args()
    variant = TWO_NAMES if args.two_names else ONE_NAME
    smoke._prepare_environment()
    from vidgen.infrastructure.local_ai.factory import build_ai_adapters
    from vidgen.settings import Settings

    settings = Settings()  # type: ignore[call-arg]  # secrets come from the placeholder env
    adapters: Any = build_ai_adapters(settings)
    MARKETING.mkdir(parents=True, exist_ok=True)
    variant.scratch.mkdir(parents=True, exist_ok=True)
    timer = smoke.Timer()

    if args.slot_only:
        if not variant.template.is_file():
            raise SystemExit("no template to re-time; run without --slot-only first")
        length = _duration(variant.template)
    else:
        length = build_template(adapters, timer, variant)

    final_audio = variant.scratch / "template_16k.wav"
    _run(
        "ffmpeg", "-v", "error", "-y", "-i", str(variant.template), "-vn", "-ac", "1",
        "-ar", str(SAMPLE_RATE), str(final_audio),
    )  # fmt: skip
    started = time.perf_counter()
    words: list[Word] = adapters.stt.transcribe(final_audio)
    adapters.stt.release()
    timer.stage("stt", started)
    print("transcript (app Whisper, word times):")
    _report_transcript(words)

    runs = silence_runs(final_audio, length)
    print("silencedetect speech runs: " + ", ".join(f"{s:.3f}-{e:.3f}" for s, e in runs))
    if args.two_names:
        first, second = choose_two_slots(words, runs, length)
        _print_two_slots(first, second)
        check_two_slots(first, second, length)
        extract_frame(
            variant.template, (first.start + first.end) / 2, MARKETING / "frame_name1.png"
        )
        extract_frame(
            variant.template, (second.start + second.end) / 2, MARKETING / "frame_name2.png"
        )
        write_readme_2names(README_2NAMES, length, first, second)
    else:
        slot = choose_slot(words, runs)
        print(
            f"whisper name span {slot.whisper[0]:.2f}-{slot.whisper[1]:.2f}s; "
            f"silencedetect run {slot.run[0]:.3f}-{slot.run[1]:.3f}s; "
            f"whisper widened 0.05s {slot.widened[0]}-{slot.widened[1]}s; "
            f"CHOSEN slot {slot.start:.1f}-{slot.end:.1f}s"
        )
        _check_middle_third(slot.start, slot.end, length)

        extract_frame(TEMPLATE, (slot.start + slot.end) / 2, MARKETING / "frame_name.png")
        extract_frame(TEMPLATE, 0.5, MARKETING / "frame_start.png")
        write_sheet(MARKETING / "names_marketing.csv")
        write_readme(MARKETING / "README.txt", length, slot)

    info = describe(variant.template)
    print(f"template: {info}")
    if (info["width"], info["height"]) != (CANVAS_W, CANVAS_H) or info["audio"] == "none":
        raise SystemExit("the template does not match the required format")
    print(f"peak RSS {smoke._peak_rss_gb():.1f} GB; MPS {smoke._mps_gb():.1f} GB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
