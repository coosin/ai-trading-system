#!/bin/bash
# OpenClaw Trading System - Start Script (single-instance guarded)
#
# PID bookkeeping mirrors (any process can regenerate via: ./scripts/start-openclaw-trading.sh repair-pid):
# - /tmp/openclaw-trading.pid
# - <repo>/runtime/openclaw-trading.pid
# - ~/.openclaw-trading/runtime/openclaw-trading.pid

set -euo pipefail

APP_NAME="openclaw-trading"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${APP_DIR}/logs"
RUNTIME_DIR="${APP_DIR}/runtime"
HOME_RUNTIME=""
if [[ -n "${HOME:-}" ]]; then
  HOME_RUNTIME="${HOME}/.openclaw-trading/runtime"
fi
PID_FILE="/tmp/${APP_NAME}.pid"
PID_BASENAME="${APP_NAME}.pid"
LOCK_FILE="/tmp/${APP_NAME}.lock"
PY="${APP_DIR}/.venv/bin/python"
export APP_DIR_FOR_OPENCLAW="${APP_DIR}"
NOHUP_LOG_FILE="${LOG_DIR}/nohup.out.log"
NOHUP_MAX_MB="${OPENCLAW_NOHUP_MAX_MB:-50}"
NOHUP_MAX_BACKUPS="${OPENCLAW_NOHUP_MAX_BACKUPS:-7}"
HEALTH_URL="${OPENCLAW_HEALTH_URL:-http://127.0.0.1:8000/api/v1/system/health}"
HEALTH_WAIT_SECONDS="${OPENCLAW_HEALTH_WAIT_SECONDS:-60}"

rotate_nohup_log_if_needed() {
  local file="$1"
  local max_mb="$2"
  local max_backups="$3"
  local max_bytes=$((max_mb * 1024 * 1024))
  if [[ ! -f "$file" ]]; then
    return 0
  fi

  local size
  size="$(wc -c < "$file" 2>/dev/null || echo 0)"
  if [[ -z "$size" || "$size" -lt "$max_bytes" ]]; then
    return 0
  fi

  local ts
  ts="$(date +%Y%m%d_%H%M%S)"
  local rotated="${file}.${ts}"
  mv "$file" "$rotated"
  echo "Rotated nohup log: ${rotated}"

  # keep newest N rotated files
  local rotated_list
  rotated_list="$(ls -1t "${file}".* 2>/dev/null || true)"
  if [[ -n "$rotated_list" ]]; then
    local idx=0
    while IFS= read -r f; do
      idx=$((idx + 1))
      if [[ "$idx" -gt "$max_backups" ]]; then
        rm -f "$f"
      fi
    done <<< "$rotated_list"
  fi
}

write_pid_everywhere() {
  local NEW_PID="$1"
  mkdir -p "${RUNTIME_DIR}"
  echo "${NEW_PID}" > "${PID_FILE}"
  echo "${NEW_PID}" > "${RUNTIME_DIR}/${PID_BASENAME}"
  if [[ -n "${HOME_RUNTIME}" ]]; then
    mkdir -p "${HOME_RUNTIME}"
    echo "${NEW_PID}" > "${HOME_RUNTIME}/${PID_BASENAME}"
  fi
}

start_detached() {
  if command -v setsid >/dev/null 2>&1; then
    setsid "$PY" -m src.main </dev/null >> "$NOHUP_LOG_FILE" 2>&1 &
  else
    nohup "$PY" -m src.main </dev/null >> "$NOHUP_LOG_FILE" 2>&1 &
  fi
}

wait_for_health() {
  local waited=0
  while [[ "$waited" -lt "$HEALTH_WAIT_SECONDS" ]]; do
    if command -v curl >/dev/null 2>&1; then
      if curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then
        return 0
      fi
    fi
    sleep 1
    waited=$((waited + 1))
  done
  return 1
}

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

if [[ "${1:-}" == "status" ]]; then
  PIDS="$(running_pids)"
  if [[ -n "${PIDS}" ]]; then
    echo "RUNNING: ${PIDS}"
  else
    echo "STOPPED"
  fi
  exit 0
fi

if [[ "${1:-}" == "repair-pid" ]]; then
  PIDS="$(running_pids)"
  if [[ -z "${PIDS}" ]]; then
    echo "ERROR: no running openclaw process found to repair bookkeeping"
    exit 1
  fi
  NEW_PID="$(echo "${PIDS}" | awk '{print $1}')"
  write_pid_everywhere "${NEW_PID}"
  echo "REPAIRED: pid=${NEW_PID} (mirrored to /tmp, repo runtime/, ~/.openclaw-trading/runtime/)"
  exit 0
fi

cd "$APP_DIR"

if [[ ! -x "$PY" ]]; then
  echo "ERROR: venv missing at $PY — run: cd $APP_DIR && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

mkdir -p "$LOG_DIR" "${RUNTIME_DIR}"
if [[ -n "${HOME_RUNTIME}" ]]; then
  mkdir -p "${HOME_RUNTIME}"
fi

rotate_nohup_log_if_needed "$NOHUP_LOG_FILE" "$NOHUP_MAX_MB" "$NOHUP_MAX_BACKUPS"

PIDS="$(running_pids)"
if [[ -n "${PIDS}" ]]; then
  echo "ERROR: ${APP_NAME} already running (PID(s): ${PIDS})"
  echo "Use ./scripts/stop-openclaw-trading.sh before starting a new instance."
  exit 1
fi

rm -f "$PID_FILE" "$LOCK_FILE"

echo "Starting OpenClaw Trading System..."
# NOTE:
# src.main 已配置 RotatingFileHandler 写入 logs/app.log。
# 若这里再把 stdout/stderr 重定向到同一文件，会造成每条日志“双写”。
# 因此将 nohup 控制台输出落到独立文件，避免与应用文件日志重叠。
start_detached
sleep 3

PIDS="$(running_pids)"
if [[ -n "${PIDS}" ]]; then
  NEW_PID="$(echo "${PIDS}" | awk '{print $1}')"
  write_pid_everywhere "${NEW_PID}"
  if wait_for_health; then
    echo "SUCCESS: OpenClaw Trading System started (PID: $NEW_PID)"
    echo "Log file: $LOG_DIR/app.log"
    echo "Nohup output: $LOG_DIR/nohup.out.log"
    echo "API docs: http://localhost:8000/docs"
    exit 0
  fi
  echo "FAILED: process started but health endpoint did not become ready within ${HEALTH_WAIT_SECONDS}s"
  echo "Check logs: tail -50 $LOG_DIR/app.log"
  exit 1
fi

echo "FAILED: OpenClaw Trading System did not start"
echo "Check logs: tail -50 $LOG_DIR/app.log"
exit 1
