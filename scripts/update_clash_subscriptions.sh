#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/cool/.openclaw-trading"
PY="${ROOT}/scripts/subscription_updater.py"
VENV_PY="${ROOT}/.venv-tools/bin/python"
LOCAL_CFG="${ROOT}/config/clash_config.yaml"
TMP_CFG="/etc/mihomo/generated_from_openclaw.yaml"
CLASH_API="http://127.0.0.1:9090/configs"
SYSTEM_CFG="/etc/mihomo/config.yaml"
LOG_DIR="${ROOT}/logs"
LOG_FILE="${LOG_DIR}/clash_subscription_update.log"

mkdir -p "${LOG_DIR}"

{
  echo "[$(date '+%F %T')] start subscription update"
  if [[ -x "${VENV_PY}" ]]; then
    "${VENV_PY}" "${PY}"
  else
    python3 "${PY}"
  fi

  if [[ ! -s "${LOCAL_CFG}" ]]; then
    echo "[$(date '+%F %T')] ERROR local config missing: ${LOCAL_CFG}"
    exit 1
  fi

  cp "${LOCAL_CFG}" "${TMP_CFG}"
  chmod 644 "${TMP_CFG}"

  CLASH_SECRET="${CLASH_SECRET:-}"
  if [[ -z "${CLASH_SECRET}" ]]; then
    SECRET_PY="python3"
    if [[ -x "${VENV_PY}" ]]; then
      SECRET_PY="${VENV_PY}"
    fi
    CLASH_SECRET="$(${SECRET_PY} - <<'PY'
import yaml
paths = [
    "/etc/mihomo/config.yaml",
    "/home/cool/.openclaw-trading/config/clash_config.yaml",
]
for p in paths:
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = yaml.safe_load(f) or {}
        secret = (d.get("secret") or "").strip()
        if secret:
            print(secret)
            break
    except Exception:
        continue
else:
    print("")
PY
)"
  fi

  if [[ -n "${CLASH_SECRET}" ]]; then
    curl -fsS -X PUT "${CLASH_API}" \
      -H 'Content-Type: application/json' \
      -H "Authorization: Bearer ${CLASH_SECRET}" \
      -d "{\"path\":\"${TMP_CFG}\"}" >/dev/null
  else
    curl -fsS -X PUT "${CLASH_API}" \
      -H 'Content-Type: application/json' \
      -d "{\"path\":\"${TMP_CFG}\"}" >/dev/null
  fi

  echo "[$(date '+%F %T')] clash reloaded with ${TMP_CFG}"
} >> "${LOG_FILE}" 2>&1

