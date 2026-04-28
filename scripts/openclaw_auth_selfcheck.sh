#!/usr/bin/env bash
set -euo pipefail

# OpenClaw -> Trading API auth self-check
# Usage:
#   OPENCLAW_API_TOKEN=xxx ./scripts/openclaw_auth_selfcheck.sh
#   BASE_URL=http://127.0.0.1:8000 OPENCLAW_API_TOKEN=xxx ./scripts/openclaw_auth_selfcheck.sh

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TOKEN="${OPENCLAW_API_TOKEN:-}"
API_USERNAME="${OPENCLAW_API_ADMIN_USERNAME:-}"
API_PASSWORD="${OPENCLAW_API_ADMIN_PASSWORD:-}"
SOURCE="${OPENCLAW_SOURCE:-openclaw}"
TIMEOUT_SEC="${OPENCLAW_DISPATCH_TIMEOUT_SEC:-8}"

if [[ -z "${TOKEN}" && ( -z "${API_USERNAME}" || -z "${API_PASSWORD}" ) ]]; then
  echo "[FAIL] Missing auth material."
  echo "       Set OPENCLAW_API_TOKEN, or set OPENCLAW_API_ADMIN_USERNAME + OPENCLAW_API_ADMIN_PASSWORD."
  exit 2
fi

_curl_json() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local override_token="${4:-}"
  local auth_token="${override_token:-$TOKEN}"
  if [[ -n "${body}" ]]; then
    curl -fsS -X "${method}" "${BASE_URL}${path}" \
      -H "Authorization: Bearer ${auth_token}" \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
      -d "${body}"
  else
    curl -fsS -X "${method}" "${BASE_URL}${path}" \
      -H "Authorization: Bearer ${auth_token}" \
      -H "Accept: application/json"
  fi
}

echo "[INFO] BASE_URL=${BASE_URL}"
echo "[INFO] source=${SOURCE}"
echo "[STEP] 1/4 health"
_curl_json GET "/api/v1/system/health" >/dev/null
echo "[OK] health reachable"

echo "[STEP] 2/4 auth status"
AUTH_STATUS="$(_curl_json GET "/api/v1/auth/status")"
echo "${AUTH_STATUS}" | python3 -c 'import json,sys; raw=sys.stdin.read().strip(); obj=json.loads(raw); assert "enforce_auth_on_writes" in obj; assert "required_write_roles" in obj; print("[OK] auth/status:", json.dumps({"enforce_auth_on_writes": obj.get("enforce_auth_on_writes"), "required_write_roles": obj.get("required_write_roles"), "require_ws_auth": obj.get("require_ws_auth")}, ensure_ascii=False))'

echo "[STEP] 3/4 write policy"
WRITE_POLICY="$(_curl_json GET "/api/v1/auth/write-policy")"
echo "${WRITE_POLICY}" | python3 -c 'import json,sys; raw=sys.stdin.read().strip(); obj=json.loads(raw); assert obj.get("success") is True; policy=obj.get("policy") or {}; assert "protected_write_prefixes" in policy; print("[OK] auth/write-policy:", json.dumps({"required_write_roles": policy.get("required_write_roles"), "protected_write_prefixes": policy.get("protected_write_prefixes")}, ensure_ascii=False))'

echo "[STEP] 4/4 dispatch write path"
DISPATCH_PAYLOAD="$(python3 - <<'PY'
import json
import os
print(json.dumps({
  "message":"系统巡检（auth_selfcheck）",
  "source":os.environ.get("OPENCLAW_SOURCE", "openclaw"),
  "timeout_sec":float(os.environ.get("OPENCLAW_DISPATCH_TIMEOUT_SEC", "8"))
}, ensure_ascii=False))
PY
)"

DISPATCH_RES=""
if ! DISPATCH_RES="$(_curl_json POST "/api/v1/modules/commander/dispatch" "${DISPATCH_PAYLOAD}" 2>/dev/null)"; then
  DISPATCH_RES=""
fi
_dispatch_ok() {
  local raw="${1:-}"
  if [[ -z "${raw}" ]]; then
    return 1
  fi
  echo "${raw}" | python3 -c 'import json,sys; raw=sys.stdin.read().strip();
try:
  obj=json.loads(raw) if raw else {}
except Exception:
  raise SystemExit(1)
ok=bool(obj.get("success"))
status=str(obj.get("status") or "")
allowed={"completed","timeout","queued","running","accepted","success",""}
if ok and status in allowed:
  print("[OK] dispatch auth passed:", json.dumps({"status": status, "success": ok}, ensure_ascii=False))
  raise SystemExit(0)
raise SystemExit(1)'
}

if ! _dispatch_ok "${DISPATCH_RES}"; then
  if [[ -n "${API_USERNAME}" && -n "${API_PASSWORD}" ]]; then
    echo "[WARN] token dispatch failed, trying login fallback with OPENCLAW_API_ADMIN_USERNAME"
    LOGIN_PAYLOAD="$(python3 - <<'PY'
import json, os
print(json.dumps({
  "username": os.environ.get("OPENCLAW_API_ADMIN_USERNAME", ""),
  "password": os.environ.get("OPENCLAW_API_ADMIN_PASSWORD", ""),
}, ensure_ascii=False))
PY
)"
    LOGIN_RES="$(curl -fsS -X POST "${BASE_URL}/api/v1/auth/login" \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
      -d "${LOGIN_PAYLOAD}")"
    LOGIN_TOKEN="$(echo "${LOGIN_RES}" | python3 -c 'import json,sys; obj=json.loads(sys.stdin.read().strip()); print((obj.get("access_token") or obj.get("token") or "").strip())')"
    if [[ -z "${LOGIN_TOKEN}" ]]; then
      echo "[FAIL] login fallback did not return token"
      exit 1
    fi
    DISPATCH_RES="$(_curl_json POST "/api/v1/modules/commander/dispatch" "${DISPATCH_PAYLOAD}" "${LOGIN_TOKEN}")"
    if ! _dispatch_ok "${DISPATCH_RES}"; then
      echo "[FAIL] dispatch auth failed even after login fallback."
      echo "[DEBUG] dispatch response: ${DISPATCH_RES}"
      exit 1
    fi
    echo "[OK] dispatch auth passed via login fallback"
  else
    echo "[FAIL] dispatch auth failed and no login fallback credentials provided."
    exit 1
  fi
fi

echo "[PASS] OpenClaw auth self-check passed."
