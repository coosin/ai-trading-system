#!/bin/bash
# OpenClaw Trading System - Stop Script

set -euo pipefail

APP_NAME="openclaw-trading"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${APP_DIR}/runtime"
HOME_RUNTIME=""
if [[ -n "${HOME:-}" ]]; then
  HOME_RUNTIME="${HOME}/.openclaw-trading/runtime"
fi
PID_BASENAME="${APP_NAME}.pid"
PID_FILE="/tmp/${PID_BASENAME}"
LOCK_FILE="/tmp/${APP_NAME}.lock"
REPO_PID_FILE="${RUNTIME_DIR}/${PID_BASENAME}"
HOME_PID_FILE=""
if [[ -n "${HOME_RUNTIME}" ]]; then
  HOME_PID_FILE="${HOME_RUNTIME}/${PID_BASENAME}"
fi

running_pids() {
  APP_DIR="$APP_DIR" python3 - <<'PY'
import os

app_dir = os.environ.get("APP_DIR", "")
prefix = os.path.join(app_dir, ".venv", "bin", "python") + " -m src.main"
out = []
for pid_str in os.listdir("/proc"):
    if not pid_str.isdigit():
        continue
    try:
        cmd = (
            open(f"/proc/{pid_str}/cmdline", "rb")
            .read()
            .decode("utf-8", "ignore")
            .replace("\x00", " ")
            .strip()
        )
    except Exception:
        continue
    if cmd.startswith(prefix):
        out.append(int(pid_str))
print(" ".join(str(x) for x in sorted(out)))
PY
}

collect_target_pids() {
  local vals=()
  for f in "$PID_FILE" "$REPO_PID_FILE" "${HOME_PID_FILE:-}"; do
    [[ -n "${f:-}" && -f "$f" ]] || continue
    local pid
    pid="$(cat "$f" 2>/dev/null || true)"
    [[ "$pid" =~ ^[0-9]+$ ]] && vals+=("$pid")
  done
  local detected
  detected="$(running_pids)"
  if [[ -n "${detected:-}" ]]; then
    for pid in $detected; do
      vals+=("$pid")
    done
  fi
  printf '%s\n' "${vals[@]}" | awk 'NF' | sort -u
}

echo "Stopping OpenClaw Trading System..."
TARGET_PIDS="$(collect_target_pids || true)"
if [[ -z "${TARGET_PIDS:-}" ]]; then
    echo "No managed OpenClaw process found"
else
    echo "Sending SIGTERM to process(es): $(echo "$TARGET_PIDS" | tr '\n' ' ' | xargs)"
    while read -r PID; do
        [[ -n "${PID:-}" ]] || continue
        kill -TERM "$PID" 2>/dev/null || true
    done <<< "$TARGET_PIDS"

    for _ in $(seq 1 20); do
        sleep 1
        STILL_RUNNING=""
        while read -r PID; do
            [[ -n "${PID:-}" ]] || continue
            if kill -0 "$PID" 2>/dev/null; then
                STILL_RUNNING="${STILL_RUNNING}${PID}"$'\n'
            fi
        done <<< "$TARGET_PIDS"
        [[ -z "${STILL_RUNNING:-}" ]] && break
    done

    if [[ -n "${STILL_RUNNING:-}" ]]; then
        echo "Process not responding, force killing: $(echo "$STILL_RUNNING" | tr '\n' ' ' | xargs)"
        while read -r PID; do
            [[ -n "${PID:-}" ]] || continue
            kill -9 "$PID" 2>/dev/null || true
        done <<< "$STILL_RUNNING"
        sleep 1
    fi
    echo "SUCCESS: OpenClaw Trading System stopped"
fi

rm -f "$PID_FILE" "$LOCK_FILE" "$REPO_PID_FILE" 2>/dev/null || true
if [[ -n "${HOME_PID_FILE:-}" ]]; then
  rm -f "$HOME_PID_FILE" 2>/dev/null || true
fi
echo "Lock files cleaned"

echo "Cleanup complete"
