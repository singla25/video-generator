#!/usr/bin/env bash
# Start the whole app on this machine: API (8000), worker and dashboard (5173).
# Needs the Docker postgres + redis from docker-compose.yml to be running already.
# Safe to run again: it never overwrites .env and never starts a second copy.
#   ENV_FILE=<path>   use another env file (default .env)
#   STATE_DIR=<path>  where logs and PIDs go (default .dev, git-ignored)
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-.env}"
STATE_DIR="$(pwd)/${STATE_DIR:-.dev}"
API_PORT=8000   # fixed: frontend/vite.config.ts proxies /api to it
WEB_PORT=5173
mkdir -p "$STATE_DIR/logs"

[ -x .venv/bin/uvicorn ] || { echo "Run 'uv sync' first (Python deps missing)."; exit 1; }
[ -d frontend/node_modules ] || { echo "Run 'cd frontend && npm ci' first (dashboard deps missing)."; exit 1; }

.venv/bin/python scripts/dev_setup.py --env-file "$ENV_FILE" env \
  ${DB_NAME:+--db-name "$DB_NAME"}

set -a; . "./$ENV_FILE"; set +a
if [ -z "${VIDGEN_ADMIN_PASSWORD_HASH:-}" ]; then
  echo "No admin login yet. Run this once, then run dev_up.sh again:"
  echo "  .venv/bin/python scripts/dev_setup.py --env-file $ENV_FILE create-admin"
  exit 1
fi

echo "Checking postgres and redis..."
.venv/bin/python - <<'PY' || { echo "Postgres or redis is not reachable. Start the Docker containers first."; exit 1; }
import os, socket
from sqlalchemy import create_engine, text
with create_engine(os.environ["VIDGEN_DATABASE_URL"]).connect() as c:
    c.execute(text("select 1"))
socket.create_connection(("127.0.0.1", 6379), timeout=3).close()
PY

# Migrations are never applied silently: list what is pending and ask first.
pending="$(.venv/bin/python scripts/dev_setup.py pending)"
if [ -n "$pending" ]; then
  echo "These database migrations are new and have NOT been applied yet:"
  echo "$pending" | sed 's/^/  /'
  if [ ! -t 0 ]; then
    echo "Not applied (no terminal to ask on). Run this script from a terminal to answer."; exit 1
  fi
  read -r -p "Apply them to the database named in $ENV_FILE now? [y/N] " answer
  case "$answer" in
    [yY]|[yY][eE][sS])
      .venv/bin/alembic -c backend/alembic.ini upgrade head >"$STATE_DIR/logs/migrate.log" 2>&1 \
        || { echo "Migration failed, see $STATE_DIR/logs/migrate.log"; exit 1; }
      echo "Migrations applied." ;;
    *) echo "Not applied. Nothing was started. Run the script again when you are ready."; exit 1 ;;
  esac
fi

start() {  # start <name> <command...>
  local name="$1"; shift
  if [ -f "$STATE_DIR/$name.pid" ] && kill -0 "$(cat "$STATE_DIR/$name.pid")" 2>/dev/null; then
    echo "$name already running (pid $(cat "$STATE_DIR/$name.pid"))"; return
  fi
  nohup "$@" >"$STATE_DIR/logs/$name.log" 2>&1 &
  echo $! >"$STATE_DIR/$name.pid"
}
start api .venv/bin/uvicorn vidgen.api.server:create_server_app --factory \
  --host 127.0.0.1 --port "$API_PORT"
start worker .venv/bin/python -m vidgen.worker
( cd frontend && start web ./node_modules/.bin/vite --host 127.0.0.1 --port "$WEB_PORT" --strictPort )

wait_for() {  # wait_for <url> <name>
  for _ in $(seq 1 40); do curl -fsS -o /dev/null "$1" && return 0; sleep 1; done
  echo "$2 did not come up, see $STATE_DIR/logs/"; exit 1
}
wait_for "http://127.0.0.1:$API_PORT/api/health" "API"
wait_for "http://127.0.0.1:$WEB_PORT/" "Dashboard"

echo
echo "Ready. Open: http://localhost:$WEB_PORT"
echo "Stop everything: scripts/dev_down.sh"
