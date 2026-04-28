#!/usr/bin/env bash
# 宿主机出网正常但 bridge 容器无出网时：用 host 网络重建 trading-system（Redis 仍 compose + 6379 映射）。
# 代理：默认仅 HTTP http://127.0.0.1:7890（与 compose.hostnet 一致）；勿用裸 docker run，会丢卷与 Redis 依赖。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> 使用 docker-compose.yml + docker-compose.hostnet.yml 重建 trading-system …"
docker compose -f docker-compose.yml -f docker-compose.hostnet.yml up -d --force-recreate trading-system

PORT="${API_PORT:-8000}"
echo "==> 等待 http://127.0.0.1:${PORT}/api/v1/system/health …"
for i in $(seq 1 30); do
  if curl -sf --max-time 5 "http://127.0.0.1:${PORT}/api/v1/system/health" >/dev/null 2>&1; then
    echo "OK"
    exit 0
  fi
  sleep 2
done
echo "超时，请: docker logs openclaw-trading --tail 60"
exit 1
