#!/usr/bin/env bash
# 完整栈网络与模块验收（裸机）：健康轮询 → 本机网络烟测 → 验收 API。
# 前提：已在仓库根启动 API（如 python -m src.main、./start_production.sh 或 systemd）。
# 在仓库根目录执行: bash scripts/verify_full_stack_network.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
API_PORT="${API_PORT:-8000}"
BASE="http://127.0.0.1:${API_PORT}"

echo "== [1/4] wait ${BASE}/api/v1/system/health =="
ok=0
for i in $(seq 1 50); do
  if curl -sf --max-time 15 "${BASE}/api/v1/system/health" >/dev/null; then
    ok=1
    echo "health OK (attempt $i)"
    break
  fi
  echo "waiting... ($i)"
  sleep 3
done
if [[ "$ok" != "1" ]]; then
  echo "FAIL: health not ready（请先启动本机 API，再重试本脚本）" >&2
  exit 1
fi

echo "== [2/4] network smoke (host Python, +redis +api) =="
python3 scripts/network_connectivity_smoke.py \
  --redis \
  --api-url "${BASE}/api/v1/system/health"

echo "== [3/4] startup acceptance =="
env ACCEPTANCE_BASE="$BASE" python3 scripts/startup_acceptance.py

echo "== [4/4] commander audit (optional) =="
curl -sf --max-time 60 "${BASE}/api/v1/modules/commander/audit?enrich=true" | head -c 2500 || echo "(audit skip or non-200)"

echo ""
echo "VERIFY_FULL_STACK=PASS"
