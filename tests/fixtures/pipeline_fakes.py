"""Fakes for the per-row render pipeline ports (ADR-008). They record calls and can fail."""

from __future__ import annotations

import array
import io
import shutil
import threading
import time
import wave
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from vidgen.domain.timing import TimingPlan

SAMPLE_RATE = 16000


def _next_error(queue: list[BaseException | None]) -> BaseException | None:
    """Pop the next scripted outcome: an exception to raise, or None for success."""
    return queue.pop(0) if queue else None


@dataclass
class EncoderCall:
    """What the video engine was asked to do."""

    template_existed: bool
    template_bytes: bytes
    audio_existed: bool
    label_existed: bool
    slot: tuple[float, float]
    plan: TimingPlan
    metadata: dict[str, str]


class FakeEncoder:
    """VideoEncoder double: writes b'ENC' to ``out``; failures and delays are scripted."""

    def __init__(self, calls: list[str] | None = None) -> None:
        self.calls: list[EncoderCall] = []
        self.errors: list[BaseException | None] = []
        self.delay_s = 0.0
        self.on_render: Callable[[], None] | None = None
        self.order = calls if calls is not None else []
        self._lock = threading.Lock()

    def render(
        self,
        template: Path,
        new_slot_audio: Path,
        slot: tuple[float, float],
        plan: TimingPlan,
        label_png: Path,
        metadata: Mapping[str, str],
        out: Path,
    ) -> None:
        """Record the call, maybe fail, otherwise write the output."""
        with self._lock:
            self.order.append("encode")
            self.calls.append(
                EncoderCall(
                    template.exists(),
                    template.read_bytes() if template.exists() else b"",
                    new_slot_audio.exists(),
                    label_png.exists(),
                    slot,
                    plan,
                    dict(metadata),
                )
            )
            error = _next_error(self.errors)
        if self.on_render is not None:
            self.on_render()
        if self.delay_s:
            time.sleep(self.delay_s)
        if error is not None:
            raise error
        out.write_bytes(b"ENC")


class FakeVoice:
    """VoiceCloner double: writes a real WAV of a chosen length and loudness."""

    def __init__(self, calls: list[str] | None = None) -> None:
        self.texts: list[str] = []
        self.sample_existed: list[bool] = []
        self.errors: list[BaseException | None] = []
        self.seconds = 0.6
        self.reported: float | None = None  # override the returned duration
        self.amplitude = 0.3
        self.order = calls if calls is not None else []

    def synthesize(self, text: str, voice_sample: Path, out: Path) -> float:
        """Write speech for ``text`` and return its duration."""
        self.order.append("tts")
        self.texts.append(text)
        self.sample_existed.append(voice_sample.exists())
        error = _next_error(self.errors)
        if error is not None:
            raise error
        count = int(self.seconds * SAMPLE_RATE)
        level = int(self.amplitude * 32767)
        samples = array.array("h", [level if (i // 20) % 2 else -level for i in range(count)])
        with wave.open(str(out), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(SAMPLE_RATE)
            handle.writeframes(samples.tobytes())
        return self.seconds if self.reported is None else self.reported


class FakeLipSync:
    """LipSyncer double: passes the video through (plus an optional marker) unless it fails."""

    def __init__(self, calls: list[str] | None = None) -> None:
        self.errors: list[BaseException | None] = []
        self.count = 0
        self.marker = b""  # appended to the output so tests can see the chain
        self.video_bytes: list[bytes] = []
        self.audio_existed: list[bool] = []
        self.start_s: list[float] = []  # the start_s each call received (DD-39 part B)
        self.order = calls if calls is not None else []

    def sync(self, video: Path, audio: Path, out: Path, start_s: float = 0.0) -> None:
        """Pass the video through; record the start."""
        self.order.append("lipsync")
        self.count += 1
        self.start_s.append(start_s)
        self.video_bytes.append(video.read_bytes())
        self.audio_existed.append(audio.exists())
        error = _next_error(self.errors)
        if error is not None:
            raise error
        shutil.copyfile(video, out)
        if self.marker:
            with out.open("ab") as handle:
                handle.write(self.marker)


class FakeQuality:
    """QualityChecker double returning scripted failure codes."""

    def __init__(self, calls: list[str] | None = None) -> None:
        self.result: list[str] = []
        self.count = 0
        self.order = calls if calls is not None else []

    def check(self, template: Path, output: Path) -> list[str]:
        """Return the configured failure codes (empty = pass)."""
        self.order.append("check")
        self.count += 1
        return list(self.result)


class FakeLabels:
    """LabelRenderer double: writes a tiny opaque PNG and remembers the requested sizes."""

    def __init__(self) -> None:
        self.sizes: list[tuple[int, int]] = []

    def render_label(self, width: int, height: int, out: Path) -> None:
        """Write a dark PNG of the requested size."""
        self.sizes.append((width, height))
        buffer = io.BytesIO()
        Image.new("RGB", (width, height), (20, 20, 40)).save(buffer, "PNG")
        out.write_bytes(buffer.getvalue())


@dataclass
class PreviewEvents:
    """PreviewSink double: what the worker reported about previews."""

    rendered: list[tuple[object, str]] = field(default_factory=list)
    failed: list[tuple[object, object]] = field(default_factory=list)

    def preview_rendered(self, batch_id: object, key: str) -> None:
        """Record a finished preview."""
        self.rendered.append((batch_id, key))

    def preview_failed(self, batch_id: object, code: object) -> None:
        """Record a failed preview."""
        self.failed.append((batch_id, code))
