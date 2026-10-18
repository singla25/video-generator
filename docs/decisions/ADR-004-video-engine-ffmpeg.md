# ADR-004 — Video engine: FFmpeg CLI behind the VideoEncoder port

## Status
Accepted (Admin, 2026-10-18)

## Context
M1 needs to probe uploads, splice audio with crossfades, normalise loudness, overlay the AI label, write metadata and re-encode, all while preserving resolution, fps and codecs, and without loading whole videos into memory.

## Options
| Option | Pros | Cons | Cost | Scales? |
|--------|------|------|------|---------|
| **FFmpeg CLI via subprocess** | Streams; `ffprobe`, `acrossfade`, `loudnorm`, `overlay`, metadata all built in | Needs `ffmpeg` installed; we build argument lists | Low | Yes |
| PyAV | Frame-level control | More code for simple operations | Medium | Yes |
| MoviePy | Easy API | Slow, decodes frames in Python, high memory | Low | No |

## Decision
**FFmpeg / ffprobe CLI**, called with argument lists (never `shell=True`), behind the `VideoEncoder` port. The bilingual label "AI-Generated / एआई-जनित" is rendered once per batch to a PNG with Pillow and a Devanagari font (Noto Sans Devanagari, OFL-1.1), then overlaid by FFmpeg. This avoids depending on how a given FFmpeg build shapes Devanagari text. If M2 lip sync needs frame access, PyAV is added through a new ADR.

## Consequences
- `ffmpeg` is a system prerequisite on dev machines and worker images.
- Homebrew's FFmpeg is a GPL build (x264). That's fine for internal use; check its licence before shipping the worker image to a client.
- Every FFmpeg call has a timeout, and its failures map to `RENDER_TIMEOUT` / typed errors.
