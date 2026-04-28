#!/usr/bin/env bash
# 完整栈网络与模块验收：compose 校验 → 重建启动 → 健康轮询 → 容器内外连通性 → 验收 API。
# 在仓库根目录执行: bash scripts/verify_full_stack_network.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== [1/6] docker compose config =="
docker compose config -q

echo "== [2/6] docker compose up -d --build =="
docker compose up -d --build

echo "== [3/6] wait /api/v1/system/health (host -> published port) =="
ok=0
for i in $(seq 1 50); do
  if curl -sf --max-time 15 "http://127.0.0.1:${API_PORT:-8000}/api/v1/system/health" >/dev/null; then
    ok=1
    echo "health OK (attempt $i)"
    break
  fi
  echo "waiting... ($i)"
  sleep 3
done
if [[ "$ok" != "1" ]]; then
  echo "FAIL: health not ready" >&2
  docker compose logs --tail=120 trading-system >&2 || true
  exit 1
fi

echo "== [4/6] network smoke (inside trading-system, +redis +api) =="
docker compose exec -T trading-system python3 scripts/network_connectivity_smoke.py \
  --redis \
  --api-url "http://127.0.0.1:8000/api/v1/system/health"

echo "== [5/6] startup acceptance (inside container) =="
docker compose exec -T trading-system env ACCEPTANCE_BASE="http://127.0.0.1:8000" \
  python3 scripts/startup_acceptance.py

echo "== [6/6] commander audit (optional) =="
curl -sf --max-time 60 "http://127.0.0.1:${API_PORT:-8000}/api/v1/modules/commander/audit?enrich=true" | head -c 2500 || echo "(audit skip or non-200)"

echo ""
echo "VERIFY_FULL_STACK=PASS"
