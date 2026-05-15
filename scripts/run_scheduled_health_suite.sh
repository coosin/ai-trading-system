#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
LOG_DIR="${ROOT}/logs/health"
RUNTIME_DIR="${ROOT}/runtime"
MODE="${1:-audit}"
TS="$(date +%Y%m%d_%H%M%S)"

mkdir -p "${LOG_DIR}" "${RUNTIME_DIR}"

if [[ ! -x "${PY}" ]]; then
  echo "ERROR: missing venv python at ${PY}" >&2
  exit 1
fi

case "${MODE}" in
  audit)
    AUDIT_LOG="${LOG_DIR}/full_system_audit_${TS}.log"
    set +e
    "${PY}" "${ROOT}/scripts/full_system_audit.py" > "${AUDIT_LOG}" 2>&1
    RC=$?
    set -e
    "${PY}" "${ROOT}/scripts/health_suite_summary.py" >/dev/null 2>&1 || true
    "${PY}" "${ROOT}/scripts/health_suite_status.py" >/dev/null 2>&1 || true
    exit "${RC}"
    ;;
  monitor)
    DURATION_MIN="${OPENCLAW_STABILITY_MONITOR_DURATION_MIN:-60}"
    INTERVAL_SEC="${OPENCLAW_STABILITY_MONITOR_INTERVAL_SEC:-30}"
    MONITOR_LOG="${LOG_DIR}/live_stability_monitor_${TS}.log"
    set +e
    "${PY}" "${ROOT}/scripts/live_stability_monitor.py" \
      --duration-min "${DURATION_MIN}" \
      --interval-sec "${INTERVAL_SEC}" \
      --out "${RUNTIME_DIR}/live_stability_monitor.${TS}.jsonl" \
      --summary-out "${RUNTIME_DIR}/live_stability_monitor.${TS}.summary.json" \
      > "${MONITOR_LOG}" 2>&1
    RC=$?
    set -e
    "${PY}" "${ROOT}/scripts/health_suite_summary.py" >/dev/null 2>&1 || true
    "${PY}" "${ROOT}/scripts/health_suite_status.py" >/dev/null 2>&1 || true
    exit "${RC}"
    ;;
  *)
    echo "Usage: $0 [audit|monitor]" >&2
    exit 2
    ;;
esac
