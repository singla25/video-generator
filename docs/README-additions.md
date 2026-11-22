# README additions (to paste into README.md)

The guard did not let an agent edit `README.md` during the overnight run, so the new text is here. Paste each part where
it says. Every statement below is true of the code on `integration/overnight`; nothing here was run live.

## 1. "Choose your mode" table: replace the `modal` row with

| `modal` | On Modal cloud GPUs. **Demo and learning data only, never real voter data** | A Modal account with credit and a token pair | **Code ready, not deployed, not tried live.** The speech-to-text and voice-cloning code and the Modal app (`backend/modal_app/app.py`) are written and tested offline against a fake. Lip sync on Modal is **not available yet** (licence decision pending). See [ADR-013](docs/decisions/ADR-013-cloud-gpu-modal.md) |

## 2. New subsection after "Choose your mode": "Where to render"

When you approve a preview, the dashboard asks **where to render**: on this computer, or on a cloud provider when one is
set up. A provider that is for demo data only is not offered for a batch that holds real data. Each cloud provider has a
**spend cap**; when it is reached the batch pauses.

The cap is a soft limit. With N rows rendering at once it can be passed by up to N-1 rows' cost. The cloud provider's own
workspace limit is the hard stop, so always set one there too.

## 3. New subsection under "Usage": "Finding the name in the template"

Type the name as it is spoken in the template, in Roman letters (for example `Rahul`). The app listens to the template and
matches by **sound**, so `Rahul` and the Devanagari word `राहुल` count as the same name. If no word is close
enough, the dashboard shows up to **3 closest words** with their time and how close they are; press **Use this word** to
mark the slot. You always confirm the slot yourself.

- Setting: `VIDGEN_NAME_MATCH_THRESHOLD` (default `0.8`, from 0 to 1). Lower finds more but guesses more.
- To compare Whisper sizes on your own demo templates (offline, no downloads), run
  `backend/scripts/whisper_size_test.py --weights-root <folder with small/ and medium/ subfolders> --name Rahul --audio <16 kHz mono wav>`.
  First result: [docs/reports/WHISPER-SIZE-TEST-2026-11-22.md](docs/reports/WHISPER-SIZE-TEST-2026-11-22.md). It is one demo clip, so no default was changed.

## 4. New bullet in "Troubleshooting"

**The dashboard shows "The database needs migration ..."** The database is behind the code. Most pages answer 503 until the
admin applies the migration. The app never applies migrations by itself: run the guided start (it asks y/N) or the
migration command, then reload. The page recovers within a few seconds.

## 5. Local mode with the Docker app (already in README)

The README already names `python3 scripts/setup.py native-worker`. Keep the honest status: only static and configuration
checks were run; the first real run on a Mac (about 20 GB of RAM) is still to be done.

## 6. Optional setting to mention

`VIDGEN_WARM_UP_ON_START` (default off) loads each AI model once at worker start, one at a time, so a missing weight shows
immediately. It does not keep models in memory.
