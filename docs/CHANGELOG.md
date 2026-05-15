# 变更记录

## 2026-05-13 — API 发现、只读链路与脚本基址文档收口

- **代码（此前已合入，本节为文档对齐说明）**
  - `src/modules/api/route_catalog.py`：`read_pipeline_spec()` 推荐只读巡检顺序；`extended_core_routes()` 与 surface **`catalog`** 去重合并。
  - `src/modules/api/module_surface.py`：`GET /api/v1/modules/surface/registry` 增加 **`read_pipeline`**、**`api_base_env`**；`CONTRACT_VERSION` 更新。
  - `src/utils/openclaw_api_client.py`：基址 **`OPENCLAW_API_BASE` > `ACCEPTANCE_BASE` > `BASE_URL` > 默认**。
  - 脚本：`startup_acceptance.py`、`prod_stability_check.py`、`network_connectivity_smoke.py`（`--include-api`）、`system_probe_daily_summary.py` 等与上述基址一致。
  - 测试：`tests/unit/test_route_catalog.py`。

- **文档**
  - 更新 `docs/API_REFERENCE.md`、`docs/OPERATIONS.md`、`docs/ENGINEERING.md`、`docs/DEVELOPMENT.md`、`docs/DAILY_HOSTING_ACCEPTANCE.md`、`docs/README.md`、`scripts/README.md`、根目录 `README.md`：统一说明环境变量优先级、`surface/registry` 机器可读字段与只读链路规范。
  - `.env.example`：补充 `OPENCLAW_API_BASE` 注释与兼容变量说明。

## 2026-05-12 — Astron 主模型收口与 OKX 路由回退修正

- **LLM 运行态对齐：**
  - `config/config.yaml`
    - `ai_trading.ai_config.model_id` 从 `qianfan-code-latest` 改为 `astron-code-latest`
  - 目的：
    - 修复默认模型已切换，但交易引擎运行态诊断仍显示旧模型的配置漂移

- **OKX 路由修正：**
  - `/etc/mihomo/config.yaml`
    - `OKX` 组从 `GCP-HTTP -> GCP-SS -> AUTO -> DIRECT` 收敛为 `AUTO -> DIRECT`
  - 原因：
    - 本地 `127.0.0.1:17892/17893` 当前无监听
    - `mihomo` 日志持续出现 `connect: connection refused` 与 `failed to dial WebSocket: EOF`
    - 直连 `https://www.okx.com/api/v5/public/time` 超时，但经 `http://127.0.0.1:7890` 可达

- **运行结论：**
  - 应用进程仍可正常启动与运行
  - OKX 公共接口可达，系统健康接口恢复为 `healthy`
  - 私有 REST 仍可见 `50013 Systems are busy`，当前问题已从“本地坏隧道”收敛为“上游链路或交易所侧波动”

- **OKX 私有接口减压：**
  - `src/modules/exchanges/okx.py`
    - `get_positions()` / `get_balances()` 改为“空结果也缓存”，避免空仓时反复打私有 REST
    - 增加单飞锁，压制多模块并发查询造成的请求风暴
    - 将 `50013` 视为可退避重试的“繁忙”状态，并增加短冷却窗口
  - 效果：
    - 日志形态从高密度 `ERROR` 风暴收敛为带退避的 `WARNING`
    - 系统在私有接口波动时更容易维持健康运行而不是自我放大异常

## 2026-05-12 — 主模型切换至 NVIDIA 托管 DeepSeek V4 Pro

- **背景：**
  - 原 `DeepSeek V4 Flash` 官方额度耗尽，生产链路持续返回 `402 Payment Required / Insufficient Balance`；
  - 决策引擎虽可退回规则兜底，但会显著削弱 AI 分析与生成链路。

- **本次切换：**
  - `config/config.yaml`
    - `llm.default_model` 改为 `deepseek-ai/deepseek-v4-pro`
    - 主模型 `base_url` 改为 `https://integrate.api.nvidia.com/v1`
    - `api_key_env` 改为 `NVIDIA_API_KEY`
    - 增加：
      - `top_p: 0.95`
      - `extra_body.chat_template_kwargs.thinking: false`
  - `src/modules/core/enhanced_llm_manager.py`
    - `OpenAIProvider` 增加 `top_p` 与 `extra_body` 透传能力；
    - 配置加载器支持从 YAML 注册上述字段。
  - `.env`
    - 新增 `NVIDIA_API_KEY`

- **验证结果：**
  - `GET /api/v1/ai-models/default` 已返回默认模型：
    - `deepseek-ai/deepseek-v4-pro`
  - 通过进程内最小实测调用，模型已成功返回：
    - `content=OK`

## 2026-05-11 — GCP 专线接管 OKX、独立代理变量与链路托管

- **目标：**
  - 不再让 OKX 交易链路直接依赖公共订阅节点；
  - 将 OKX REST / WS 从全局代理出口中拆出，优先走 GCP 专线；
  - 保留本地 `mihomo` 作为普通第三方流量出口，降低耦合与排障复杂度。

- **网络拓扑调整：**
  - GCP 实例 `34.21.174.74` 上启用：
    - `tinyproxy`（远端 `127.0.0.1:3128`）
    - `sing-box`（远端 `127.0.0.1:8080`，当前作为备用专线入口）
  - 本机新增 / 使用的 systemd 隧道服务：
    - `gcp-okx-http-tunnel.service`
      - 本地 `127.0.0.1:17892 -> GCP 127.0.0.1:3128`
    - `gcp-okx-ss2022-tunnel.service`
      - 本地 `127.0.0.1:17893 -> GCP 127.0.0.1:8080`
  - 说明：
    - HTTP 隧道当前是 OKX 主用链路；
    - `sing-box`/SS 链路保留为备用方案与后续进一步收敛入口。

- **本机 `mihomo` 分流收口：**
  - 更新 [`/etc/mihomo/config.yaml`](/etc/mihomo/config.yaml)：
    - 新增 `GCP-HTTP`
    - 新增 `GCP-SS`
    - `OKX` 组改为独立 `fallback`
    - 当前优先顺序：`GCP-HTTP -> GCP-SS -> AUTO -> DIRECT`
  - 目标域名：
    - `okx.com`
    - `okx.cab`

- **应用侧 OKX 独立代理支持：**
  - `src/modules/exchanges/okx.py`
    - 初始化时优先读取：
      - `OPENCLAW_OKX_HTTPS_PROXY`
      - `OPENCLAW_OKX_HTTP_PROXY`
    - 然后才回退到：
      - `OPENCLAW_HTTPS_PROXY`
      - `OPENCLAW_HTTP_PROXY`
      - `HTTPS_PROXY`
      - `HTTP_PROXY`
  - 含义：
    - 允许仅将 OKX REST / WS 指向专线；
    - LLM、新闻、Reddit、第三方行情等仍可保留原全局出口。

- **`.env` 运行约定：**
  - 新增：
    - `OPENCLAW_OKX_HTTP_PROXY=http://127.0.0.1:17892`
    - `OPENCLAW_OKX_HTTPS_PROXY=http://127.0.0.1:17892`
    - `OPENCLAW_OKX_PROXY_ONLY=1`
  - 当前语义：
    - OKX 仅走 GCP HTTP 专线；
    - 其他模块继续走全局 `7890`。

- **启动与托管：**
  - 统一使用：
    - `scripts/start-openclaw-trading.sh`
    - `scripts/stop-openclaw-trading.sh`
  - 不再依赖手工散启动进程，PID 与健康等待逻辑统一收口到脚本。

- **验证口径：**
  - 基础：
    - `curl http://127.0.0.1:8000/api/v1/system/health`
    - `bash scripts/health_check.sh`
  - 代理运行态：
    - `systemctl status gcp-okx-http-tunnel.service`
    - `systemctl status gcp-okx-ss2022-tunnel.service`
    - `curl http://127.0.0.1:9090/proxies/OKX`
  - 应用日志关键字：
    - `OKX使用环境代理: http://127.0.0.1:17892`
    - 作为“OKX 已脱离全局 7890、独立走 GCP 专线”的确认依据。

## 2026-05-10 — 满仓替换链路、同向集中度门控与机会成本诊断

- **执行门控与仓位治理：**
  - `AICoreDecisionEngine` 新增同向集中度门控 `max_same_direction_ratio`（默认 `0.7`），按“开仓后投影占比”判定是否拒绝。
  - 新增“满仓高置信替换最差仓”执行路径：
    - 当开仓在执行网关返回“风控红线/持仓数上限”时，若新信号置信度达到阈值（`replace_worst_min_confidence`），尝试先平质量最低持仓，再重试开仓。
  - 更新说明（2026-05-14）：该替换路径现已收口为 `ExecutionGateway` 单点实现，配置入口为 `ai_brain.policy.*`；`AICoreDecisionEngine` 不再读取 `replace_worst_*` 配置，也不再因“满仓 + 高置信 + 启用替换”绕过同向集中度门控。

- **止损与开仓风险参数同步：**
  - `min_confidence_to_trade` / `ai_core_min_confidence_to_open` 调整至 `0.65`，并引入 `ai_core_min_confidence_floor` 防止运行时过度放松。
  - `stop_loss_take_profit.initial_trailing_offset` 调整为 `0.025`；
    `stop_loss_take_profit.tier2_trailing_offset` 调整为 `0.018`。
  - 开仓合成风险距离支持按波动档位采用两档止损（低波动 `4%` / 高波动 `6%`）。

- **机会成本闭环：**
  - 新增被拒绝信号记录（`rejected_signal`）与 `ai_core` 内部机会成本汇总能力。
  - `GET /api/v1/modules/commander/trading-diagnosis` 新增 `opportunity_cost` 输出：
    - `rejected_total` / `evaluated`
    - `missed_win_count` / `missed_loss_count`
    - `avg_forward_return_pct`
    - `top_missed_wins`

- **ExecutionVerifier 探针开仓限频：**
  - 配置项 `trading.execution_verifier.open_symbol_cooldown_sec`（默认 `900`）：同一交易对经 Verifier 成功开仓后，在冷却时间内再次 Verifier 开仓将被拒绝。
  - 启动日志会打印 `ExecutionVerifier 配置: ... open_symbol_cooldown_sec=...`；命中冷却时打印 `VERIFIER_OPEN_COOLDOWN_SKIP`（WARNING），用于压制 `execution_verifier_open` 短时风暴（运行证据已见 DOGE/USDT 等场景）。

- **Trading Monitor：**
  - 策略绩效类 `low_win_rate` / `low_sharpe` 告警增加最小成交样本门槛与按 (策略, 告警类型) 冷却，并将 INFO 级告警改为 `logger.info`，减轻日志刷屏。

- **验证结论（运行证据）：**
  - “先平后开”替换链路已在实测中连续成功触发（风控红线 -> 平最差仓 -> 重试开仓）。
  - 同向集中度门控在 100% 同向持仓场景稳定拦截同向新开仓。
  - `trading-diagnosis.opportunity_cost` 已可稳定输出空样本与有样本两类结果。
  - Verifier 同 symbol 冷却：`app.log` 已出现 `VERIFIER_OPEN_COOLDOWN_SKIP` 与 `execution_verifier_open_symbol_cooldown` 错误回传至决策引擎。

## 2026-05-08 — 临界风险建议平仓可见性修复（close_recommendation）

- **问题现象：**
  - `critical_risk_auto_close=true` 场景下，系统已触发“建议平仓”，但在部分观察面（记忆事件/前端订阅）出现“偶发看不到”的感知。

- **根因确认（基于运行日志）：**
  - 建议事件主链路本身可达（`_on_risk_warning` -> `_recommend_close_to_main_lane`）；
  - 但 `close_recommendation_*` 与常规风险事件共用冷却去重，导致 300 秒窗口内事件写入记忆被跳过，影响可见性与复盘连续性。

- **修复内容：**
  - `AITradingEngine._save_risk_event_to_memory` 引入 `effective_cooldown`：
    - 对 `event_type == "close_recommendation"` 设为 `0`（绕过冷却）；
    - 其他风险事件保持原有冷却机制，避免噪声膨胀。
  - `AITradingEngine._recommend_close_to_main_lane` 增加直接镜像到 `TradeEventHub.publish_system_alert`：
    - `kind="risk.close_recommendation"`，
    - 保障在即时消息开关/过滤开启时，前端与事件订阅侧仍可稳定观测。

- **验证结论：**
  - `close_recommendation` 连续触发场景下，记忆事件可持续写入；
  - 事件总线与 TradeEventHub 通道均稳定分发；
  - 调试埋点已清理，仅保留功能修复逻辑。

## 2026-05-06 — 交易真值自动同步、分账与对账报告（实盘口径对齐）

- **交易所真值回填（自动化）：**
  - 平仓成功后，`ExecutionGateway` 会基于订单 `ordId` 自动拉取 OKX `fills` 并回填真实字段（`pnl/fee/average price`），优先使用 `fillPnl/fee/fillPx/fillSz` 聚合结果，避免仅靠本地估算导致系统收益与交易所不一致。
  - 新增 OKX 接口封装：
    - `OKXExchange.get_swap_fills_for_order(symbol, ord_id)`：按订单拉取成交明细
    - `OKXExchange.get_recent_fills(symbol, limit)`：按 symbol 拉取近期成交明细（用于无 `order_id` 场景的时间窗兜底）

- **交易所事实账本（与运行日志分离）：**
  - 新增 `src/modules/core/exchange_sync_ledger.py`，写入 `logs/exchange_sync/exchange_truth.jsonl`（JSON Lines，仅追加）。
  - 用途：将“交易所侧事实”（回填结果、回填来源、是否估算、fills 数量）与 `app.log` 运行日志彻底分离，便于对账与排障。

- **对账接口与一键差异报告：**
  - 新增 `GET /api/v1/trades/reconcile`：对比系统平仓记录与交易所 `fills`，输出 `pnl_delta/fee_delta/price_delta`、`match_method` 等。
  - 新增 `GET /api/v1/trades/reconcile/report`：输出摘要 + Top 偏差列表（按 `abs(pnl_delta)` / `abs(fee_delta)`）。
  - `accurate_only`/`realized_only` 过滤口径修正：真实平仓但盈亏为 0 的记录不再被误排除（以 `action=close`/`status=filled` 判定为 realized）。

- **全自动同步线程（默认启用）：**
  - `MainController` 启动时自动启动后台同步线程：周期同步账户状态（余额/持仓）+ 周期回填近期平仓真值（pnl/fee/price）。
  - 新增配置段 `exchange_auto_sync.*`（默认启用；可调 `interval_sec`、回填 lookback、每 N 轮回填一次等）。

## 2026-05-06 — ai_core 开仓门控与低波动缓趋势适配（交易频率恢复）

- **开仓门控修复：**
  - 修复 `analysis_hard_gate` 与 `TradeDecision` 字段不对齐导致的“所有开仓被拒绝”（`quality_score/confidence` 为 none）。
  - 统一将多源融合与市场情报载荷合并写入 `decision.market_analysis`，使 `analysis_hard_gate_for_open` 能正确读取 `quality_score/confidence/provenance/partial`。

- **市况识别增强：**
  - 新增/完善 `low_vol_grind`（低波动 + 缓趋势）识别与 profile overrides，避免“慢涨/慢跌”被误判为纯横盘从而过度收紧。

## 2026-05-06 — SLTP 防回吐调优与诊断口径收敛

- **执行归因与诊断可观测性：**
  - `ExecutionGateway._classify_error_code` 新增 `ALREADY_CLOSED_NO_POSITION`（识别 OKX `sCode=51169` / 无可平仓位）。
  - `GET /api/v1/modules/commander/trading-diagnosis` 的 `execution_attribution` 新增：
    - `benign_failures_in_window`
    - `benign_failure_codes`
  - `ALREADY_CLOSED_NO_POSITION` 从可行动失败中分流，避免与真实失败混淆。

- **SLTP 链路收敛：**
  - `stop_loss_take_profit` 在 close context 中统一透传 `trace_id`、`strategy_id`、`strategy_used`。
  - 对 `51169/no position` 类错误按终态处理：停止 pending-close 重试，回收本地索引，避免失败噪声膨胀。

- **参数调优（防“浮盈回吐后亏损离场”）：**
  - `stop_loss_take_profit.initial_trailing_offset`: `0.02 -> 0.016`
  - `profit_tier2_pnl_threshold`: `0.06 -> 0.02`
  - `tier2_trailing_offset`: `0.02 -> 0.012`
  - `breakeven_trigger`: `0.02 -> 0.01`
  - `profit_protect_trigger_1`: `0.02 -> 0.012`
  - `profit_protect_lock_1`: `0.004 -> 0.002`
  - `profit_protect_trigger_2`: `0.04 -> 0.025`
  - `profit_protect_lock_2`: `0.012 -> 0.008`
  - `profit_protect_tighten_factor`: `0.88 -> 0.82`
  - `layered_trailing_tp_drawdown_levels`: `[0.03/0.06/0.10]` 对应回撤阈值收紧为 `[0.008/0.014/0.02]`

- **分析口径说明：**
  - 最近窗口交易诊断需显式区分 `metadata.source=db_bootstrap` 与真实执行记录，避免将补录/种子样本误判为实盘亏损离场。

## 2026-05-05 — 决策契约化、可恢复与学习闭环升级（实盘链路收口）

- **执行链路升级：**
  - 新增 `src/modules/core/decision_contract.py`，引入 `DecisionEnvelope` 与统一校验（`symbol/action/side/quantity/leverage/strategy_id`）。
  - `AICoreDecisionEngine` 在执行前强制构建并校验契约；校验失败 fail-closed。
  - `ExecutionVerifier` open/close 路径接入契约校验并优先使用 envelope 字段。
  - `AICommandExecutor` 手动开平仓优先走 `execute_command -> execution_verifier -> execution_gateway`，统一策略归因字段透传。

- **稳定性升级：**
  - 新增 `src/modules/core/ai_core_checkpoint_store.py`，支持 AI Core 运行态 checkpoint（重启恢复关键门控/档位状态）。
  - `AICoreDecisionEngine` 启停与循环周期保存/加载 checkpoint。

- **学习闭环升级：**
  - `TradeHistoryService` 新增 `run_outcome_reflection()`，实现 pending->realized->reflection 自动闭环（去重索引持久化）。
  - `AICoreDecisionEngine` 策略管理循环接入 outcome reflection 自动运行。

- **统计与诊断升级：**
  - `TradeHistoryService.get_statistics()` 新增 `strategy_distribution`（策略维度胜率/PnL）。
  - `GET /api/v1/modules/commander/trading-diagnosis` 新增：
    - `strategy_distribution_30d`
    - `decision_contract_integrity`（含 coverage/by_source/samples/healthy）
  - 契约完整性不健康时自动追加 `diagnosis_hints`。

- **结构清理与工具：**
  - strategy 字段解析统一收敛到 `normalize_strategy_field()`（减少 `strategy/strategy_used/strategy_id` 重复分支）。
  - 新增 `scripts/migrate_strategy_ids.py`（安全模式：只生成回填计划，不直接重写历史记录）。

## 2026-05-02 — AI 维护交接文档与优化结果固化

- **文档：** 新增 `docs/AI_HANDOFF_OPTIMIZATION_VERIFICATION_2026Q2.md`，汇总本轮系统测试与代码侧优化项、环境变量、验证命令（`health` / `trading-diagnosis` / `decision-traces`）、调参约束、`events.db` 裁剪脚本与重启注意点；`docs/README.md` 已索引。后续补充 **§4.2c**：监控数据源优先级（持仓 vs `recent_events`）、`GET /api/v1/positions` 的 `size`/`notional_value` 与 CCXT 别名字段说明。
- **变更摘要（实现已于同期合入仓库）：** 决策轨迹持久化与 `top_hold_reason_tags`；`ai_core` 取价兜底与 `trade_counters`；OKX TLS（合并 CA / 应急开关）；LLM 超时可调；第三方采集默认限速；`scripts/prune_events_db.py`；`.env.example` 补充 TLS/LLM 相关说明。

## 2026-04-26 — 安全加固、鉴权回归测试与文档同步

- **API 鉴权与权限策略：**
  - 受保护写接口启用 token + role（默认 admin）校验；
  - WebSocket `/ws` 默认要求 token；
  - commander mirror 目标固定为本机回环地址，降低 Host Header 相关转发风险。
- **新增 API 接口：**
  - `GET /api/v1/auth/status`（鉴权状态）
  - `GET /api/v1/auth/write-policy`（写策略可观测）
- **数据一致性：**
  - 历史交易库对非空 `order_id` 增加唯一索引；
  - `save_trade` 在有 `order_id` 时使用 `INSERT OR IGNORE`；
  - 交易历史服务增加缓存层幂等去重（`order_id` / `trade_id`）。
- **稳定性：**
  - 风控异常在实盘模式下改为 fail-safe 拒绝交易；
  - 数据库备份流程改为 `asyncio.to_thread` 避免阻塞事件循环。
- **测试与文档：**
  - 新增 `tests/unit/test_api_auth_write_guard.py` 覆盖 `401/403/200` 与策略接口可见性；
  - 同步更新 `docs/API_REFERENCE.md`、`docs/ENGINEERING.md`、`docs/OPERATIONS.md`。

## 2026-04-20 — 超时治理与可观测性增强（文档同步）

- **AI 对话链路可观测性：**
  - `POST /api/v1/ai/chat` 增加分段耗时 `trace`（`core_router_ms` / `executor_ms` / `llm_direct_ms`）与 `latency_ms_total`；
  - 超时响应同样返回 `trace`，用于快速定位瓶颈阶段。
- **行情聚合快路径优化：**
  - `GET /api/v1/market/state` 支持 `timeout_sec`（1.5~8.0），成功响应新增 `latency_ms`，降级响应新增 `timeout_sec`；
  - `market/state` 扇出聚合优先快路径，降低 `snapshot_timeout` 触发概率。
- **学习反馈观测增强：**
  - `GET /api/v1/modules/ai/learning-feedback` 的 `summary` 新增 `penalized_ratio`、`total_stop_loss_hits`、`penalty_rule`。
- **文档同步：**
  - 更新 `docs/API_REFERENCE.md`、`docs/DEVELOPMENT.md`、`docs/OPERATIONS.md`、`docs/OPENCLAW_INTEGRATION_GUIDE.md`，对齐当前运行行为与验收口径。

## 2026-04-16 — OpenClaw 对接文档全量更新 + 网络守护文档同步

- 新增 `docs/OPENCLAW_INTEGRATION_GUIDE.md`：
  - 对接目标、最小读写接口集、上线前检查、事件补偿策略、治理审计要点、常见失败点。
- 文档索引更新：
  - `README.md`、`docs/README.md` 增加 OpenClaw 对接入口。
- API 文档更新：
  - `docs/API_REFERENCE.md` 新增“OpenClaw 对接最小接口集”。
- 工程文档更新：
  - `docs/ENGINEERING.md` 增加 `market.state` 缓存优先 + 缺失补拉 + 自适应超时设计说明；
  - 增加 OpenClaw 对接契约说明（读写入口与 `source=openclaw` 审计建议）。
- 运维与开发文档更新：
  - `docs/OPERATIONS.md` 增加 OpenClaw 上线核对步骤；
  - `docs/DEVELOPMENT.md` 增加 OpenClaw 本地联调最小命令集。
- 网络守护能力文档化：
  - `docs/OPERATIONS.md` 已同步 `scripts/okx_proxy_guard.py` 与 `deploy/systemd/okx-proxy-guard.{service,timer}` 的启用流程。

## 2026-04-15 — 新增每日托管验收手册（3~5 步）

- 新增 `docs/DAILY_HOSTING_ACCEPTANCE.md`，提供日常托管最小验收路径：
  - 一键总验收（当前统一入口：`scripts/verify.py trading`）
  - 托管模式/自动化档位检查
  - 统一风控红线检查
  - 账户持仓与事件流活性检查
  - 失败时自动降级到半自动的固定处置动作
- `docs/README.md` 增加该手册入口，便于值守快速定位。
- `docs/OPERATIONS.md` 增加引用，统一“运行巡检”和“日常托管验收”入口。
- `docs/API_REFERENCE.md` 补充治理与托管相关接口清单，并给出该手册作为日常验收建议。

## 2026-04-15 — 文档全量同步（API/MCP/工程）与同步一致性说明

- **文档结构更新:**
  - 新增 `docs/MCP_BASELINE.md`，统一 MCP 基础概念、OKX Agent Trade Kit 对标结论与落地方向。
  - `docs/README.md` 与根 `README.md` 增加 MCP 基线文档入口。
- **工程文档更新:**
  - `docs/ENGINEERING.md` 新增“账户/持仓同步一致性”章节，明确 `get_exchange()` 多级兜底与 `commander/snapshot` 持仓回退策略。
- **API 文档更新:**
  - `docs/API_REFERENCE.md` 补充：
    - `GET /api/v1/modules/commander/snapshot` 的持仓回退语义；
    - `GET /api/v1/modules/commander/account-diagnostics` 的超时降级字段语义；
    - `GET /api/v1/modules/ai/learning-feedback` 的学习反馈用途。
- **运维与开发文档更新:**
  - `docs/OPERATIONS.md` 增加账户/持仓一致性巡检命令与降级判读说明。
  - `docs/DEVELOPMENT.md` 增加 MCP 基础联调步骤与最小验收命令。

## 2026-04-14 — 日志清理与运行维护

- **日志清理:** 清空 `logs/` 下历史运行日志与临时诊断文件（保留 `logs/.gitkeep` 及目录结构），减少磁盘占用并避免旧日志干扰巡检。
- **运行维护:** 保持账户链路优先策略，持续使用 OKX 代理优先与抖动降载保护，降低市场高频请求对钱包/持仓同步的影响。
- **文档同步:** 更新变更记录，便于后续运维追溯与发布同步。

## 2026-04-14 — API 文档与仓库同步

- **API 文档对齐运行态:** `docs/API_REFERENCE.md` 明确：
  - `GET /api/v1/market/symbol/{symbol}` 支持包含 `/` 的 symbol（建议 URL 编码如 `BTC%2FUSDT`）
  - `market/state` 与 `market/symbol` 的超时降级语义（`degraded=true`、缓存回退）
  - 事件流补齐中文别名字段（`type_zh`/`action_zh`/`side_zh`/`detail_zh`/`reason_zh`）
- **OpenAPI 导出:** 从运行实例 `GET /openapi.json` 导出到 `docs/API_OPENAPI_FULL.json`（权威以该文件与线上 `/docs` 为准）。
- **仓库卫生:** 扩展 `.gitignore` 以忽略 `logs/_tmp*.json` 与 `*.backup*`/`*.bak_*`，并移除本地备份残留文件，避免误提交。

## 2026-04-14 — 监控 API 与文档

- **监控:** `GET /api/v1/monitoring/alerts` 与 `alerts/history` 合并 **TradingMonitor** 与 **EnhancedMonitoringSystem** 告警，条目含 `source` 字段；`summary` 增加 `sources` 及增强监控状态块；`resolve` 同时识别两路 ID。`MainController` 在增强监控初始化成功/失败/清理时调用 `set_enhanced_monitoring`，保证 REST 与 Telegram 规则告警一致。
- **OKX 钱包/仓位同步:** `OKXExchange.invalidate_account_caches()`；`force_sync_account_state` 与 `get_account_sync_diagnostics` 在拉取前失效缓存；下单/撤单成功后失效缓存；私有 WebSocket `positions` 推送经 `merge_positions_ws_update` 合并进持仓缓存并失效余额缓存（需 `OPENCLAW_OKX_WS_ENABLED=1`）。
- **OKX 凭证加载:** `AITradingEngine.initialize` 现与 `config/config.yaml` 中 `api_key_env` / `secret_env` / `passphrase_env` 一致，从对应环境变量解析后再构造 `OKXExchange`（此前仅从 `exchanges.okx` 取字典时缺少 `api_key` 字段，会导致引擎未接交易所却仍以为「已配密钥」）。
- **文档:** 更新 `API_REFERENCE.md`（REST 标准化头、WebSocket 出站字段、`debug/exchange-binding`、监控合并说明）、`ENGINEERING.md`（可观测性与单实例 API）、`OPERATIONS.md`（监控巡检小节与验收字段）。

## 2026-04-13 — 文档与仓库卫生

- **文档**：`ENGINEERING` 补充 Compose 挂载 `./scripts`、`./tests` 与 `HOST_CLASH_EGRESS` 引用；`OPERATIONS` 补充 `verify_full_stack_network.sh`、`/api/v1/system/acceptance`、`startup_acceptance.py` 与宿主机 Clash 文档链接；`docs/README`、根 `README` 同步索引与快速命令。
- **仓库**：`agents/`（本地会话类 `*.jsonl` 等）不再纳入版本控制，已加入 `.gitignore` 并从索引移除历史误提交文件；`workspace/memory/working/` 等运行时碎片、`workspace/memory/core` 下本机人格 Markdown（保留已跟踪的 `SKILL_PACK_*` 等）、`data/**/*.db`、`backups/`、`logs` 下滚动日志与 `logs/config-health.json` 等写入 `.gitignore`，已跟踪的 `working/*.json` 从索引移除。

## 2026-04-12 — 配置统一与仓库清理

- **配置**：业务主配置仅为 `config/config.yaml`（及可选同目录 `local.*`）；`ConfigManager` 不再加载 `openclaw.yml`、`default.yml`、按节分散的旧 JSON 树。
- **删除**：根目录 `openclaw-trading.json*` 备份；`data/config` 下旧 `default.yml`、`*.json` 测试碎片等；该目录保留 `.gitkeep` 供可选本机 `local.*`。
- **部署**：根目录 **已移除** `docker-compose.yml` / `Dockerfile`；以裸机 `python -m src.main`、systemd 或 `scripts/start-openclaw-trading.sh` 为主；`MODE`/`TRADING_MODE`/`SYSTEM_MODE` 请在 `.env` 显式配置。
- **测试**：Pytest 9 要求异步 fixture 使用 `pytest_asyncio.fixture`；`NaturalLanguageInterface` 单测改为 `IsolatedAsyncioTestCase`。
- **工具**：`src/web/app.py` 改为读取主 YAML；新增 `scripts/network_connectivity_smoke.py`。
- **文档**：补回 `docs/ENGINEERING.md`、`docs/CHANGELOG.md`、`docs/memory/MEMORY_LIBRARY_GUIDE.md`；更新 `OPERATIONS`、`DEVELOPMENT`、`README` 索引；`status.sh` / `check-dual-system.sh` 改为检查 `config/config.yaml`。
- **仓库**：新增根 `.gitignore`（含 `config/local.*`、`data/config/local.*` 等）。
