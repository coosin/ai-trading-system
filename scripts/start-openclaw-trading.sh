#!/bin/bash
# OpenClaw Trading System - Start Script (single-instance guarded)

set -euo pipefail

APP_NAME="openclaw-trading"
APP_DIR="/home/cool/ai-trading-system"
LOG_DIR="$APP_DIR/logs"
PID_FILE="/tmp/${APP_NAME}.pid"
LOCK_FILE="/tmp/${APP_NAME}.lock"
PY="${APP_DIR}/.venv/bin/python"
CMD_PREFIX="${PY} -m src.main"

running_pids() {
  python3 - <<'PY'
import os
prefix="/home/cool/ai-trading-system/.venv/bin/python -m src.main"
out=[]
for pid in os.listdir("/proc"):
    if not pid.isdigit():
        continue
    try:
        cmd=open(f"/proc/{pid}/cmdline","rb").read().decode("utf-8","ignore").replace("\x00"," ").strip()
    except Exception:
        continue
    if cmd.startswith(prefix):
        out.append(int(pid))
print(" ".join(str(x) for x in sorted(out)))
PY
}

if [[ "${1:-}" == "status" ]]; then
  PIDS="$(running_pids)"
  if [[ -n "${PIDS}" ]]; then
    echo "RUNNING: ${PIDS}"
  else
    echo "STOPPED"
  fi
  exit 0
fi

cd "$APP_DIR"

if [[ ! -x "$PY" ]]; then
  echo "ERROR: venv missing at $PY — run: cd $APP_DIR && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

mkdir -p "$LOG_DIR"

PIDS="$(running_pids)"
if [[ -n "${PIDS}" ]]; then
  echo "ERROR: ${APP_NAME} already running (PID(s): ${PIDS})"
  echo "Use ./scripts/stop-openclaw-trading.sh before starting a new instance."
  exit 1
fi

# Clean stale bookkeeping files if no real process exists.
rm -f "$PID_FILE" "$LOCK_FILE"

echo "Starting OpenClaw Trading System..."
nohup "$PY" -m src.main >> "$LOG_DIR/app.log" 2>&1 &
sleep 3

PIDS="$(running_pids)"
if [[ -n "${PIDS}" ]]; then
  NEW_PID="$(echo "$PIDS" | awk '{print $1}')"
  echo "$NEW_PID" > "$PID_FILE"
  echo "SUCCESS: OpenClaw Trading System started (PID: $NEW_PID)"
  echo "Log file: $LOG_DIR/app.log"
  echo "API docs: http://localhost:8000/docs"
  exit 0
fi

echo "FAILED: OpenClaw Trading System did not start"
echo "Check logs: tail -50 $LOG_DIR/app.log"
exit 1
