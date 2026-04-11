#!/usr/bin/env bash
# 交易环境维护：清理旧轮转日志、抓取残留、源码 __pycache__、重复/测试虚拟环境、构建缓存。
# 不删除：当前 app.log、最近审计、backups/、data/ 内业务数据、frontend/node_modules。
# 环境变量：
#   OPENCLAW_REMOVE_DOTVENV=1  若存在 venv/ 则删除重复的 .venv/（与 setup_environment / DEVELOPMENT 一致）
#   OPENCLAW_REMOVE_TEST_VENV=1 删除 .venv_test/（可由 run_full_test_suite.sh 再生）
#   OPENCLAW_PIP_CACHE_PURGE=1   对当前用户执行 pip cache purge
#   OPENCLAW_DOCKER_BUILDER_PRUNE=1  docker builder prune -f
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOGDIR="$ROOT/logs"
AUDIT_KEEP_DAYS="${AUDIT_KEEP_DAYS:-14}"
TRADING_LOG_KEEP="${TRADING_LOG_KEEP:-12}"
OPENCLAW_REMOVE_DOTVENV="${OPENCLAW_REMOVE_DOTVENV:-0}"
OPENCLAW_REMOVE_TEST_VENV="${OPENCLAW_REMOVE_TEST_VENV:-0}"
OPENCLAW_PIP_CACHE_PURGE="${OPENCLAW_PIP_CACHE_PURGE:-0}"
OPENCLAW_DOCKER_BUILDER_PRUNE="${OPENCLAW_DOCKER_BUILDER_PRUNE:-0}"

echo "[cleanup] ROOT=$ROOT"

# 1) 轮转碎片：仅保留最近 N 个 trading_system_*.log（按 mtime）
if [[ -d "$LOGDIR" ]]; then
  if ls "$LOGDIR"/trading_system_*.log >/dev/null 2>&1; then
    ls -t "$LOGDIR"/trading_system_*.log 2>/dev/null | tail -n +"$((TRADING_LOG_KEEP + 1))" | xargs -r rm -f
    echo "[cleanup] trimmed trading_system_*.log to last $TRADING_LOG_KEEP files (by mtime)"
  fi

  # 2) 一次性抓取/分析残留（可安全再生成）
  rm -rf "$LOGDIR/okx_js" 2>/dev/null || true
  rm -f "$LOGDIR/okx_eth_swap_page.html" "$LOGDIR/okx_js_analysis.txt" "$LOGDIR/okx_js_urls.txt" 2>/dev/null || true

  # 3) 审计：删除过久 jsonl
  if [[ -d "$LOGDIR/audit" ]]; then
    find "$LOGDIR/audit" -maxdepth 1 -type f -name 'audit_*.jsonl' -mtime +"$AUDIT_KEEP_DAYS" -print -delete 2>/dev/null || true
    echo "[cleanup] audit jsonl older than ${AUDIT_KEEP_DAYS}d removed (if any)"
  fi
fi

# 4) 源码树 Python 缓存；可选清理 venv 内 __pycache__（不占多少空间但减少文件数）
find "$ROOT/src" "$ROOT/tests" -type d -name __pycache__ -print0 2>/dev/null | xargs -0 rm -rf 2>/dev/null || true
find "$ROOT/src" "$ROOT/tests" -type f -name '*.pyc' -delete 2>/dev/null || true
if [[ -d "$ROOT/venv" ]]; then
  find "$ROOT/venv" -type d -name __pycache__ -print0 2>/dev/null | xargs -0 rm -rf 2>/dev/null || true
fi
echo "[cleanup] __pycache__ / *.pyc under src tests (and venv) cleared"

# 4b) 重复 .venv：文档与 setup 以 venv/ 为准
if [[ "$OPENCLAW_REMOVE_DOTVENV" == "1" && -d "$ROOT/venv" && -d "$ROOT/.venv" ]]; then
  rm -rf "$ROOT/.venv"
  echo "[cleanup] removed duplicate .venv/ (kept venv/)"
fi

# 4c) 测试专用虚拟环境（全量测试脚本会重建）
if [[ "$OPENCLAW_REMOVE_TEST_VENV" == "1" && -d "$ROOT/.venv_test" ]]; then
  rm -rf "$ROOT/.venv_test"
  echo "[cleanup] removed .venv_test/ (recreate: ./scripts/run_full_test_suite.sh)"
fi

# 4d) pip 下载缓存（当前用户）
if [[ "$OPENCLAW_PIP_CACHE_PURGE" == "1" ]]; then
  if command -v pip >/dev/null 2>&1; then
    pip cache purge 2>/dev/null || python3 -m pip cache purge 2>/dev/null || true
    echo "[cleanup] pip cache purge attempted"
  fi
fi

# 4e) Docker buildkit 悬空缓存（不删在用镜像）
if [[ "$OPENCLAW_DOCKER_BUILDER_PRUNE" == "1" ]] && command -v docker >/dev/null 2>&1; then
  docker builder prune -f 2>/dev/null || true
  echo "[cleanup] docker builder prune -f done"
fi

# 5) 可选：压缩超大 app.log（>80MB 时 gzip 归档一份并截断）
APP_LOG="$LOGDIR/app.log"
if [[ -f "$APP_LOG" ]]; then
  sz=$(stat -c%s "$APP_LOG" 2>/dev/null || stat -f%z "$APP_LOG" 2>/dev/null || echo 0)
  if ((sz > 83886080)); then
    ts=$(date +%Y%m%d_%H%M%S)
    gzip -c "$APP_LOG" >"$LOGDIR/app.log.$ts.gz" || true
    : >"$APP_LOG"
    echo "[cleanup] rotated large app.log -> app.log.$ts.gz"
  fi
fi

echo "[cleanup] done. Disk:"
df -h "$ROOT" | tail -1 || true
