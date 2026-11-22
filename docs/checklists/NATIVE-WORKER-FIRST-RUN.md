# Checklist: first real run of local AI with the Docker app and a native worker

For the Admin, on the Mac (Apple silicon). Nothing here costs money or touches the cloud. Use **made-up demo data only**
(the neutral demo template and the 4 made-up names). Not run by me; the first real run is yours.

## Before you start
- [ ] About **20 to 21 GB of RAM** is needed by the worker alone (measured on the M4 Pro, 24 GB); the Mac will swap. Quit
      browsers with many tabs, video apps and other heavy apps. 32 GB is recommended.
- [ ] Docker Desktop: keep its memory limit small (Settings, Resources, for example 4 GB). The AI models run outside Docker,
      so Docker does not need much.
- [ ] Stop the hand-started dev stack if it runs: `scripts/dev_down.sh`. It and the Docker app use the same ports (8000, 5173).
- [ ] The weights are in `backend/spikes/m2_mac/work/local_ai_weights` (default) with whisper, qwen, chatterbox, musetalk.
- [ ] The database is at migration 0003 (`vidgen` is). If you prefer a separate demo database, `vidgen_demo` first needs 0003
      (back up, then apply: see `docs/plans/CURRENT-PLAN.md`, section 5). Otherwise the first run adds one demo batch to `vidgen`.

## Steps
1. [ ] `docker compose up -d` (PostgreSQL and Redis).
2. [ ] `python3 scripts/setup.py` and answer **local** (it keeps your existing keys; answer `n` to overwriting if `.env` is fine).
      Check `.env` has `VIDGEN_AI_MODE=local` and `VIDGEN_DOCKER_WORKERS=0` (no worker container).
3. [ ] `docker compose --profile app up -d` (API and dashboard in containers; no worker container).
4. [ ] Preview the native worker settings (changes nothing, secrets hidden):
      `python3 scripts/setup.py native-worker --print`. It must show `VIDGEN_AI_MODE=local`, `127.0.0.1` for the database and
      Redis, your media folder as an absolute path, and `***` for the password.
5. [ ] In a **second terminal**, start the worker (it stays in the foreground, Ctrl+C stops it):
      `python3 scripts/setup.py native-worker`.
      It first installs `chatterbox-tts==0.1.7` without its stale pins, then starts `python -m vidgen.worker`. Wait for the line
      "local AI mode: development use only until licences are verified" and for the models to load on the first job.
6. [ ] Open http://localhost:5173, sign in, upload the **neutral demo template** (`backend/spikes/m2_mac/work/neutral_demo/demo_template.mp4`),
      type the name `Rahul`, analyse. Expect the slot to be found (name detection by sound); confirm it.
7. [ ] Upload `names_marketing.csv` (4 made-up rows), map the columns, press **Generate preview**. The first preview after a
      start is slow (models load and the GPU compiles). Watch the progress steps.
8. [ ] Confirm the spoken spelling, approve the preview, start the batch, wait for the 4 videos.

## What to check and write down
- [ ] Time of the first preview, of a warm preview, and per row. Peak memory (Activity Monitor "Memory", or `top -stats mem`) and swap used.
- [ ] Output quality: voice says the new name, lips match, beard and face unchanged, no seam, music, AI label in the corner.
- [ ] Did anything fail? Worker log is in the second terminal; API log: `docker compose logs api`.
- [ ] The queue after a restart: stop the worker with Ctrl+C mid-batch, start it again; the stuck rows should be picked up again within about 5 minutes.

## Stop and clean up
- Ctrl+C in the worker terminal, then `docker compose --profile app down` (your data stays in the Docker volumes and `./media`).
- To go back to the hand-started dev stack: `scripts/dev_up.sh`.

## If something goes wrong
- "Settings file not found" or "only for AI mode local": run `python3 scripts/setup.py` and choose local.
- Port already in use: step "Stop the hand-started dev stack" was skipped.
- The dashboard shows "The database needs migration ...": the database is behind; apply the migration (yours to run) and reload.
- Out of memory or very slow: close other apps; try one row at a time.
Send me the numbers and any error text and I will record them in the plan.
