# ADR-010 — M2 AI model stack (self-hosted, commercial-use licences)

## Status
**Proposed (provisional)**, drafted by the CEO under delegated authority on 2026-10-19. Final acceptance needs a full component-licence audit (M2 task G1) and a quality spike on a GPU, which costs money and therefore needs the Admin.

## Context
M2 replaces the M1 fakes with real models behind the existing ports. Constraints:
- **D1:** self-hosted.
- **C5:** voter data never leaves our servers.
- **REQ §7:** licences must allow commercial use.
- **D12:** Hindi.
- **Template:** 60 fps, 1080×1300.

Licences were checked on 2026-10-19 against the official repos and model cards. Sources are listed at the bottom.

## Options and findings
| Port | Candidate | Code licence | Weights licence | Hindi | Notes / verdict |
|------|-----------|--------------|-----------------|-------|-----------------|
| SpeechToText (word timestamps) | **faster-whisper** (CTranslate2 Whisper) | MIT | Whisper weights MIT | yes | `word_timestamps=True` supported. **Recommended.** |
| | WhisperX | BSD-2 | alignment/diarization models vary (some gated) | yes | Extra alignment helps, but its licence chain is heavier; fallback only |
| Transliterator | **AI4Bharat IndicXlit** | MIT (code + models) | MIT | yes (Roman → Devanagari) | Hindi named-entity Top-1 ≈ 58.9 %, so a per-row "Spoken name" override + preview stays essential. **Recommended.** |
| VoiceCloner (TTS) | **Chatterbox-Multilingual** (Resemble AI) | MIT | MIT (HF tag), Hindi finetune `Chatterbox-Multilingual-hi` | yes | Zero-shot cloning from ~10 s reference; **built-in Perth watermark** (helps C3). **Recommended.** |
| | Dhee-Indic-F5 / F5-TTS family | MIT (base code) | **CC-BY-NC-4.0** | yes | ❌ non-commercial, **excluded** |
| | XTTS-v2 | MPL | **Coqui Public Model Licence (non-commercial)** | yes | ❌ **excluded** |
| | CosyVoice2 | Apache-2.0 | Apache-2.0 | unverified | Fallback if Chatterbox Hindi quality fails |
| LipSyncer | **MuseTalk** | MIT | "available for any purpose, even commercially" | n/a | Bundles whisper-tiny, sd-vae-ft-mse, DWPose, S3FD, face-parse-bisent; **each sub-licence must be audited (G1)**. Trained at 25 fps. **Recommended (provisional).** |
| | LatentSync 1.6 (ByteDance) | Apache-2.0 | **OpenRAIL++** (use-based restrictions) | n/a | Quality-strong, 18 GB VRAM; the OpenRAIL use restrictions need legal review for election content. Fallback only |
| | Wav2Lip | — | research / non-commercial | n/a | ❌ **excluded** |
| Source separation (risk R1: music under the voice) | **Demucs htdemucs** | MIT | (not separately stated, verify) | n/a | `--two-stems=vocals`. Upstream archived Jan 2025; use the maintained fork `adefossez/demucs`. **Recommended, with a check.** |

## Decision (provisional)
faster-whisper + IndicXlit + Chatterbox-Multilingual (Hindi) + MuseTalk + Demucs, each behind its existing port. The M1 fakes stay for tests. Excluded for licence reasons: F5-TTS-derived Hindi weights, XTTS-v2 and Wav2Lip.

## Consequences / open risks
- **Frame rate:** MuseTalk and LatentSync are trained at 25 fps, and our template is 60 fps. The slot segment must be resampled to 25 fps for lip sync, then re-timed or interpolated back to 60 fps. A quality spike is needed, and Q3/Q5 (sync score, no seam) decide.
- **Watermark:** Chatterbox's Perth watermark is a bonus for C3 (invisible watermark). Keep it on.
- **Quality is unproven for this speaker and Hindi.** The GPU spike (G2) is mandatory before committing.
- **Every bundled sub-model gets a licence line in G1.** If one is non-commercial, swap it out or drop the candidate.
- GPU cost: Chatterbox + MuseTalk fit a single 24 GB GPU. Renting one costs money, so the Admin decides.

## Sources (checked 2026-10-19)
- Chatterbox: https://github.com/resemble-ai/chatterbox · https://huggingface.co/ResembleAI/chatterbox
- MuseTalk: https://github.com/TMElyralab/MuseTalk
- LatentSync: https://github.com/bytedance/LatentSync · https://huggingface.co/ByteDance/LatentSync-1.6
- faster-whisper: https://github.com/SYSTRAN/faster-whisper
- IndicXlit: https://github.com/AI4Bharat/IndicXlit
- Demucs: https://github.com/facebookresearch/demucs
- Dhee-Indic-F5 (NC licence): https://huggingface.co/dheeyantra/dhee-indic-f5
- Overview articles: https://tts.ai/blog/open-source-text-to-speech-guide-2026/ · https://www.creativeainews.com/articles/open-source-lip-sync-licenses-commercial-use-2026/
