# 系统架构（已迁移）

架构、模块边界、配置与 API 的**正式说明**见：

**[docs/ENGINEERING.md](./docs/ENGINEERING.md)**

运维与部署见 **[docs/OPERATIONS.md](./docs/OPERATIONS.md)**，文档索引见 **[docs/README.md](./docs/README.md)**。

---

## 2026-05 交易真值同步与分账（入口索引）

近期对“系统记录 vs 交易所事实不一致”的修复与架构收敛点：

- **执行脊柱**：`ExecutionGateway`（统一开平仓审计与回填入口）
  - 平仓后真值回填：`src/modules/core/execution_gateway.py` → `_enrich_close_result_with_exchange_fills`
- **交易所成交明细**：`OKXExchange`（OKX `/trade/fills`）
  - `src/modules/exchanges/okx.py` → `get_swap_fills_for_order` / `get_recent_fills`
- **事实账本（分账）**：`src/modules/core/exchange_sync_ledger.py`
  - 输出：`logs/exchange_sync/exchange_truth.jsonl`
- **全自动同步线程**：`src/modules/main_controller.py` → `_auto_exchange_sync_worker`
  - 周期同步余额/持仓
  - 周期回填近期平仓真值（pnl/fee/price）

对账与排障入口：

- API：`docs/API_REFERENCE.md`（`/api/v1/trades/reconcile`、`/api/v1/trades/reconcile/report`）
- 排障：`docs/TRADING_DEBUG_PLAYBOOK.md`（分账原则与排障优先级）
