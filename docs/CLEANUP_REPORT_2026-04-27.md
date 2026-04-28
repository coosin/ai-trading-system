# Cleanup Report (2026-04-27)

## Scope

Aggressive full-chain cleanup and consolidation:
- core lifecycle fixes
- API surface pruning (removed compatibility aliases/mirrors)
- script de-duplication and dangerous script removal
- docs synchronization to new canonical endpoints

## Core Fixes

- `src/modules/core/ai_trading_engine.py`
  - `start()` now restores `self._running = True` before starting loops.
- `src/modules/core/ai_learning_engine.py`
  - Removed misplaced `initialize()` method from `LessonType` enum.
  - `stop()` now awaits cancelled learning task for graceful shutdown.

## API Surface Changes

- `src/modules/api/server.py`
  - Removed root auth aliases (`/auth/*`), kept `/api/v1/auth/*`.
  - Removed deprecated trade-history aliases:
    - `/api/v1/trading/history`
    - `/api/v1/trade/history`
  - Removed deprecated data-fusion analyze aliases:
    - `/api/v1/data-fusion/analyze`
    - `/api/v1/data-fusion/analyze/{symbol}`
  - Removed commander mirror forwarding endpoints:
    - `/api/v1/commander`
    - `/api/v1/commander/{path}`
    - `/api/v1/commander/_audit`
  - Consolidated health/status to canonical v1 system endpoints:
    - `/api/v1/system/health`
    - `/api/v1/system/status`

## Removed API Modules (stale / unused)

- src/modules/api/enhanced_api.py
- src/modules/api/risk_api.py
- src/modules/api/backtest_api.py

## Script Consolidation

### New canonical entrypoint
- `scripts/verify.py`

### Retained key scripts
- `scripts/trading_exec_fullcheck.py`
- `scripts/sltp_sr_simtest.py`
- `scripts/production_network_baseline.py`
- `scripts/network_connectivity_smoke.py`
- `scripts/proxy_mode_network_benchmark.py`
- `scripts/startup_acceptance.py`

### Removed scripts (duplicate/legacy/dangerous)

- Python:
  - `analyze_module_functions.py`
  - `check_all_modules.py`
  - `check_module_connections.py`
  - `check_module_duplicates.py`
  - `clean_system.py`
  - `code_cleaner.py`
  - `optimize_system.py`
  - `memory_inventory_archive.py`
  - `memory_restore_optimize.py`
  - `memory_unify_migrate.py`
  - `migrate_sltp_legacy_pending.py`
  - `s1_autoverify_all.py`
  - `s1_smoke_test.py`
  - `trading_fullcheck.py`
  - `probe_report_to_tg.py`
  - `okx_hft_tuning_probe.py`
  - `one_click_upgrade_pipeline.py`
  - `full_system_integration_check.py`
  - `continuous_system_probe.py`
  - `upgrade_regression_check.py`
  - `subscription_updater.py`
- Shell:
  - `health_check.sh`
  - `daily_backup.sh`
  - `update_clash_subscriptions.sh`
  - `go_live_acceptance.sh`
  - `verify_trading_chain.sh`
  - `smoke_local_network.sh`
  - `control_plane_autoheal.sh`

## Documentation Sync

- Updated `docs/API_REFERENCE.md`:
  - removed deleted endpoint references
  - removed legacy auth/root and commander mirror entries
  - updated migration notes to canonical endpoints
- Added `scripts/README.md` with active inventory and retained operational scripts.

## Validation Notes

- Local static checks/lints passed for modified files.
- Runtime OpenAPI regeneration could not run in this environment due missing `fastapi` dependency in current interpreter.
- `scripts/trading_exec_fullcheck.py` remains resilient when API service is offline and still validates local SLTP/SR sim path.

