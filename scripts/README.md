# Scripts Inventory

This directory was aggressively cleaned and consolidated.

## API base URL（规范）

调用本仓库 HTTP API 的脚本应优先读取环境变量 **`OPENCLAW_API_BASE`**（其次 `ACCEPTANCE_BASE`、`BASE_URL`），与 **`src/utils/openclaw_api_client.py`** 及 **`GET /api/v1/modules/surface/registry`** 响应中的 **`api_base_env`** 一致。说明见 **`docs/API_REFERENCE.md`**（「API 基址、只读巡检链与 Surface」）与 **`docs/OPERATIONS.md`**。

## Active Scripts

- `verify.py`
  - Unified entrypoint.
  - `python3 scripts/verify.py trading --base-url http://127.0.0.1:8000`（或先 `export OPENCLAW_API_BASE=...` 再传同一基址）
  - `python3 scripts/verify.py network --check-only`
- `trading_exec_fullcheck.py`
  - End-to-end trading acceptance checks (diagnosis + SR sim + learning seed).
- `sltp_sr_simtest.py`
  - Offline SR/SLTP simulation test.
- `production_network_baseline.py`
  - Production proxy/clash baseline checks.
- `network_connectivity_smoke.py`
  - Lightweight network connectivity smoke tests.
  - Optional: `--include-api` hits `OPENCLAW_API_BASE`（经 `openclaw_api_url`）下的 `GET /api/v1/system/health`.
- `proxy_mode_network_benchmark.py`
  - Proxy mode benchmark checks.
- `startup_acceptance.py`
  - Startup acceptance checks.

## Kept Operational Shell Scripts

- `deploy_production_stack.sh`
- `run_full_test_suite.sh`
- `verify_full_stack_network.sh`
- `verify_okx_container.sh`
- `check_trading_host_health.sh`
- `cleanup_trading_workspace.sh`
- `diagnose_container_net.sh`
- `recover_trading_hostnet.sh`
- `start-openclaw-trading.sh`
- `stop-openclaw-trading.sh`
- `openclaw_auth_selfcheck.sh`

## Removed in Cleanup

- Deprecated aliases and duplicate verifiers (`trading_fullcheck.py`, `s1_*`, `full_system_integration_check.py`, etc.).
- One-off migration/archive scripts (`memory_*`, `migrate_sltp_legacy_pending.py`).
- Dangerous code mutators (`clean_system.py`, `code_cleaner.py`, `optimize_system.py`).
- Old-path or secret-bearing scripts (`health_check.sh`, `daily_backup.sh`, `update_clash_subscriptions.sh`).

