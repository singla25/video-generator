"""The per-slot passes of the row pipeline (DD-40).

A template can hold several name slots. Lip sync runs one pass per slot in ascending order: each
pass takes the previous output, and every pass after the first takes the template as the source
of its face boxes. Encode runs one pass per slot in descending order, so the earlier timestamps
still match the video they are applied to. Only the pass of the first slot gets the real label and
writes the final output; every other pass gets a transparent label.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from vidgen.domain.slot_match import Slot
from vidgen.domain.timing import TimingPlan
from vidgen.ports import LipSyncer, VideoEncoder
from vidgen.services.render_support import TRANSPARENT_PNG

NO_LABEL_NAME = "no-label.png"


def lip_sync_slots(
    lipsync: LipSyncer, template: Path, speech: Path, slots: Sequence[Slot], folder: Path
) -> Path:
    """Lip-sync the template once per slot, ascending; returns the output of the last pass.

    Pass ``i`` starts at the start of slot ``i``. The first pass reads the template and needs no
    key source; later passes read the previous output and take the template as their key source.
    With one slot the output is ``lipsync.mp4``.
    """
    current = template
    for index, slot in enumerate(slots):
        out = folder / _lip_sync_name(index, len(slots))
        key_from = None if index == 0 else template
        lipsync.sync(current, speech, out, start_s=slot[0], key_from=key_from)
        current = out
    return current


def encode_slots(
    encoder: VideoEncoder,
    lip_synced: Path,
    speech: Path,
    slots: Sequence[Slot],
    plans: Sequence[TimingPlan],
    label: Path,
    metadata: Mapping[str, str],
    folder: Path,
    output: Path,
) -> None:
    """Encode the video once per slot, last slot first; the first slot's pass writes ``output``.

    Pass ``i`` takes the result of the pass before it (the first one takes ``lip_synced``). Only
    the first slot's pass draws ``label``; the other passes draw a transparent label.
    """
    blank = _write_blank_label(folder) if len(slots) > 1 else label
    current = lip_synced
    for index in reversed(range(len(slots))):
        pass_label, out = (label, output) if index == 0 else (blank, folder / f"encode{index}.mp4")
        encoder.render(current, speech, slots[index], plans[index], pass_label, metadata, out)
        current = out


def _lip_sync_name(index: int, count: int) -> str:
    """File name of a lip sync pass; a single pass keeps the plain name."""
    return "lipsync.mp4" if count == 1 else f"lipsync{index}.mp4"


def _write_blank_label(folder: Path) -> Path:
    """Write the transparent 1x1 label into ``folder`` and return its path."""
    path = folder / NO_LABEL_NAME
    path.write_bytes(TRANSPARENT_PNG)
    return path
