# 交易链路调试手册（开平仓专项）

本文是实盘调试与联调标准手册，覆盖：

- 开仓/平仓主链路
- 关键参数调整入口
- 诊断接口与排障步骤
- 常见故障与修复顺序

> 推荐先执行：`make verify-trading`、`make verify-trading-gates`

---

## 1. 开平仓标准链路

- **主决策链**：`AICoreDecisionEngine` -> `ExecutionGateway`
- **兼容链**：`AITradingEngine`（人工/兼容入口）-> `ExecutionGateway`
- **实际下单**：`OKXExchange.open_swap_position` / `close_swap_position`
- **风控与退出**：`stop_loss_take_profit`、`AccountRiskMonitor`
- **对账保护**：`ExecutionReconciler`、`ReconciliationProtectionManager`
- **决策契约**：`DecisionEnvelope`（`decision_contract`）在执行前统一校验 `symbol/action/side/quantity/leverage/strategy_id`

核心原则：

- 所有真实开平仓写入都应可在 `ExecutionGateway` 审计到。
- 拒单必须可解释（置信度、RR、spread、depth、funding、OI、保护锁等）。

---

## 2. 开仓参数调整（重点）

配置主入口：`config/config.yaml`

### 2.1 ai_core 开仓门控（生产主路径）

路径：`ai_core_runtime.*`（运行态覆盖）与 `AICoreDecisionEngine` 默认配置

关键项：

- `min_confidence_to_trade`
- `ai_core_min_confidence_to_open`
- `min_data_quality_to_trade`
- `min_rr_to_trade`
- `max_spread_bps_to_trade`
- `max_abs_depth_imbalance_to_trade`
- `microstructure_enable_funding_oi_gates`
- `microstructure_max_abs_funding_rate_to_trade`
- `microstructure_min_open_interest_to_trade`

### 2.2 ai_trading 兼容开仓门控

路径：`ai_trading.ai_config.*`

关键项：

- `enable_microstructure_open_gates`
- `microstructure_max_spread_bps`
- `microstructure_max_abs_depth_imbalance`
- `microstructure_max_abs_funding_rate`
- `microstructure_min_open_interest`

### 2.3 持仓与加仓限制

路径：`trading.position_limits.*`

- `symbol_max_margin_ratio`
- `max_same_direction_positions`
- `max_positions_oneway`
- `max_positions_hedge`
- `hard_max_positions`
- `scale_in_min_confidence_2/3/4`

---

## 3. 平仓参数调整（重点）

路径：`stop_loss_take_profit.*`

- `trailing_only_mode`
- `initial_trailing_offset`
- `tier2_trailing_offset`
- `enable_breakeven`
- `breakeven_trigger`
- `profit_protect_*`

平仓验证：

- `GET /api/v1/modules/commander/trading-diagnosis` -> `data.sltp`
- `GET /api/v1/modules/stop-loss/stats`
- `python3 scripts/sltp_sr_simtest.py`

---

## 4. 调试接口与观察点

### 4.1 一键总览

- `GET /api/v1/modules/commander/trading-diagnosis`

重点字段：

- `data.execution_gateway`
- `data.execution_attribution`
- `data.execution_reconciliation`
- `data.execution_reconciliation_protection`
- `data.execution_safe_recovery`
- `data.analysis_pipeline_assessment.market_analysis`
- `data.decision_contract_integrity`
- `data.strategy_distribution_30d`

### 4.2 决策轨迹复盘

- `GET /api/v1/modules/commander/decision-traces`
- `GET /api/v1/modules/commander/decision-traces/{trace_id}`

### 4.3 学习闭环联调

- `POST /api/v1/modules/commander/learning/seed-and-run`

注意：该接口不会下实单，但会写学习状态与运行态覆盖。

---

## 4.4 交易所真值同步（自动）与对账排障（2026-05-06）

### 4.4.1 为什么要“分账”

- **`app.log`**：记录系统行为（决策、门控、下单尝试、异常），用于排障。
- **`exchange_truth.jsonl`**：记录交易所侧事实回填（pnl/fee/均价、fills 数量、是否估算），用于对账与收益口径收敛。

账本文件：

- `logs/exchange_sync/exchange_truth.jsonl`

### 4.4.2 对账接口（快速定位不一致）

- `GET /api/v1/trades/reconcile`
- `GET /api/v1/trades/reconcile/report`

排障优先级建议：

1. 先看 `report.summary.missing_on_exchange`（系统有记录但交易所未查到 fills）
2. 再看 `details[].match_method=time_window`（说明 order_id 链路不完整或历史样本缺失）
3. 最后看 `abs(pnl_delta)` 最大的几笔，逐笔核对交易所成交明细

超时与降级（2026-05-07 更新）：

- 当 OKX 不可达（例如 `SSLCertVerificationError` / 代理 MITM 根证书缺失）时，对账端点可能在拉取 fills 时耗时较长。
- `reconcile/report` 支持 `timeout_sec`（默认 8 秒），建议值守脚本显式设置：
  - `GET /api/v1/trades/reconcile/report?days=7&top_n=20&timeout_sec=6`
- 若触发超时会返回 `message=trade_reconcile_report_timeout`，此时应优先修复网络/TLS，再做收益口径核对。

---

## 5. 标准排障流程

1. **先看总诊断**：`trading-diagnosis`
2. **看拒单主因**：`execution_attribution.top_reasons`
2.1 **看契约完整性**：`decision_contract_integrity.strategy_coverage/trace_coverage`
3. **看市场样本完整度**：`market_analysis.degraded_ratio`、`samples[]` 的 spread/depth/funding/OI
4. **看对账保护是否拦截**：`execution_reconciliation_protection`
5. **看单条轨迹**：`decision-traces/{trace_id}`
6. **复测**：`make verify-trading` + `make verify-trading-gates`

---

## 6. 常见问题速查

- **问题：开仓明显变少**
  - 排查：`min_confidence`、`min_rr`、`max_spread`、`funding/OI` 门控是否过严
- **问题：最近 3 小时“看起来大量亏损离场”**
  - 先排查：`/api/v1/trades` 中是否混入 `metadata.source=db_bootstrap`（补录/种子样本）；该来源不应用于实盘离场归因
  - 再排查：真实执行样本（`trade.fill`/`trade.position`）中的 `trace_id + strategy_id + sltp_reason`
- **问题：诊断偶发超时**
  - 排查：`scripts/trading_exec_fullcheck.py` 是否启用重试；服务是否单实例运行
- **问题：pytest 收集阶段报 `ModuleNotFoundError: No module named 'src'`**
  - 说明：pytest 9 在不同 import 模式下，repo root 可能未被稳定加入 `sys.path`
  - 处理：确保测试入口包含 `tests/conftest.py` 的路径注入（已在仓库默认提供）；或直接用 `make test` 从仓库根目录运行
- **问题：诊断里 quality 低但行情看起来正常**
  - 排查：`market_analysis.samples[].provenance`、`quality_score` 与 `data_source_hub` collector 健康
- **问题：本地与交易所持仓不一致**
  - 排查：`execution_reconciliation.summary` 与 `safe_recovery` 动作

---

## 6.1 失败归因口径（2026-05-06）

- `ALREADY_CLOSED_NO_POSITION`（如 OKX `51169`）已归类为 benign failure；
- 查看 `trading-diagnosis.data.execution_attribution` 时，应同时看：
  - `failures_in_window`（可行动失败）
  - `benign_failures_in_window`（终态噪声）
  - `benign_failure_codes`（当前含 `ALREADY_CLOSED_NO_POSITION`）

---

## 7. 建议值（起步）

- `microstructure_max_spread_bps`: 10~15
- `microstructure_max_abs_depth_imbalance`: 0.85~0.93
- `microstructure_max_abs_funding_rate`: 0.0008~0.0015
- `microstructure_min_open_interest`: 按品种分层（主流币可从 1e6 起）

建议每次只调整 1~2 项，并用 `decision-traces` 观察至少 20~50 条样本后再继续收紧/放宽。
