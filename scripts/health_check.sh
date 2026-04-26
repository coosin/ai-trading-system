#!/bin/bash
# OpenClaw Trading System - Health Check Script
# Run frequency: hourly
# 
# 重要：此脚本只监控系统状态，不直接启动进程
# 所有进程管理通过 systemd 进行

APP_NAME="openclaw-trading"
APP_DIR="/home/cool/.openclaw-trading"
LOG_FILE="$APP_DIR/logs/health_check.log"
ALERT_FILE="$APP_DIR/logs/alerts.log"
SERVICE_NAME="openclaw-trading.service"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTH_CHECK_SCRIPT="$SELF_DIR/openclaw_auth_selfcheck.sh"
AUTH_CHECK_BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
REGIME_HEALTH_STATE_FILE="$APP_DIR/logs/regime_attribution_health.state"

# Telegram configuration
# Use explicit proxy to avoid network timeouts in restricted networks.
TELEGRAM_PROXY="http://127.0.0.1:7890"
TELEGRAM_BOT_TOKEN="8792055007:AAHpk8zwcsCXYh3bKqwDgxb4UVLZ3Qlik60"
TELEGRAM_CHAT_ID="6716232147"

mkdir -p "$(dirname "$LOG_FILE")"

send_telegram() {
    local message="$1"
    if [ -n "$TELEGRAM_CHAT_ID" ]; then
        curl -s -x "$TELEGRAM_PROXY" -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
            -d chat_id="$TELEGRAM_CHAT_ID" \
            -d text="$message" \
            -d parse_mode="Markdown" > /dev/null 2>&1
    fi
}

restart_service() {
    if [ "$(id -u)" -eq 0 ]; then
        systemctl restart "$SERVICE_NAME" 2>/dev/null
    else
        sudo systemctl restart "$SERVICE_NAME" 2>/dev/null
    fi
}

service_exists() {
    systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '{print $1}' | grep -qx "$SERVICE_NAME"
}

echo "=== $(date) Health Check ===" >> "$LOG_FILE"

ALERTS=""
CRITICAL=false

# Check regime attribution readiness (notify only on state change)
REGIME_HEALTH_RAW=$(curl -s "${AUTH_CHECK_BASE_URL}/api/v1/trades/attribution/regime/health" 2>/dev/null || true)
if [ -n "$REGIME_HEALTH_RAW" ]; then
    REGIME_READY=$(python3 - <<'PY'
import json, os
raw = os.environ.get("REGIME_HEALTH_RAW", "").strip()
try:
    d = json.loads(raw) if raw else {}
    print("true" if bool((d.get("readiness") or {}).get("ready_for_regime_tuning")) else "false")
except Exception:
    print("unknown")
PY
)
    REGIME_SUMMARY=$(python3 - <<'PY'
import json, os
raw = os.environ.get("REGIME_HEALTH_RAW", "").strip()
try:
    d = json.loads(raw) if raw else {}
    sample = d.get("sample") or {}
    cov = d.get("coverage") or {}
    print(
        f"total={sample.get('total', 0)} "
        f"regime_cov={cov.get('regime_coverage', 0)} "
        f"pnl_cov={cov.get('nonzero_pnl_coverage', 0)}"
    )
except Exception:
    print("parse_failed")
PY
)
    PREV_READY=""
    if [ -f "$REGIME_HEALTH_STATE_FILE" ]; then
        PREV_READY=$(cat "$REGIME_HEALTH_STATE_FILE" 2>/dev/null)
    fi
    echo "$REGIME_READY" > "$REGIME_HEALTH_STATE_FILE"
    echo "[INFO] Regime attribution health: ready=${REGIME_READY} ${REGIME_SUMMARY}" >> "$LOG_FILE"
    if [ "$REGIME_READY" = "unknown" ]; then
        ALERTS="${ALERTS}WARNING: regime attribution health parse failed\n"
    elif [ "$PREV_READY" != "$REGIME_READY" ] && [ -n "$PREV_READY" ]; then
        if [ "$REGIME_READY" = "true" ]; then
            ALERTS="${ALERTS}INFO: regime attribution is READY (${REGIME_SUMMARY})\n"
        else
            ALERTS="${ALERTS}WARNING: regime attribution is NOT READY (${REGIME_SUMMARY})\n"
        fi
    fi
else
    ALERTS="${ALERTS}WARNING: regime attribution health endpoint unavailable\n"
fi

# Check systemd service status (preferred method when service exists)
if service_exists; then
    SERVICE_STATUS=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null)
    if [ "$SERVICE_STATUS" != "active" ]; then
        ALERTS="${ALERTS}WARNING: Service not active (status: $SERVICE_STATUS)\n"
        echo "[CRITICAL] Service not active!" | tee -a "$ALERT_FILE"
        
        # Try to restart via systemctl (not direct process start)
        restart_service
        sleep 5
        
        NEW_STATUS=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null)
        if [ "$NEW_STATUS" = "active" ]; then
            ALERTS="${ALERTS}SUCCESS: Service restarted via systemctl\n"
            echo "[INFO] Service restarted via systemctl" >> "$LOG_FILE"
        else
            ALERTS="${ALERTS}ERROR: Service restart failed!\n"
            echo "[EMERGENCY] Service restart failed!" | tee -a "$ALERT_FILE"
            CRITICAL=true
        fi
    fi
else
    ALERTS="${ALERTS}INFO: ${SERVICE_NAME} not found; skipped systemd service restart check\n"
    echo "[INFO] ${SERVICE_NAME} not found; skipped systemd restart check" >> "$LOG_FILE"
fi

# Check for multiple instances (should never happen)
PROCESS_COUNT=$(pgrep -f "python.*src.main" 2>/dev/null | wc -l)
if [ "$PROCESS_COUNT" -gt 1 ]; then
    ALERTS="${ALERTS}WARNING: Multiple instances detected ($PROCESS_COUNT)\n"
    echo "[WARNING] Multiple instances detected!" | tee -a "$ALERT_FILE"
    
    # Kill all but the systemd service
    SYSTEMD_PID=$(systemctl show --property MainPID "$SERVICE_NAME" 2>/dev/null | cut -d= -f2)
    
    for PID in $(pgrep -f "python.*src.main" 2>/dev/null); do
        if [ "$PID" != "$SYSTEMD_PID" ] && [ "$PID" -gt 1 ]; then
            kill -9 "$PID" 2>/dev/null
            ALERTS="${ALERTS}Killed extra process: $PID\n"
            echo "[INFO] Killed extra process: $PID" >> "$LOG_FILE"
        fi
    done
fi

# Check API
if ! curl -s http://localhost:8000/api/v1/health > /dev/null 2>&1; then
    ALERTS="${ALERTS}WARNING: API service not responding\n"
    echo "[WARNING] API service not responding" >> "$ALERT_FILE"
fi

# Check OpenClaw -> Trading API token auth path
if [ -x "$AUTH_CHECK_SCRIPT" ]; then
    if [ -n "${OPENCLAW_API_TOKEN:-}" ]; then
        AUTH_OUTPUT=$(
            BASE_URL="$AUTH_CHECK_BASE_URL" \
            OPENCLAW_API_TOKEN="$OPENCLAW_API_TOKEN" \
            OPENCLAW_SOURCE="${OPENCLAW_SOURCE:-openclaw}" \
            "$AUTH_CHECK_SCRIPT" 2>&1
        ) || AUTH_RC=$?
        AUTH_RC=${AUTH_RC:-0}
        if [ "$AUTH_RC" -ne 0 ]; then
            ALERTS="${ALERTS}WARNING: OpenClaw auth self-check failed (rc=${AUTH_RC})\n"
            echo "[WARNING] OpenClaw auth self-check failed (rc=${AUTH_RC})" | tee -a "$ALERT_FILE"
            echo "$AUTH_OUTPUT" >> "$LOG_FILE"
            CRITICAL=true
        else
            echo "[INFO] OpenClaw auth self-check passed" >> "$LOG_FILE"
        fi
    else
        ALERTS="${ALERTS}INFO: OPENCLAW_API_TOKEN is not set; skipped auth self-check\n"
        echo "[INFO] OPENCLAW_API_TOKEN is not set; skipped auth self-check" >> "$LOG_FILE"
    fi
else
    ALERTS="${ALERTS}WARNING: Auth self-check script not executable: ${AUTH_CHECK_SCRIPT}\n"
    echo "[WARNING] Auth self-check script not executable: ${AUTH_CHECK_SCRIPT}" >> "$ALERT_FILE"
fi

# Check memory
MEM_USED=$(free | grep Mem | awk '{print int($3/$2 * 100)}')
if [ "$MEM_USED" -gt 90 ]; then
    ALERTS="${ALERTS}WARNING: High memory usage: ${MEM_USED}%\n"
    echo "[WARNING] High memory usage: ${MEM_USED}%" | tee -a "$ALERT_FILE"
    CRITICAL=true
elif [ "$MEM_USED" -gt 80 ]; then
    ALERTS="${ALERTS}INFO: Memory usage: ${MEM_USED}%\n"
fi

# Check disk
DISK_USED=$(df -h /home | grep -v Filesystem | awk '{print $5}' | tr -d '%')
if [ "$DISK_USED" -gt 90 ]; then
    ALERTS="${ALERTS}WARNING: Low disk space: ${DISK_USED}%\n"
    echo "[WARNING] Low disk space: ${DISK_USED}%" | tee -a "$ALERT_FILE"
    CRITICAL=true
fi

# Check error logs
ERROR_COUNT=$(grep -c "ERROR" "$APP_DIR/logs/app.log" 2>/dev/null || echo "0")
if [ "$ERROR_COUNT" -gt 20 ]; then
    ALERTS="${ALERTS}WARNING: Too many errors in log: ${ERROR_COUNT}\n"
    echo "[WARNING] Too many errors: ${ERROR_COUNT}" >> "$ALERT_FILE"
fi

# Send Telegram notification
if [ -n "$ALERTS" ]; then
    if [ "$CRITICAL" = true ]; then
        MESSAGE="*OpenClaw System Alert*\n\n$(echo -e "$ALERTS")\nTime: $(date '+%Y-%m-%d %H:%M:%S')\nPlease check immediately!"
    else
        MESSAGE="*OpenClaw System Notice*\n\n$(echo -e "$ALERTS")\nTime: $(date '+%Y-%m-%d %H:%M:%S')"
    fi
    send_telegram "$MESSAGE"
fi

echo "Health check complete" >> "$LOG_FILE"
