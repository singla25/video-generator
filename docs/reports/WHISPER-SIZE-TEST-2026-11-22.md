# Whisper model size test (first result, 2026-11-22)

Run during the overnight run (DD-41, DD-42). Offline, on this Mac's CPU, with the Whisper weights the Admin approved
(small and medium, public `Systran/faster-whisper-*`, stored in the git-ignored work folder; large-v3 was not downloaded).
Data: the made-up **neutral demo template** (`neutral_demo/demo_template.mp4`, 10.5 s), no voter data. The spoken
name in the video is राहुल; the typed name was `Rahul`. Script: `backend/scripts/whisper_size_test.py`.

| Size | Name found | Closeness | Seconds (load + run) | Peak memory | What Whisper wrote |
|------|-----------|-----------|----------------------|-------------|--------------------|
| small | yes | 1.00 | 8.9 | 1368 MB | रहुल |
| medium | yes | 1.00 | 10.8 | 2317 MB | राहुल |

## What it says
- Both sizes find the name. Small wrote the word slightly wrong, but the new sound-based matching still accepted it.
  Medium wrote it correctly.
- Small is about 1 GB lighter and a little faster.
- This is **one demo clip**. It does not prove small is enough for real templates. No default was changed. To decide, run
  the script on more demo templates (different voices, noise, names), then choose.

## How to repeat
`backend/scripts/whisper_size_test.py --weights-root <folder with small/ and medium/ subfolders> --name Rahul --audio <16 kHz mono wav>`
