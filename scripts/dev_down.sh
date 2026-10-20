#!/usr/bin/env bash
# Stop the API, worker and dashboard started by dev_up.sh (postgres and redis keep running).
set -uo pipefail
cd "$(dirname "$0")/.."
STATE_DIR="$(pwd)/${STATE_DIR:-.dev}"
for name in web worker api; do
  pidfile="$STATE_DIR/$name.pid"
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    kill "$(cat "$pidfile")" && echo "stopped $name"
  fi
done
