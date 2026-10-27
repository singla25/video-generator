"""S6: real-sample end-to-end personalisation, local Mac only.

Usage: s6_real.py <template.mp4> <sheet.xlsx> <out_dir> <musetalk_dir> <name_map.json> <rows>

name_map.json maps a first name to its Devanagari spelling (IndicXlit is unavailable on
this Mac, see RESULTS.md). It lives in the git-ignored out_dir, so no sheet content is
committed. Only timings are printed; names and IDs are never logged.
"""

import json
import os
import re
import resource
import subprocess
import sys
import time
from pathlib import Path

import librosa
import numpy as np
import openpyxl
import soundfile as sf
import torch
from demucs.apply import apply_model
from demucs.pretrained import get_model

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))  # backend/ for the label renderer
from vidgen.infrastructure.ffmpeg.label import PillowLabelRenderer, label_band_height  # noqa: E402

SLOT_END_S = 1.0  # end of the "<name> ji" word found by faster-whisper (S1 on the template)
SLOT_VIDEO_S = 1.6  # slot plus padding for MuseTalk
OUT_FPS = 60
SRC_FPS = 25
SR = 44100
REF_WINDOW = (3.0, 13.0)
MAX_STRETCH = 1.6
XFADE_S = 0.015
FONTS = HERE.parent.parent / "vidgen" / "assets" / "fonts"


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Run a command, failing loudly."""
    return subprocess.run(cmd, check=True, **kw)


def separate_template(template: Path, out: Path, device: str) -> tuple[np.ndarray, np.ndarray]:
    """Demucs the template audio; returns (vocals, rest) as (2, n) float32 arrays."""
    wav = out / "tpl_44k.wav"
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(template), "-vn", "-ar", str(SR),
         "-ac", "2", str(wav)])
    model = get_model("htdemucs").to(device).eval()
    data, _ = sf.read(wav, dtype="float32")
    x = torch.from_numpy(data.T)
    t = time.time()
    with torch.no_grad():
        stems = apply_model(model, x[None], device=device, split=True, progress=False)[0]
    voc = stems[model.sources.index("vocals")]
    rest = stems.sum(0) - voc
    print(f"demucs template {x.shape[-1] / SR:.1f}s audio: {time.time() - t:.1f}s")
    return voc.cpu().numpy(), rest.cpu().numpy()


def fit_clip(clip: np.ndarray, sr_in: int, window_s: float) -> np.ndarray:
    """Trim silence, resample to SR and fit the clip into window_s seconds (mono)."""
    clip, _ = librosa.effects.trim(clip, top_db=35)
    clip = librosa.resample(clip, orig_sr=sr_in, target_sr=SR)
    window = int(window_s * SR)
    if len(clip) > window:
        rate = min(len(clip) / window, MAX_STRETCH)
        clip = librosa.effects.time_stretch(clip, rate=rate)[: window + int(0.1 * SR)]
    return clip


def splice_vocals(voc: np.ndarray, clip: np.ndarray) -> np.ndarray:
    """Replace [0, SLOT_END_S] of the vocal stem with clip (level-matched), cross-faded."""
    end = int(SLOT_END_S * SR)
    ref_rms = float(np.sqrt(np.mean(voc[:, :end] ** 2)) + 1e-9)
    clip = clip * (ref_rms / (float(np.sqrt(np.mean(clip**2))) + 1e-9))
    new = np.zeros_like(voc)
    n = min(len(clip), voc.shape[1])
    new[:, :n] = clip[:n]
    xf = int(XFADE_S * SR)
    ramp = np.linspace(1.0, 0.0, xf, dtype=np.float32)
    new[:, end - xf : end] = new[:, end - xf : end] * ramp + voc[:, end - xf : end] * (1 - ramp)
    new[:, end:] = voc[:, end:]
    new[:, end - xf : end] = new[:, end - xf : end]
    return new


def musetalk_slot(mt: Path, slot_mp4: Path, audio16k: Path, name: str) -> tuple[Path, dict]:
    """Run MuseTalk on the slot clip in a subprocess; returns (output, resource stats)."""
    cfg = mt / "configs" / "inference" / f"s6_{name}.yaml"
    cfg.write_text(
        f'task_0:\n video_path: "{slot_mp4}"\n audio_path: "{audio16k}"\n result_name: "{name}.mp4"\n'
    )
    env = {**os.environ, "PYTORCH_ENABLE_MPS_FALLBACK": "1", "PYTHONPATH": str(mt)}
    py = sys.executable
    t = time.time()
    log = open(mt.parent / "real" / f"mt_{name}.log", "w")
    res = subprocess.run(
        ["/usr/bin/time", "-l", py, "scripts/inference.py", "--inference_config", str(cfg),
         "--unet_config", "./models/musetalkV15/musetalk.json", "--result_dir", "./results",
         "--version", "v15", "--output_vid_name", f"{name}.mp4"],
        cwd=mt, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, check=True,
    )
    wall = time.time() - t
    log.close()
    m = re.search(r"(\d+)\s+peak memory footprint", Path(log.name).read_text())
    peak_gb = int(m.group(1)) / 2**30 if m else float("nan")
    return mt / "results" / "v15" / f"{name}.mp4", {"musetalk_s": wall, "musetalk_peak_gb": peak_gb}


def assemble(template: Path, lip25: Path, audio: Path, label_png: Path, out: Path) -> None:
    """Splice the lip-synced slot into the template, add the label and the new audio."""
    slot_frames = int(SLOT_VIDEO_S * OUT_FPS)
    fc = (
        f"[0:v]fps={OUT_FPS},setsar=1,format=yuv420p,trim=end_frame={slot_frames},"
        f"setpts=PTS-STARTPTS[a];"
        f"[1:v]scale=in_range=auto,format=yuv420p,setsar=1,setpts=PTS-STARTPTS[t0];"
        f"[t0]trim=start_frame={slot_frames},setpts=PTS-STARTPTS[b];"
        f"[a][b]concat=n=2:v=1:a=0[c];[c][2:v]overlay=0:0[v]"
    )
    # Input 0 is the slot rendered at SRC_FPS; resampled to OUT_FPS by the fps filter.
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(lip25), "-i", str(template),
         "-i", str(label_png), "-i", str(audio), "-filter_complex", fc, "-map", "[v]",
         "-map", "3:a", "-r", str(OUT_FPS), "-c:v", "libx264", "-crf", "18", "-c:a", "aac",
         "-b:a", "192k", "-movflags", "+faststart", str(out)])


def main() -> None:
    """Drive the whole spike for the first N rows of the sheet."""
    template, sheet, out_dir, mt, name_map_p, rows = sys.argv[1:7]
    template, out, mt = Path(template), Path(out_dir), Path(mt)
    name_map = json.loads(Path(name_map_p).read_text())
    ws = openpyxl.load_workbook(sheet, read_only=True).worksheets[0]
    people = [r for r in list(ws.iter_rows(values_only=True))[1 : 1 + int(rows)]]
    device = "mps"
    timings: dict[str, dict] = {}

    voc, rest = separate_template(template, out, device)
    ref = out / "ref_voice.wav"
    a, b = (int(s * SR) for s in REF_WINDOW)
    sf.write(ref, voc[:, a:b].mean(0), SR)

    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    orig_load = torch.load
    torch.load = lambda *x, **k: orig_load(*x, **{**k, "map_location": torch.device(device)})
    t = time.time()
    tts = ChatterboxMultilingualTTS.from_pretrained(device=torch.device(device))
    print(f"chatterbox load: {time.time() - t:.1f}s")

    label_png = out / "label.png"
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "json", str(template)], capture_output=True, text=True,
        check=True).stdout)["streams"][0]
    w, h = probe["width"], probe["height"]
    PillowLabelRenderer(FONTS / "NotoSansDevanagari-Bold.ttf", FONTS / "NotoSans-Bold.ttf"
                        ).render_label(w, label_band_height(h), label_png)

    for i, (name, vid) in enumerate(people, start=1):
        tm: dict = {}
        t0 = time.time()
        first = str(name).split()[0]
        deva = name_map[first]
        t = time.time()
        wav = tts.generate(f"{deva} जी", language_id="hi", audio_prompt_path=str(ref))
        tm["tts_s"] = time.time() - t
        clip = fit_clip(wav.squeeze().cpu().numpy(), tts.sr, SLOT_END_S)
        new_voc = splice_vocals(voc, clip)
        mix = np.clip(new_voc + rest, -1, 1)
        mix_wav = out / f"row{i}_mix.wav"
        sf.write(mix_wav, mix.T, SR)
        v16 = out / f"row{i}_voc16k.wav"
        sf.write(out / f"row{i}_voc44k.wav", new_voc[:, : int(SLOT_VIDEO_S * SR)].mean(0), SR)
        run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(out / f"row{i}_voc44k.wav"),
             "-ar", "16000", "-ac", "1", str(v16)])
        slot = out / "slot_25.mp4"
        if not slot.exists():
            run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(template), "-t",
                 str(SLOT_VIDEO_S), "-vf", f"fps={SRC_FPS}", "-an", "-c:v", "libx264",
                 "-crf", "10", str(slot)])
        lip, stats = musetalk_slot(mt, slot, v16, f"row{i}")
        tm.update(stats)
        t = time.time()
        assemble(template, lip, mix_wav, label_png, out / f"{vid}.mp4")
        tm["assemble_s"] = time.time() - t
        tm["total_s"] = time.time() - t0
        timings[f"row{i}"] = tm
        print(f"row{i}", {k: round(v, 1) for k, v in tm.items()})
    timings["parent_peak_rss_gb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30
    (out / "timings.json").write_text(json.dumps(timings, indent=1))


if __name__ == "__main__":
    main()
