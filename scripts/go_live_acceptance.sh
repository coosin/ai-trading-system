#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
PROBE_TAG="go_live_memory_probe_$(date +%s)"

pass_count=0
fail_count=0

ok() {
  echo "[PASS] $1"
  pass_count=$((pass_count + 1))
}

fail() {
  echo "[FAIL] $1"
  fail_count=$((fail_count + 1))
}

assert_contains() {
  local name="$1"
  local body="$2"
  local needle="$3"
  if [[ "$body" == *"$needle"* ]]; then
    ok "$name"
  else
    fail "$name"
    echo "  expected contains: $needle"
    echo "  got: ${body:0:500}"
  fi
}

get_json() {
  local path="$1"
  curl -sS "${BASE_URL}${path}"
}

post_json() {
  local path="$1"
  local data="$2"
  curl -sS -X POST "${BASE_URL}${path}" -H "Content-Type: application/json" -d "$data"
}

echo "=== OpenClaw Go-Live Acceptance ==="
echo "BASE_URL=${BASE_URL}"

# 1) health & core status
health="$(get_json /health || true)"
assert_contains "health endpoint" "$health" "\"healthy\""

s1="$(get_json /api/v1/s1/verify || true)"
assert_contains "s1 verify all_passed" "$s1" "\"all_passed\":true"

sys_health="$(get_json /api/v1/modules/system/health || true)"
assert_contains "module system health" "$sys_health" "\"overall\":\"healthy\""

# 2) event stream / push compensation
events="$(get_json '/api/v1/trade/events?limit=15' || true)"
if [[ "$events" == *"market.update"* || "$events" == *"trade.position"* || "$events" == *"trade.fill"* ]]; then
  ok "trade events stream"
else
  fail "trade events stream"
  echo "  got: ${events:0:500}"
fi

# 3) alerts
alerts="$(get_json /api/v1/monitoring/alerts || true)"
if [[ "$alerts" == "[]" || "$alerts" == *"["* ]]; then
  ok "alerts endpoint reachable"
else
  fail "alerts endpoint reachable"
  echo "  got: ${alerts:0:500}"
fi

# 4) commander audit / memory status
audit="$(get_json '/api/v1/modules/commander/audit?enrich=true' || true)"
assert_contains "commander audit all_passed" "$audit" "\"all_passed\":true"

mem_status="$(get_json /api/v1/modules/commander/memory/status || true)"
assert_contains "commander memory status success" "$mem_status" "\"success\":true"

workspace_mem="$(get_json '/api/v1/modules/commander/memory/workspace?filename=COMMANDER_PROFILE.md' || true)"
assert_contains "workspace memory read" "$workspace_mem" "\"success\":true"

# 5) memory write/read probe
store_payload="{\"content\":\"${PROBE_TAG}\",\"category\":\"conversation\",\"layer\":\"working\"}"
store_out="$(post_json /api/v1/ai/memory/store "$store_payload" || true)"
assert_contains "memory store returns id" "$store_out" "\"memory_id\""

recall_payload="{\"query\":\"${PROBE_TAG}\",\"limit\":3}"
recall_out="$(post_json /api/v1/ai/memory/recall "$recall_payload" || true)"
assert_contains "memory recall probe hit" "$recall_out" "${PROBE_TAG}"

echo
echo "=== Summary ==="
echo "PASS=${pass_count} FAIL=${fail_count}"
if [[ $fail_count -eq 0 ]]; then
  echo "GO_LIVE_ACCEPTANCE=PASS"
  exit 0
else
  echo "GO_LIVE_ACCEPTANCE=FAIL"
  exit 1
fi

