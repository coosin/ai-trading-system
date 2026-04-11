#!/usr/bin/env bash
# 正式将当前代码与 compose 配置部署到容器并做健康 / OKX 验收。
# 用法：在项目根目录执行  ./scripts/deploy_production_stack.sh
# 说明：交易模式由根目录 .env 的 MODE 决定（simulation / paper_trading / live_trading），
#       实盘前请确认 API、风控与 OKX_TESTNET 等配置。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> 构建镜像（trading-system）…"
docker compose build trading-system

echo "==> 启动 / 重建 trading-system 与 redis…"
docker compose up -d

echo "==> 等待 API 就绪（最多 120s）…"
for i in $(seq 1 24); do
  if docker exec openclaw-trading curl -sf -o /dev/null "http://127.0.0.1:8000/health" 2>/dev/null; then
    echo "API 已就绪"
    break
  fi
  if [[ "$i" -eq 24 ]]; then
    echo "ERROR: 健康检查超时，请查看: docker logs openclaw-trading --tail 80"
    exit 1
  fi
  sleep 5
done

echo "==> OKX / 连接验收…"
"$ROOT/scripts/verify_okx_container.sh"

echo ""
echo "部署完成。当前 MODE / TRADING_MODE 见:"
docker exec openclaw-trading printenv MODE OPENCLAW__trading__mode OKX_TESTNET 2>/dev/null || true
echo "开发/回测请在 .env 设 MODE=simulation 与 TRADING_MODE=simulation 后: docker compose up -d --force-recreate trading-system"
