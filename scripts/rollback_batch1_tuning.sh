#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/cool/ai-trading-system"
CFG="${ROOT}/config/config.yaml"
BAK="${ROOT}/config/config.yaml.bak.batch1-20260504-2356"

if [[ ! -f "${BAK}" ]]; then
  echo "ERROR: backup not found: ${BAK}" >&2
  exit 1
fi

cp "${BAK}" "${CFG}"
echo "Restored config from ${BAK}"
echo "Restart service to apply:"
echo "  bash ${ROOT}/scripts/stop-openclaw-trading.sh && bash ${ROOT}/scripts/start-openclaw-trading.sh start"
