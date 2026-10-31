#!/usr/bin/env bash
# Start VidGen Studio in LOCAL AI mode after you log in: wait for Docker (open it if needed),
# start postgres + redis, then run scripts/dev_up.sh with VIDGEN_AI_MODE=local.
#   --dry-run   print the steps and change nothing
# Log: .dev/autostart.log. Stop everything with scripts/dev_down.sh.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DOCKER_WAIT_SECONDS="${DOCKER_WAIT_SECONDS:-240}"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

run() {
  if [ "$DRY_RUN" = 1 ]; then echo "[dry-run] $*"; else "$@"; fi
}

cd "$ROOT" || { echo "project folder not found: $ROOT"; exit 1; }
if [ "$DRY_RUN" = 0 ]; then
  mkdir -p .dev
  exec >> .dev/autostart.log 2>&1
fi
echo "=== autostart $(date '+%Y-%m-%d %H:%M:%S') ==="

if [ "$DRY_RUN" = 1 ] || ! docker info >/dev/null 2>&1; then
  echo "Docker is not running: opening Docker Desktop."
  run open -a Docker
  waited=0
  while [ "$DRY_RUN" = 0 ] && ! docker info >/dev/null 2>&1; do
    if [ "$waited" -ge "$DOCKER_WAIT_SECONDS" ]; then
      echo "Docker did not start within ${DOCKER_WAIT_SECONDS}s: giving up."
      exit 1
    fi
    sleep 5
    waited=$((waited + 5))
  done
fi

echo "Starting postgres and redis."
run docker compose up -d
if [ "$DRY_RUN" = 0 ]; then sleep 8; fi

echo "Starting the app in local AI mode."
if [ "$DRY_RUN" = 1 ]; then
  echo "[dry-run] VIDGEN_AI_MODE=local bash scripts/dev_up.sh"
else
  VIDGEN_AI_MODE=local bash scripts/dev_up.sh
fi
echo "done."
