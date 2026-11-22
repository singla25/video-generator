# Checklist: first real run of local AI on the Mac (everything native, the tested route)

For the Admin, on the Mac (Apple silicon). Nothing here costs money or touches the cloud. Use **made-up demo data only**
(the neutral demo template and the 4 made-up names). Not run by me; the first real run is yours.

## Why this route, not the Docker app
**The Docker API cannot analyse a template in local AI mode yet.** Template analysis (speech-to-text) runs inside the **API
process**. The Docker backend image is built without the `local-ai` extra, so it has no `faster-whisper`, and the weights
folder is not mounted into the container. In local mode the first "Analyse" would fail with a speech-to-text error (the API log
shows `speech-to-text failed`, error type `ModuleNotFoundError`) and the template would end with the slot not found.
So use **`scripts/dev_up.sh`**: API, worker and dashboard all run natively on the Mac; only PostgreSQL and Redis are in Docker.
This is the route the pilot and the tests used. The "Docker app plus native worker" route is **not ready**: see the end of this file.

## Before you start
- [ ] About **20 to 21 GB of RAM** is needed by the worker alone (measured on the M4 Pro, 24 GB); the Mac will swap. Quit
      browsers with many tabs, video apps and other heavy apps. 32 GB is recommended.
- [ ] Stop anything that already uses ports 8000 and 5173 (an old `dev_up.sh` run: `scripts/dev_down.sh`; the Docker app:
      `docker compose --profile app down`).
- [ ] The weights are in `backend/spikes/m2_mac/work/local_ai_weights` (the default) with whisper, qwen, chatterbox, musetalk.
      Whisper there is the small size, which is what we recommend on the Mac.
- [ ] The database is at migration 0003 (`vidgen` is). The first run adds one demo batch to `vidgen`. If you prefer a separate
      demo database, `vidgen_demo` first needs 0003 (back up, then apply: `docs/plans/CURRENT-PLAN.md`, section 5), and you start with
      `DB_NAME=vidgen_demo`.

## Steps
1. [ ] `docker compose up -d` (PostgreSQL and Redis only; no `--profile app`).
2. [ ] `VIDGEN_AI_MODE=local scripts/dev_up.sh`. It installs the `local-ai` extra and Chatterbox without its stale pins, sets the
      weights folder and one worker thread, then starts the API, the worker and the dashboard. The first run downloads
      several GB of packages. If it says migrations are pending it asks y/N: do not answer `y` unless you mean to.
3. [ ] Check the worker started in local mode: `.dev/logs/worker.log` shows "local AI mode: development use only until licences are verified".
4. [ ] Open http://localhost:5173, sign in, upload the **neutral demo template** (`backend/spikes/m2_mac/work/neutral_demo/demo_template.mp4`),
      type the name `Rahul`, analyse. Expect the slot to be found (name detection by sound); confirm it. If it is not found, the
      dashboard shows up to 3 closest words: pick one.
5. [ ] Upload `names_marketing.csv` (4 made-up rows), map the columns, press **Generate preview**. The first preview after a
      start is slow (models load and the GPU compiles). Watch the progress steps and the "first run is slow" note.
6. [ ] Confirm the spoken spelling, approve the preview, start the batch, wait for the 4 videos.

## What to check and write down
- [ ] Time of the first preview, of a warm preview, and per row. Peak memory (Activity Monitor "Memory", or `top -stats mem`) and swap used.
- [ ] Output quality: voice says the new name, lips match, beard and face unchanged, no seam, music, AI label in the corner.
- [ ] Did anything fail? Logs are in `.dev/logs/` (`api.log`, `worker.log`, `web.log`).
- [ ] The queue after a restart: run `scripts/dev_down.sh` mid-batch and start again with the same command; the stuck rows should be picked up again within about 5 minutes.

## Stop and clean up
- `scripts/dev_down.sh` stops the API, worker and dashboard (PostgreSQL and Redis keep running in Docker).
- To start again later, run step 2.

## If something goes wrong
- Port already in use: a previous run or the Docker app is still up (see "Before you start").
- The dashboard shows "The database needs migration ...": the database is behind; apply the migration (yours to run) and reload.
- Out of memory or very slow: close other apps; try one row at a time.
- Analyse says the slot was not found: check `.dev/logs/api.log` for `speech-to-text failed`; send me the error type.
Send me the numbers and any error text and I will record them in the plan.

## Not ready: the Docker app with a native worker (do not use for the first run)
`docker compose --profile app up -d` plus `python3 scripts/setup.py native-worker` starts the worker natively, but the API in the
container would still have to run template analysis, and it cannot (no `faster-whisper`, no weights). To make it work one of these
is needed, each a code or image change that needs your approval:
- **A.** Build the API image with the `local-ai` extra and mount the weights folder into it (a big image; the speech-to-text would run
  on CPU inside the container).
- **B.** Run the API natively and keep only PostgreSQL and Redis in Docker. This is what `scripts/dev_up.sh` already does; nothing to build.
- **C.** Move template analysis from the API to the worker (an architecture change).
Recommendation: **B** for now (this checklist), and decide A or C only if you need the API in Docker.
