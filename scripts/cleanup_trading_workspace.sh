#!/usr/bin/env bash
# 交易环境维护：清理旧轮转日志、巡检/监控产物、抓取残留、源码 __pycache__、重复/测试虚拟环境、构建缓存。
# 不删除：当前 app.log、最近审计、backups/、data/ 内业务数据、frontend/node_modules、openclaw-trading.pid。
# 环境变量：
#   OPENCLAW_REMOVE_DOTVENV=1  若存在 venv/ 则删除重复的 .venv/（与 setup_environment / DEVELOPMENT 一致）
#   OPENCLAW_REMOVE_TEST_VENV=1 删除 .venv_test/（可由 run_full_test_suite.sh 再生）
#   OPENCLAW_PIP_CACHE_PURGE=1   对当前用户执行 pip cache purge
#   HEALTH_LOG_KEEP_DAYS=14      删除 logs/health 下超过天数的历史日志
#   LIVE_MONITOR_KEEP_DAYS=7     删除 runtime/live_stability_monitor.* 历史产物
#   REALTIME_WATCH_MAX_MB=512    runtime/realtime_watch.jsonl 超过阈值时 gzip 归档并截断
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOGDIR="$ROOT/logs"
AUDIT_KEEP_DAYS="${AUDIT_KEEP_DAYS:-14}"
TRADING_LOG_KEEP="${TRADING_LOG_KEEP:-12}"
OPENCLAW_REMOVE_DOTVENV="${OPENCLAW_REMOVE_DOTVENV:-0}"
OPENCLAW_REMOVE_TEST_VENV="${OPENCLAW_REMOVE_TEST_VENV:-0}"
OPENCLAW_PIP_CACHE_PURGE="${OPENCLAW_PIP_CACHE_PURGE:-0}"
HEALTH_LOG_KEEP_DAYS="${HEALTH_LOG_KEEP_DAYS:-14}"
LIVE_MONITOR_KEEP_DAYS="${LIVE_MONITOR_KEEP_DAYS:-7}"
REALTIME_WATCH_MAX_MB="${REALTIME_WATCH_MAX_MB:-512}"
RUNTIME_DIR="$ROOT/runtime"

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

  # 3b) health suite logs
  if [[ -d "$LOGDIR/health" ]]; then
    find "$LOGDIR/health" -maxdepth 1 -type f \( -name 'full_system_audit_*.log' -o -name 'live_stability_monitor_*.log' \) -mtime +"$HEALTH_LOG_KEEP_DAYS" -print -delete 2>/dev/null || true
    echo "[cleanup] health logs older than ${HEALTH_LOG_KEEP_DAYS}d removed (if any)"
  fi
fi

# 3c) runtime monitor artifacts
if [[ -d "$RUNTIME_DIR" ]]; then
  find "$RUNTIME_DIR" -maxdepth 1 -type f \( -name 'live_stability_monitor.*.jsonl' -o -name 'live_stability_monitor.*.summary.json' \) -mtime +"$LIVE_MONITOR_KEEP_DAYS" -print -delete 2>/dev/null || true
  echo "[cleanup] live stability monitor artifacts older than ${LIVE_MONITOR_KEEP_DAYS}d removed (if any)"

  # large continuous watch file: keep one compressed archive then truncate current file
  REALTIME_WATCH="$RUNTIME_DIR/realtime_watch.jsonl"
  if [[ -f "$REALTIME_WATCH" ]]; then
    max_bytes=$((REALTIME_WATCH_MAX_MB * 1024 * 1024))
    sz=$(stat -c%s "$REALTIME_WATCH" 2>/dev/null || stat -f%z "$REALTIME_WATCH" 2>/dev/null || echo 0)
    if ((sz > max_bytes)); then
      ts=$(date +%Y%m%d_%H%M%S)
      gzip -c "$REALTIME_WATCH" >"$RUNTIME_DIR/realtime_watch.jsonl.$ts.gz" || true
      : >"$REALTIME_WATCH"
      echo "[cleanup] rotated large realtime_watch.jsonl -> realtime_watch.jsonl.$ts.gz"
    fi
  fi

  if ls "$RUNTIME_DIR"/realtime_watch.jsonl.*.gz >/dev/null 2>&1; then
    find "$RUNTIME_DIR" -maxdepth 1 -type f -name 'realtime_watch.jsonl.*.gz' -mtime +"$LIVE_MONITOR_KEEP_DAYS" -print -delete 2>/dev/null || true
    echo "[cleanup] archived realtime_watch gzip older than ${LIVE_MONITOR_KEEP_DAYS}d removed (if any)"
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
