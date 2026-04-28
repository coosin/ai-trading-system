#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
API_URL="${OPENCLAW_HEALTH_URL:-http://127.0.0.1:8000/api/v1/system/health}"
REDIS_HOST="${OPENCLAW_REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${OPENCLAW_REDIS_PORT:-6379}"

echo "[health_check] root=${ROOT_DIR}"
echo "[health_check] api=${API_URL}"

if command -v curl >/dev/null 2>&1; then
  API_BODY="$(curl -fsS --max-time 8 "${API_URL}" || true)"
else
  API_BODY=""
fi

if [[ -z "${API_BODY}" ]]; then
  echo "[health_check] ERROR: api health request failed"
  exit 1
fi

if [[ "${API_BODY}" != *"\"success\": true"* && "${API_BODY}" != *"\"success\":true"* ]]; then
  echo "[health_check] ERROR: api health payload unexpected: ${API_BODY}"
  exit 1
fi

echo "[health_check] api health ok"

if command -v redis-cli >/dev/null 2>&1; then
  if redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" ping >/dev/null 2>&1; then
    echo "[health_check] redis ok (${REDIS_HOST}:${REDIS_PORT})"
  else
    echo "[health_check] ERROR: redis ping failed (${REDIS_HOST}:${REDIS_PORT})"
    exit 2
  fi
else
  if command -v nc >/dev/null 2>&1 && nc -z -w 2 "${REDIS_HOST}" "${REDIS_PORT}" >/dev/null 2>&1; then
    echo "[health_check] redis port open (${REDIS_HOST}:${REDIS_PORT})"
  else
    echo "[health_check] ERROR: redis unavailable and redis-cli missing"
    exit 2
  fi
fi

echo "[health_check] all checks passed"
