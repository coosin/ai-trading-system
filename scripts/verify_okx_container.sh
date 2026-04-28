#!/usr/bin/env bash
# 容器内 OKX / API 连接快速验收（与当前 compose 代理、WS 配置一致）
set -euo pipefail
C="${CONTAINER_NAME:-openclaw-trading}"

if ! docker inspect "$C" >/dev/null 2>&1; then
  echo "容器不存在: $C"
  exit 1
fi

echo "=== GET /api/v1/system/health ==="
docker exec "$C" curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8000/api/v1/system/health

echo "=== GET /api/v1/exchanges ==="
docker exec "$C" curl -sS http://127.0.0.1:8000/api/v1/exchanges
echo ""

echo "=== GET /api/v1/market/ticker?symbol=BTC/USDT (前 500 字符) ==="
docker exec "$C" curl -sS "http://127.0.0.1:8000/api/v1/market/ticker?symbol=BTC/USDT" | head -c 500
echo ""

echo "=== 近期日志：OKX WebSocket / Hub（最多 25 行）==="
docker logs "$C" 2>&1 | grep -E "OKX WS|WebSocket Hub|OKX交易所初始化|限速\(50011\)|代理" | tail -25 || echo "(无匹配行)"

echo "=== 容器内 pytest：tests/unit/test_okx_websocket.py ==="
docker exec -e PYTEST_ADDOPTS="-p no:cacheprovider" "$C" \
  python3 -m pytest /app/tests/unit/test_okx_websocket.py -q --tb=short 2>&1 || true

echo "=== 完成 ==="
