#!/usr/bin/env bash
# 交易系统启动后一键检查：HTTP 健康、架构验收快照、交易所绑定调试。
set -euo pipefail
BASE="${OPENCLAW_API_BASE:-http://127.0.0.1:8000}"

echo "GET $BASE/health"
curl -sS -m 8 "${BASE}/health" | head -c 600 || true
echo ""
echo "---"
echo "GET $BASE/api/v1/status (truncated)"
curl -sS -m 15 "${BASE}/api/v1/status" | head -c 2500 || true
echo ""
echo "---"
echo "GET $BASE/api/v1/system/acceptance"
curl -sS -m 20 "${BASE}/api/v1/system/acceptance" | head -c 3500 || true
echo ""
echo "---"
echo "GET $BASE/api/v1/debug/exchange-binding"
curl -sS -m 15 "${BASE}/api/v1/debug/exchange-binding" | head -c 2000 || true
echo ""
