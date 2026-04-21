#!/usr/bin/env bash
set -euo pipefail

# Lightweight watchdog for API control-plane hangs.
# Trigger: /health timeout/failure N consecutive checks.

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
CHECK_TIMEOUT_SEC="${CHECK_TIMEOUT_SEC:-5}"
CHECK_INTERVAL_SEC="${CHECK_INTERVAL_SEC:-20}"
MAX_CONSECUTIVE_FAILS="${MAX_CONSECUTIVE_FAILS:-3}"
PY_BIN="${PY_BIN:-/home/cool/ai-trading-system/.venv/bin/python}"
PROJECT_DIR="${PROJECT_DIR:-/home/cool/ai-trading-system}"
LOG_FILE="${LOG_FILE:-/home/cool/ai-trading-system/logs/control_plane_autoheal.log}"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE" >/dev/null
}

restart_main() {
  log "[autoheal] restarting src.main due to health check failures"
  pkill -f "python -m src.main" || true
  sleep 1
  nohup "$PY_BIN" -m src.main > /tmp/trading_system_autoheal.log 2>&1 < /dev/null &
  sleep 2
  log "[autoheal] restart command issued"
}

fails=0
log "[autoheal] started: BASE_URL=$BASE_URL interval=${CHECK_INTERVAL_SEC}s threshold=$MAX_CONSECUTIVE_FAILS"
cd "$PROJECT_DIR"

while true; do
  if curl -sS -m "$CHECK_TIMEOUT_SEC" "$BASE_URL/health" >/dev/null 2>&1; then
    if [[ "$fails" -gt 0 ]]; then
      log "[autoheal] health recovered (fails reset from $fails)"
    fi
    fails=0
  else
    fails=$((fails + 1))
    log "[autoheal] health check failed ($fails/$MAX_CONSECUTIVE_FAILS)"
    if [[ "$fails" -ge "$MAX_CONSECUTIVE_FAILS" ]]; then
      restart_main
      fails=0
    fi
  fi
  sleep "$CHECK_INTERVAL_SEC"
done

