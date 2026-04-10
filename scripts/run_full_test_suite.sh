#!/usr/bin/env bash
# 全量测试：安装依赖（轻量集合）后运行 pytest + e2e 烟测。
# 用法：在项目根目录执行  ./scripts/run_full_test_suite.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VENV="${VENV:-.venv_test}"

if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1090
source "$VENV/bin/activate"
python -m pip install -q -U pip wheel

# 与单元测试收集/运行相关的最小依赖（避免 requirements.txt 中 ta-lib 等阻塞 CI）
python -m pip install -q \
  "pytest>=7.4" "pytest-asyncio>=0.21" "pytest-cov>=4.1" \
  "httpx>=0.25" "aiohttp>=3.9" "aiofiles>=23" \
  "fastapi>=0.104" "uvicorn[standard]>=0.24" \
  "pydantic>=2" "pyyaml>=6" \
  "pandas>=2" "numpy>=1.24" "scipy>=1.10" "scikit-learn>=1.3" \
  "sqlalchemy>=2" "aiosqlite>=0.19" \
  "redis>=5" "psutil>=5.9" "prometheus-client>=0.19" "structlog>=23" \
  "cryptography>=41" "python-dotenv>=1" "websockets>=11" \
  "python-jose[cryptography]>=3.3" "passlib[bcrypt]>=1.7" \
  "python-multipart>=0.0.6" "python-telegram-bot>=20" \
  "ccxt>=4" || true

export PYTEST_ADDOPTS="--tb=short -q"
# 关闭 coverage 全量扫描以加快「完整测试」迭代；需要覆盖率时去掉下行
python -m pytest tests/ --no-cov "$@"
echo "✅ pytest 完成（若需覆盖率：PYTEST_ADDOPTS='' python -m pytest tests/）"
