#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/cool/.openclaw-trading"
PY="${ROOT}/scripts/subscription_updater.py"
LOCAL_CFG="${ROOT}/config/clash_config.yaml"
TMP_CFG="/tmp/clash_config.yaml"
CLASH_API="http://127.0.0.1:9090/configs"
LOG_DIR="${ROOT}/logs"
LOG_FILE="${LOG_DIR}/clash_subscription_update.log"

mkdir -p "${LOG_DIR}"

{
  echo "[$(date '+%F %T')] start subscription update"
  python3 "${PY}"

  if [[ ! -s "${LOCAL_CFG}" ]]; then
    echo "[$(date '+%F %T')] ERROR local config missing: ${LOCAL_CFG}"
    exit 1
  fi

  cp "${LOCAL_CFG}" "${TMP_CFG}"
  chmod 644 "${TMP_CFG}"

  curl -fsS -X PUT "${CLASH_API}" \
    -H 'Content-Type: application/json' \
    -d "{\"path\":\"${TMP_CFG}\"}" >/dev/null

  echo "[$(date '+%F %T')] clash reloaded with ${TMP_CFG}"
} >> "${LOG_FILE}" 2>&1

