"""Spike (DD-39): a synthetic marketing template with the name spoken in the middle of a sentence.

Usage (one process at a time: a lip sync peaks at 16-18 GB of the 24 GB; do not start the app):

    PYTHONPATH=backend .venv-m2/bin/python backend/spikes/m2_mac/make_marketing_template.py

Steps: macOS ``say`` (Lekha) makes the Hindi audio; the app's MuseTalk adapter lip syncs a stock
face clip to the whole audio; FFmpeg composes a 1080x1300 template with a Pillow headline; the
app's Whisper adapter transcribes the final audio to find the name span. If Whisper misspells the
name, the span is timed from the separately synthesized parts instead. Everything is synthetic:
no sample data is read. Outputs go to the git-ignored work folder. Pilot weights, this Mac only
(DD-31): nothing leaves the machine.
"""

from __future__ import annotations

import csv
import itertools
import json
import math
import string
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageDraw, ImageFont, features

if TYPE_CHECKING:
    from vidgen.domain.values import Word

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "backend" / "spikes" / "m2_mac" / "work"
MARKETING = WORK / "marketing_demo"
TMP = MARKETING / "_tmp"
FACE_CLIP = WORK / "musetalk" / "data" / "video" / "sun.mp4"
FONT = ROOT / "backend" / "vidgen" / "assets" / "fonts" / "NotoSansDevanagari-Bold.ttf"
sys.path.insert(0, str(ROOT / "backend" / "scripts"))
import local_ai_smoke as smoke  # noqa: E402

# The script is built from parts so the fallback can time each one; SCRIPT_TEXT is their join.
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
BUBBLE_CORNER_PX = 150  # the AI label bubble (bottom-right) stays free of text
SHEET = (
    ("Rahul Verma", "MKT0001"),
    ("Priya Sharma", "MKT0002"),
    ("Gurpreet Singh", "MKT0003"),
    ("Amit Yadav", "MKT0004"),
    ("Sunita Devi", "MKT0005"),
    ("Mohit Bajaj", "MKT0006"),
)
PUNCTUATION = string.punctuation + "।॥"


def _run(*command: str) -> str:
    """Run a tool and return its stdout; on failure stop with the tool's own error line."""
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        raise SystemExit(f"{command[0]} failed: {result.stderr.strip()[-300:]}")
    return result.stdout


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


def name_span_from_words(words: Sequence[Word]) -> tuple[float, float] | None:
    """Start of the first name word to the end of the last, or None if Whisper misspells it."""
    first, last = normal(FIRST_NAME), normal(LAST_NAME)
    for this, following in itertools.pairwise(words):
        if normal(this.text) == first and normal(following.text) == last:
            return this.start_s, following.end_s
    return None


def name_span_from_parts(tmp: Path) -> tuple[float, float, dict[str, float]]:
    """Span of the name from the synthesized parts: the lead-in lengths, then the name's length."""
    names = ("before", "lead", "name", "after")
    lengths = {
        label: _say(text, tmp / f"part_{label}.wav")
        for label, text in zip(names, SCRIPT_PARTS, strict=True)
    }
    start = lengths["before"] + lengths["lead"]
    return start, start + lengths["name"], lengths


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


def write_readme(out: Path, facts: dict[str, Any]) -> None:
    """Plain-text notes for the Admin: the script, the clip used and the slot to enter."""
    text = (
        "Synthetic marketing template (DD-39). Spike output, not campaign data.\n\n"
        f"Script text (Hindi, macOS Lekha voice):\n{SCRIPT_TEXT}\n\n"
        f"Video: marketing_template.mp4, {facts['length']:.1f} s, 1080x1300, 60 fps, H.264 + AAC.\n"
        "Headline (top banner, whole video): सिंगला टीवीएस / बजाज बाइक्स\n"
        f"Face clip: {FACE_CLIP.name} (front-facing stock clip from the MuseTalk test set), "
        "lip synced to the whole script.\n\n"
        "Enter in the template form:\n"
        f"  Word to replace: {WORD_TO_REPLACE}\n"
        f"  Slot start (s): {facts['start']:.1f}\n"
        f"  Slot end (s): {facts['end']:.1f}\n\n"
        f"Slot method: {facts['method']}.\n"
        "Sheet: names_marketing.csv (6 synthetic rows, MKT0001 to MKT0006).\n"
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


def main() -> int:
    """Build the template and its outputs; returns the process exit code."""
    smoke._prepare_environment()
    from vidgen.infrastructure.local_ai.factory import build_ai_adapters
    from vidgen.settings import Settings

    settings = Settings()  # type: ignore[call-arg]  # secrets come from the placeholder env
    adapters: Any = build_ai_adapters(settings)
    MARKETING.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    timer = smoke.Timer()

    started = time.perf_counter()
    speech = TMP / "speech.wav"
    length = _say(SCRIPT_TEXT, speech)
    timer.stage("say", started)
    print(f"speech {length:.2f}s (Lekha, {VOICE})")

    face = TMP / "face_trimmed.mp4"
    trim_face(length, face)
    synced = TMP / "face_synced.mp4"
    started = time.perf_counter()
    adapters.lipsync.sync(face, speech, synced)  # the adapter output carries no audio
    adapters.lipsync.release()
    timer.stage("lipsync", started)

    background = TMP / "background.png"
    draw_background(background)
    template = MARKETING / "marketing_template.mp4"
    template.unlink(missing_ok=True)
    compose(background, synced, speech, length, template)
    timer.stage("compose", started)

    final_audio = TMP / "template_16k.wav"
    _run("ffmpeg", "-v", "error", "-y", "-i", str(template), "-vn", "-ac", "1", "-ar",
         str(SAMPLE_RATE), str(final_audio))  # fmt: skip
    started = time.perf_counter()
    words: list[Word] = adapters.stt.transcribe(final_audio)
    adapters.stt.release()
    timer.stage("stt", started)
    print("transcript (app Whisper, word times):")
    _report_transcript(words)

    span = name_span_from_words(words)
    parts_start, parts_end, lengths = name_span_from_parts(TMP)
    print(f"parts timing: {', '.join(f'{k} {v:.2f}s' for k, v in lengths.items())}")
    print(f"parts-based name span {parts_start:.2f}-{parts_end:.2f}s")
    if span is None:
        method = "timed from the separately synthesized Lekha parts (transcript misspelt the name)"
        start, end = parts_start, parts_end
    else:
        method = "app Whisper word timestamps (first word start to last word end)"
        start, end = span
    print(f"name span {start:.2f}-{end:.2f}s, method: {method}")
    _check_middle_third(start, end, length)
    facts = {
        "length": length,
        "start": math.floor(start * 10) / 10,  # rounded outwards so the slot covers both words
        "end": math.ceil(end * 10) / 10,
        "method": method,
    }
    extract_frame(template, (start + end) / 2, MARKETING / "frame_name.png")
    extract_frame(template, 0.5, MARKETING / "frame_start.png")
    write_sheet(MARKETING / "names_marketing.csv")
    write_readme(MARKETING / "README.txt", facts)

    info = describe(template)
    print(f"template: {info}")
    if (info["width"], info["height"]) != (CANVAS_W, CANVAS_H) or info["audio"] == "none":
        raise SystemExit("the template does not match the required format")
    print(f"peak RSS {smoke._peak_rss_gb():.1f} GB; MPS {smoke._mps_gb():.1f} GB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
