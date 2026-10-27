# M2 Mac feasibility spike — results (2026-10-27)

Machine: Apple M4 Pro, 24 GB, torch 2.14.1 (MPS) in `.venv-m2`. Throwaway code. The real-sample run (S6) used the
template video and rows 1–3 of the sheet, locally only; no sample-derived file, name, ID or transcript is committed.

## Per step

| # | Component | Device | Works | Time | Peak memory | Notes |
|---|-----------|--------|-------|------|-------------|-------|
| S1 | faster-whisper `small`, int8 | CPU | ✅ | 1.7 s for 3.6 s audio; 26 s for the 26 s template (RTF ~1.0) | 1.0–1.7 GB RSS | Word times found for "Krishan" (synthetic and real). On the real template `small` spells it "किर्संजी" and mangles other words: use a larger model (untested here) |
| S2 | IndicXlit | CPU | ❌ | n/a | n/a | `ai4bharat-transliteration` pulls fairseq 0.12.2, which fails on Python 3.11 (`mutable default ... CommonConfig`). It also needs urduhack/tensorflow-addons (broken with current keras; stubbed, 2nd attempt). Needs its own Python 3.9/3.10 env or a fork. Hand-written Devanagari was used for the 3 first names |
| S3 | Chatterbox-Multilingual (Hindi, cloned) | MPS | ✅ | RTF 0.9–1.2 (4.4 s for 5 s audio, warm); model load ~10 s; real name clip 8–15 s per row | 4.6 GB RSS, 3.7 GB MPS | Round-trip through Whisper recovers the text. Needed `setuptools<81` (perth) and `soundfile` instead of torchaudio.save |
| S4 | Demucs htdemucs | MPS | ✅ | 0.23 s for 3.7 s (RTF 0.06); 1.3 s for the 26 s template | ~1 GB RSS | Synthetic tone bed is an easy case. Real template split was used in S6 |
| S5 | MuseTalk v1.5 | MPS (UNet/VAE), CPU (landmarks, face parsing) | ✅ with patches | 432 s for 124 output frames (5 s video): ~240 s landmarks on CPU, 22 s UNet, 9 s blend, rest model load | 15.6 GB footprint | DWPose needs mmcv compiled ops, not available: replaced by `face-alignment` (FAN) 68 landmarks. Resnet18 init skipped (its weights are overwritten by `79999_iter.pth`) |
| S6 | Full real pipeline, 3 videos | mixed | ✅ | 158–189 s per video (see below) | 16–18 GB footprint (MuseTalk) | Output 1080x1300, 60 fps, same duration as the template (26.2 s) |

S6 per video: TTS 8–15 s, MuseTalk slot (1.6 s, 40 frames at 25 fps) 138–175 s, FFmpeg assemble ~5 s. In MuseTalk, most time
is CPU landmark extraction (~1.1 s per frame) plus model load, not the UNet.

Pipeline as run: Whisper finds the name word (0–1.0 s of the template, "<name> ji") → hand-mapped Devanagari → Chatterbox clones the
voice from a 10 s Demucs vocal-stem excerpt of the template → name clip fitted into the 1.0 s window (silence trim, time-stretch up to 1.6x)
and spliced into the vocal stem only (15 ms cross-fade) → remixed with the template's accompaniment stem → MuseTalk on the first 1.6 s
at 25 fps → upsampled to 60 fps and spliced back → AI label band added with the repo's `PillowLabelRenderer`
(10 % of frame height, from `backend/vidgen`) → AAC audio.

## Quality notes (honest)
- Automatic checks only: the new audio, re-transcribed by Whisper, contains the new name followed by "जी" and the original
  "राम राम" at the original time; frame size, fps and duration match the template; the label band is present. I could not listen
  or watch the clips, and one still-frame sheet is not a lip-sync judgement. **A human must review the 3 videos** for voice match,
  sync, seams and music continuity.
- Known weak spots from the design, not yet judged by eye: (1) the lip-synced slot is 25 fps duplicated to 60 fps, so motion in the
  first 1.6 s may judder against the rest; (2) the new name is shorter than the original "Krishan ji", leaving a short silence before
  "राम राम" (name ends ~0.45 s, next word at 1.0 s); (3) the MuseTalk face crop can differ in colour from the original at the seam;
  (4) the Demucs "rest" stem carries any residual of the old name and some artefacts on real music.
- Transliteration is unresolved (S2), and names were mapped by hand; ADR-010's per-row "Spoken name" override stays essential.

## S2b — Roman to Devanagari name transliteration without fairseq (2026-10-27)
Self-written set of 40 Indian first+last names (none from `samples/`), strict scoring: "exact" = the primary spelling, "ok" = primary or a
listed same-pronunciation variant. Several misses are probably still pronounceable (strict list), so treat "ok" as a floor.
Script: `s2b_translit_llm.py`. Deterministic decoding, 5 few-shot examples, bf16 on MPS.

| Model | Licence (HF field) | Exact | Ok | s/name | Load | Peak RSS |
|-------|--------------------|-------|----|--------|------|----------|
| indic-transliteration (rule-based baseline) | MIT | 0 % | 0 % | <0.01 | 0.1 s | ~0 |
| Qwen2.5-1.5B-Instruct | Apache-2.0 | 22 % | 30 % | 0.27 | 240 s (mostly first download) | 2.2 GB |
| **Qwen3-4B-Instruct-2507** | Apache-2.0 | **45 %** | **55 %** | 0.69 | 613 s (mostly first download) | 2.8 GB |
| Qwen2.5-7B-Instruct | Apache-2.0 | not run | not run | n/a | n/a | n/a |

- 7B: ❌ the download stalled at 0 bytes for 40 min (over the 20-min rule); not retried. Qwen2.5-3B skipped: licence is `other` (Qwen research, non-commercial).
- Skipped for licence or provenance: `psidharth567/indic-xlit-*` and `kishankumar007/mt5-multilingual-aksharantar` (no licence field), other community
  byT5/IndicXlit re-uploads (unknown author or licence, or other languages). The official `ai4bharat/IndicXlit` is MIT but fairseq-only.
- Typical errors: wrong long vowels (सुनिल vs सुनील), Hinglish spelling of "sh" (रमेस्ह), stray Latin letters, a wrong word (रक्षे जयंत for "Rakesh Jain").
  The 1.5B model is not usable; the 4B model is plausible but wrong on about 45 % of names.
- Memory is under 3 GB and about 0.7 s per name, negligible per video.
- **Recommendation:** use Qwen3-4B-Instruct-2507 (Apache-2.0) only to PRE-FILL a "Spoken name" column, and keep the per-row override plus a
  preview step mandatory (as ADR-010 already requires). Expect roughly half of names to need a human fix, similar to IndicXlit's 59 % top-1.
  Untried upgrades: a larger model (7B needs a download retry), more few-shot examples, a dictionary of common Indian names checked before the LLM.
  Rule-based transliteration is not viable (0 %).

## Estimates on this Mac (one video at a time; 16–18 GB footprint rules out running two MuseTalk jobs in parallel)
- As measured (~160 s per video): **100 videos ≈ 4.5 h, 1,000 videos ≈ 44 h**.
- With obvious fixes (landmarks computed once per template slot and reused through `--use_saved_coord`, models kept loaded in a worker),
  an unmeasured guess of ~50 s per video: **100 ≈ 1.5 h, 1,000 ≈ 14 h**. Longer name slots or full-video lip sync cost much more.

## Licences (checked against ADR-010 and the repos; the spike used only these)
faster-whisper MIT, Whisper weights MIT; Chatterbox MIT code and weights; Demucs MIT; MuseTalk MIT, sd-vae-ft-mse MIT,
whisper-tiny MIT; DWPose weights (yzd-v/DWPose) Apache-2.0, downloaded but unused after the landmark swap; `face-alignment` BSD-3
(code; S3FD/FAN weights come from the author's site, **licence to verify in G1**); face-parse-bisent weights (Google Drive, per the
MuseTalk README) **licence to verify in G1**. Nothing non-commercial was installed. Skipped: F5/Dhee, XTTS (NC).

## Recommendation
**Mac is enough for developing M2 and for small runs (tens of videos); rent a GPU for production volumes.** Every model loads
and the pipeline works end to end locally, but 1,000 videos is 14–44 h here against a few hours on a rented CUDA GPU, where DWPose and
S3FD also run natively. Before choosing, a human must judge the 3 output videos; if quality is good, spend GPU money only for batch runs.

## Reproduce
Scripts in this folder: `s1_whisper.py`, `s2_indicxlit.py`, `s3_chatterbox.py`, `s4_demucs.py`, `s5_download_weights.py`, `s6_real.py`.
MuseTalk was cloned into `work/musetalk` and patched locally (device, landmark source, resnet init); those patches are not committed.
Venv extras: `numpy==1.26.4`, `setuptools<81`, `openpyxl`, `face-alignment`, `mmpose`-family (unused in the end).
