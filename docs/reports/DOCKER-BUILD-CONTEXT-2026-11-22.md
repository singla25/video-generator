# Docker build context: 22 GB sent, 42 GB images (2026-11-22)

## What was measured
`docker compose --profile app build` transferred a **22.23 GB build context** and took about 10 minutes.

| Image | Size |
|-------|------|
| `video-generator-api:latest` | **42.3 GB** |
| `video-generator-worker:latest` | **42.3 GB** |
| `video-generator-dashboard:latest` | 77.7 MB |
| `vidgen-t3test-api:latest` / `-worker` (built by the Docker e2e test from a clean clone) | **1.24 GB** each |

The 1.24 GB test images show what the images should weigh. Layer sizes of the 42.3 GB api image (`docker history`):

| Layer | Size |
|-------|------|
| `COPY backend ./backend` | **22.2 GB** |
| `uv sync --frozen --no-dev --no-install-project` | 258 MB |
| `apt-get install ffmpeg libfribidi0 libraqm0 libharfbuzz0b` | 442 MB |
| `pip install uv` | 45.7 MB |
| everything else | under 3 MB each |

(The two 42.3 GB images share most layers, so the disk use is less than the sum.)

## Cause
`Dockerfile.backend` copies the whole `backend/` folder. `.dockerignore` does not exclude `backend/spikes/`, which holds about
**21 GB of git-ignored experiment output** on this Mac:

| Folder under `backend/spikes/m2_mac/work` | Size |
|-------------------------------------------|------|
| `hf` (Hugging Face cache) | 14 GB |
| `musetalk` | 4.1 GB |
| `whisper_sizes` (the small and medium weights downloaded for the size test) | 1.9 GB |
| `local_out` (demo outputs) | 447 MB |
| `torch` | 285 MB |
| `real` (outputs and frames from the real samples), `marketing_demo`, `neutral_demo`, wav files | about 100 MB |

Nothing in `backend/vidgen`, the Dockerfiles or `docker-compose.yml` uses `backend/spikes`.

Two smaller leaks from the same file:
- `node_modules` and `__pycache__` are listed without `**/`. Docker matches a pattern from the context root only, so
  `frontend/node_modules` (352 MB), `backend/vidgen/__pycache__` and `backend/migrations/__pycache__` are sent too.
- `*.mp4` and `*.mov` are also root-only, so a video anywhere deeper would be sent.

## Privacy note (important)
The old local images were built from a context that contained `backend/spikes/m2_mac/work/real`, which holds outputs and frames
from the **real sample**. Videos (`*.mp4`) are ignored at the root only, and other files there (jpg, wav) were not. So the
existing `video-generator-api` and `video-generator-worker` images may contain a copy of that folder. They are local only.
**Never push or share them.** After the fix is merged, rebuild and remove the old images yourself:
`docker image ls` to list, then `docker image rm <id>` for the two old ones. I did not delete anything.

## Fix (test first)
- Test: `tests/unit/meta/test_dockerignore_context.py` applies `.dockerignore` the way Docker does and checks that the spike
  folder, nested `node_modules` and `__pycache__`, model weight and media files are excluded, that everything the Dockerfiles
  copy (code, migrations, fonts, `pyproject.toml`, `uv.lock`, the dashboard sources) is still included, and that the tracked
  files that remain in the context add up to less than 20 MB, none above 5 MB.
- Change: `.dockerignore` only. Exclude `backend/spikes`, use `**/` for `node_modules`, `__pycache__`, caches, `.DS_Store`,
  and for model and media file types (`.safetensors .pt .pth .ckpt .onnx .bin .wav .mp3 .mp4 .mov`), with a comment saying why.

- Third leak found while measuring: root virtualenvs with a suffix (`.venv-m2`, 11 GB; `.venv-py314-old`) did not match the
  `.venv` line. BuildKit skips them because no `COPY` names them, but the classic builder would send them. Added `.venv*`.

## Result (measured with the test's Docker-style matcher on the real checkout, nothing built)
| Rules | Files that would be sent | Size |
|-------|--------------------------|------|
| Old `.dockerignore` | 91,352 | about 67 GB (BuildKit sent only what the COPY lines name: 22.23 GB) |
| New `.dockerignore` | **332** | **3.9 MB** (backend 2.3 MB, frontend 1.2 MB, lockfile 0.3 MB) |

Expected: a build context of a few MB and images close to the 1.24 GB of the clean-clone test images, built in about a minute
instead of ten. **Not verified by a real build**: I did not run Docker builds. Run `docker compose --profile app build` once after
merging and check the "transferring context" line and `docker images`.
