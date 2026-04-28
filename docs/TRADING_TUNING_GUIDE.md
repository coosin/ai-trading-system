# 交易开平仓/止盈止损 — 统一调参与验收指南

本页用于回答两个问题：

- **开/平仓与 SLTP 的逻辑到底在哪些模块、哪些门控条件？**
- **要调参时，应该改哪个配置入口（并如何验证已生效）？**

> 权威验证接口：`GET /api/v1/modules/commander/trading-diagnosis`

---

## 1) 你应该修改的“唯一入口/核心入口”

### 1.1 单币种/持仓数/加仓分层（唯一推荐入口）

配置位置：`config/config.yaml` → `trading.position_limits`

- `symbol_max_margin_ratio`：**每一笔开仓**（包括第2/3/4笔加仓）单笔最大保证金占用（口径=available），默认 `0.2`。
- `max_same_direction_positions`：同向持仓数上限（long/short 分别计数）。
- `max_positions_oneway`：单向模式总持仓上限。
- `max_positions_hedge`：双向对冲并存时总持仓上限。
- `hard_max_positions`：最终硬上限（任何路径不得突破）。
- `scale_in_min_confidence_2/3/4`：同向第2/3/4笔（加仓）置信度门槛（例：`0.77/0.82/0.87`）。

验证：`trading-diagnosis.data.position_limits_snapshot`。

---

### 1.2 AI 主决策（ai_core）开仓门控（关键）

门控由 `AICoreDecisionEngine` 执行，主要阈值来自：

- 运行态门控段：`ai_core_runtime.*`
- 频率档位（balanced/conservative/aggressive）会覆盖部分门控参数

你最常调的开仓门槛：

- `min_confidence_to_trade`：交易最低置信度
- `ai_core_min_confidence_to_open`：开仓专用最低置信度
- `min_rr_to_trade`：最低盈亏比（合成 RR）
- `max_spread_bps_to_trade`：点差门控
- `min_data_quality_to_trade`：数据质量门控
- `analysis_hard_gate_for_open`：开仓必须有可用分析结果（质量/置信/降级状态）
- `analysis_min_confidence_for_open`：分析层最小置信门槛（与决策置信门槛互补）
- `analysis_require_not_degraded_for_open`：是否拒绝降级数据路径开仓
- `loss_streak_cooldown_*`：连续亏损冷却（降低震荡期追单）
- `edge_after_cost_guard_*`：扣成本后的净边际收益门控

验证：

- `GET /api/v1/modules/ai/frequency-profile`：看当前档位与 `min_confidence_to_trade` 等核心门槛。
- `GET /api/v1/modules/commander/trading-diagnosis`：看 `ai_core.execution_guards.config` + `stats`（被哪些门控拦截）。

### 1.2.1 杠杆自适应（20~100，默认30）

主配置入口：`config/config.yaml` → `trading.contract`

- `leverage_min`: `20`
- `default_leverage`: `30`
- `leverage_max`: `100`
- `leverage_curve[]`: 分段曲线（`atr_gte` + `leverage`），按阈值从高到低匹配

执行逻辑：

- 开仓时在 `[leverage_min, leverage_max]` 区间内按市场波动与置信度自适应调整；
- 采用分段杠杆曲线（高波动降杠杆、低波动升杠杆），并以 `default_leverage` 作为中枢锚点；
- `default_leverage` 作为基准，不会突破上下限。

推荐曲线示例（已作为默认）：

- `atr_pct_1h >= 0.06` -> `20x`
- `0.04` -> `24x`
- `0.03` -> `28x`
- `0.02` -> `32x`
- `0.015` -> `36x`
- `0.01` -> `45x`
- `0.006` -> `60x`
- `< 0.006` -> `75x`

---

### 1.3 主动扫描自动开仓（proactive_scanner）

配置位置：`config/config.yaml` → `proactive_scanner.*`

关键降频阀门（经常导致“最近几乎不开仓”）：

- `proactive_execute_min_confidence`：扫描器自动执行的最低置信度
- `proactive_global_open_max_per_10m / per_hour`：全局开仓预算（防止短时间开太多耗尽保证金）
- `proactive_allow_scale_in`：是否允许同向加仓（默认 false）
- `proactive_stop_loss_cooldown_sec`：止损后冷却（避免止损后立即再开）
- `scanner_opportunity_gate.*`：实时数据预检（点差/滑点/入场偏差/风险收益等）

验证：`trading-diagnosis.data.execution_gateway` + 日志中的 proactive_ai 评估/跳过原因。

### 1.3.1 行情预热（降低实时查询超时）

配置位置：`config/config.yaml` → `market_intelligence.*`

- `prewarm_enabled`: 是否启用后台预热
- `prewarm_interval_sec`: 预热周期
- `prewarm_fast_interval_sec`: 快通道预热周期（ticker/轻量视图）
- `prewarm_full_every_n_fast`: 每 N 次快通道执行 1 次全量预热
- `prewarm_max_symbols`: 每轮最大预热标的数
- `prewarm_batch_size`: 并发预热批大小
- `prewarm_slow_symbol_cooldown_sec`: 慢标的冷却窗口（避免拖慢全局）
- `prewarm_slow_latency_ms`: 判定慢标的的延迟阈值
- `prewarm_timeout_cooldown_sec`: 超时标的冷却重试窗口

说明：
- 预热会后台拉取完整 `symbol_view`（含 snapshot），提升 `quality_score/atr` 等字段命中率；
- 支持“快/慢分层预热 + 慢标的隔离调度”，减少个别网络异常标的拖累整体缓存；
- 可明显降低“请求时才拉数据”导致的 `symbol_view_timeout_degraded`。

接口调用建议：

- 对外展示/运维面板优先用 `GET /api/v1/market/symbol/{symbol}?include_snapshot=true`：
  - 首次可能返回 `symbol_view_fastpath_refreshing`（warming stub），但响应毫秒级；
  - 后续会变为 `symbol_view_cached_refreshing`（缓存命中 + 后台刷新）。

统一分析链路建议（生产推荐）：

- `proactive_auto_execute_opportunities: false`（扫描器只发现机会，不直连开仓）
- 扫描机会先进入统一分析层，再由 `ai_core` 决定是否开仓
- 仅保留人工 `manual` 干预接口与 SLTP 风控平仓直达权限

---

### 1.4 止盈止损（stop_loss_take_profit）

配置位置：`config/config.yaml` → `stop_loss_take_profit.*`

当前主策略：**移动止损/分层锁盈**（`trailing_only_mode: true`）。

常用调参：

- `initial_trailing_offset`：初始移动止损距离
- `profit_tier2_pnl_threshold` / `tier2_trailing_offset`：盈利达到阈值后收紧
- `enable_breakeven` / `breakeven_trigger`：保本锁定
- `profit_protect_*`：锁盈加速器
- `profit_protect_regime_overrides.*`：高波动/低流动性时的倍率调整

验证：

- `GET /api/v1/modules/commander/trading-diagnosis` → `data.sltp`
- `GET /api/v1/modules/stop-loss/stats`
- `scripts/sltp_sr_simtest.py`（离线验收 SR 触发与保本逻辑）

---

## 2) 交易链路（开仓/平仓到底怎么走）

系统执行脊柱：`ExecutionGateway`（S1 单写入者策略）

- 开仓：`ai_core`（或经配置开启的双控）→ `ExecutionGateway.open_swap` → `OKXExchange.open_swap_position`
- 平仓：主策略/SLTP/人工三入口 → `ExecutionGateway.close_swap` → `OKXExchange.close_swap_position`

为什么要走 ExecutionGateway：

- 统一做写入权限（single_write_owner）与审计
- 统一做失败归因（error_code）、重试/冷却、post-check 等

验证：

- `trading-diagnosis.data.execution_gateway.recent_events`
- `trading-diagnosis.data.execution_attribution.top_reasons`

---

## 3) 为什么“最近开仓频率下降很明显”

常见的“叠加降频”组合：

- 扫描器：`proactive_execute_min_confidence` 较高 + `global_open_budget` 较小
- ai_core：`min_confidence_to_trade` + `min_rr_to_trade` + 点差门控
- 加仓：`proactive_allow_scale_in=false` + `position_limits.scale_in_min_confidence_*`（同向第2/3/4笔更严格）
- 止损：`proactive_stop_loss_cooldown_sec` 导致同标的 30 分钟不再开

建议用 `trading-diagnosis.data.ai_core.execution_guards.stats` 看最常触发的拒绝原因。

---

## 4) AI 自我优化/自动调整是否在跑（如何验收）

学习引擎：`AILearningEngine`

- 运行态验证：`trading-diagnosis.data.ai_learning_engine.running == true`
- 有效性验证：`total_lessons` 与 `reports_generated` 应随新增真实平仓样本持续增长（不是只看 running）
- 闭环验证（需要写接口 token）：调用
  - `POST /api/v1/modules/commander/learning/seed-and-run`
  - 再看 `trading-diagnosis.data.ai_learning_engine.total_lessons/reports_generated` 是否递增

注意：`seed-and-run` 是写接口，默认会返回 `401`（没有 token）或 `403`（角色不够），属于正常保护行为。

若你只在本机/内网对接，可启用 `api.auth_bypass_cidrs`（默认放行 `127.0.0.1/32`、`::1/128`），使该写接口在白名单来源无需 token。

