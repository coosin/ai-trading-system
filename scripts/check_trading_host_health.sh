#!/usr/bin/env bash
# 交易宿主快速体检：磁盘、内存/交换、Docker、建议项（不修改系统）。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Disk ==="
df -h / 2>/dev/null | tail -1

echo "=== Memory / Swap (高 swap 使用会导致行情/下单延迟抖动) ==="
free -h

echo "=== vm.swappiness (建议 10–30；默认 60 易积极换出) ==="
cat /proc/sys/vm/swappiness 2>/dev/null || true

echo "=== 容器 / 通用（若本机安装了 docker）==="
if command -v docker >/dev/null 2>&1; then
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Size}}' 2>/dev/null || true
  docker system df 2>/dev/null || true
else
  echo "(未安装 docker 或未在 PATH 中，已跳过)"
fi

echo "=== OpenClaw logs size ==="
du -sh "$ROOT/logs" 2>/dev/null || true

echo "=== 建议 ==="
echo "- 根分区 >90% 时：清理旧日志、包管理器缓存、或扩容。"
echo "- swap 长期高位：加内存或降负载；持久化见 config/trading-host-sysctl.conf"
if [[ -d "$ROOT/venv" && -d "$ROOT/.venv" ]]; then
  echo "- 重复 venv：同时存在 venv/ 与 .venv/，可 OPENCLAW_REMOVE_DOTVENV=1 ./scripts/cleanup_trading_workspace.sh 仅保留 venv/"
fi
if [[ -d "$ROOT/.venv_test" ]]; then
  echo "- 测试环境 .venv_test/ 可删：OPENCLAW_REMOVE_TEST_VENV=1 ./scripts/cleanup_trading_workspace.sh（测试脚本会重建）"
fi
