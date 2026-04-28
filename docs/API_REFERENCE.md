# 全智能量化交易系统API
量化交易系统的RESTful API接口
**版本:** 1.0.0

**在线文档（若服务已启动）:** `http://<host>:8000/docs`（Swagger UI）、`http://<host>:8000/redoc`

**机器可读规范（与线上一致，由运行中服务导出）:** 同目录下 [`API_OPENAPI_FULL.json`](./API_OPENAPI_FULL.json)（OpenAPI 3.1，当前约 181 条路径；含请求体、查询参数、422 校验模型等）。

## 开平仓 API 与调试总览（2026-04 收口版）

### 1) 推荐读写入口

- **决策/执行统一入口（推荐）**
  - `POST /api/v1/modules/commander/dispatch`
  - 推荐来源字段：`source=openclaw|api_chat|control_hub`
- **执行审计与归因**
  - `GET /api/v1/modules/commander/trading-diagnosis`
  - `GET /api/v1/modules/commander/decision-traces`
  - `GET /api/v1/modules/commander/decision-traces/{trace_id}`
- **事件流（实时+补偿）**
  - `GET /api/v1/trade/events`

### 2) 开仓关键观察字段

从 `trading-diagnosis.data.analysis_pipeline_assessment.market_analysis.samples[]` 读取：

- `quality_score`
- `spread_bps`
- `depth_imbalance`
- `funding_rate`
- `open_interest`
- `best_bid` / `best_ask`

这些字段用于开仓门控（置信度、RR、点差、深度失衡、资金费率、流动性）排障定位。

### 3) 调试与复测接口

- `POST /api/v1/modules/commander/learning/seed-and-run`
  - 用于学习闭环联调（不下实单，但会修改学习状态）
- `GET /api/v1/modules/ai/learning-feedback`
  - 查看止损惩罚与学习反馈命中状态

### 4) 建议的一键验收命令

- `make verify-trading`
- `make verify-trading-gates`

详见：`docs/TRADING_DEBUG_PLAYBOOK.md`

## 升级后实时链路（2026-04-13）

以下为当前版本实测可用的“实时信息与通知”主链路，优先作为前端与司令部集成基线：

- **司令部统一入口（A 接口）**
  - `POST /api/v1/modules/commander/dispatch`
  - body: `{"message":"...", "source":"api_chat|telegram|control_hub|..." }`
  - 用途：统一接收开仓/平仓/行情问询/巡检指令。
  - 超时治理（2026-04-20 更新）：
    - 同步模式支持 `timeout_sec`（默认 12 秒，范围 2~90 秒）
    - 若同步超时返回 `status=timeout`，建议改用 `async_mode=true`
    - 异步任务查询：`GET /api/v1/modules/commander/dispatch/jobs/{job_id}`
  - 调用建议（值守脚本）：
    - `python3 scripts/commander_dispatch_client.py "请返回当前系统运行摘要"`
    - 该脚本默认采用“同步优先，超时自动异步并轮询”策略

- **交易/风控事件流（前端与外部 API 推荐）**
  - `GET /api/v1/trade/events?limit=...`
  - 事件类型含：`trade.fill`（开平仓成交）、`trade.position`（含 `sltp.create` / `sltp_stop_loss_triggered` 等）、`market.update`（行情判断与质量摘要）。
  - 事件已补齐中文别名字段（不破坏原字段）：`type_zh`、`action_zh`、`side_zh`、`detail_zh`/`reason_zh`，便于前端直接展示。
  - 该接口为环形缓冲读取，适合作为前端轮询与外部系统对账源。

- **执行脊柱与审计快照**
  - `GET /api/v1/trade/execution_spine`
  - `GET /api/v1/modules/execution/production-audit`
  - 用途：读取最新一笔开平仓来源、原因、成败、策略单写入状态（S1）与 SLTP 统计。

- **行情与判断输出**
  - `GET /api/v1/market/symbol/{symbol}`（**symbol 含 `/`**；推荐 URL 编码，例如 `BTC%2FUSDT`）
  - `GET /api/v1/market/state`
  - `GET /api/v1/modules/data/hub/unified-snapshot`
  - 用途：提供实时行情、质量分、执行成本、风险建议与“是否可交易”判断依据。
  - 2026-04-20 补充：
    - `market/state` 支持 `timeout_sec`（1.5~8.0，默认 3.2）；
    - 成功响应附带 `latency_ms`；
    - 超时降级响应附带 `timeout_sec`；
    - 聚合过程优先快路径（ticker-only）以减少 `snapshot_timeout`。

- **模拟盘联调入口（升级验证用）**
  - `POST /api/v1/modules/execution/simulate-order`
  - 用于压测行情波动、触发止盈止损链路、验证通知与事件输出。

### 二次验收快照（2026-04-13 21:31 UTC+8）

以下接口已在当前运行环境复核通过（HTTP 200 且返回结构有效）：

- **系统与链路**
  - `GET /api/v1/system/health` -> `healthy`
  - `GET /api/v1/s1/verify` -> `all_passed=true`
  - `GET /api/v1/system/acceptance` -> `verdict=PASS`（本次运行实例可用性总验收）
  - `GET /api/v1/modules/system/health` -> `overall=healthy`
  - `GET /api/v1/modules/commander/audit?enrich=true` -> `all_passed=true`

- **实时推送/事件补偿**
  - `GET /api/v1/trade/events?limit=15` 返回持续 `market.update` / `trade.position` 等事件，作为前端与外部系统的补偿/回放基线。
  - WebSocket 仍建议与 `trade/events` 并用：前者实时，后者补偿。

- **报警**
  - `GET /api/v1/monitoring/alerts` 可用（空数组表示当前无活跃告警，不是链路失败）。

- **记忆系统（读写与持久化）**
  - `POST /api/v1/ai/memory/store` 写入成功（返回 `memory_id`）。
  - `POST /api/v1/ai/memory/recall` 立即召回命中（验证读写链路正常）。
  - `GET /api/v1/modules/commander/memory/status` 返回网关统计、分层计数、质量指标。
  - `GET /api/v1/modules/commander/memory/workspace?filename=COMMANDER_PROFILE.md` 返回工作区记忆文件内容。

- **迁移完成说明（重要）**
  - `GET /api/v1/data-fusion/analyze{,/symbol}` 兼容路由已移除。
  - 生产调用统一使用：`GET /api/v1/market/symbol/{symbol}` 与 `POST /api/v1/modules/intelligence/batch-analyze`。

### 账户与持仓同步接口（2026-04-15 更新）

- **`GET /api/v1/modules/commander/snapshot`**
  - 用于司令部统一快照。
  - `data.account.positions` 在缓存为空时会自动回退到：
    1. 进程内 `ai_trading_engine.positions`
    2. 交易所短超时直拉 `get_positions()`
  - 若使用了回退，会在 `data.alerts` 增加提示（如 `account_positions_from_exchange_fallback`）。

- **`GET /api/v1/modules/commander/account-diagnostics`**
  - 权威同步诊断接口（交易所实时持仓/余额 vs 本地状态）。
  - 在上游慢时可能返回：
    - `success=true`
    - `degraded=true`
    - `data.hint=account_diagnostics_timeout`
  - 即使超时降级，也会返回关键字段（如 `exchange`、`cached_position_count`），避免误判为“无交易所连接”。

- **`GET /api/v1/modules/commander/trading-diagnosis`**
  - 交易全链路诊断接口（ai_core / ai_trading_engine / execution_gateway / sltp / learning）。
  - 返回 `data.position_limits_snapshot` 用于确认统一仓位入口是否生效，关键字段：
    - `symbol_max_margin_ratio`
    - `max_same_direction_positions`
    - `max_positions_oneway`
    - `max_positions_hedge`
    - `hard_max_positions`
  - 2026-04-28 补充关键诊断块：
    - `data.execution_reconciliation`：本地/交易所状态对账摘要（仓位漂移、孤儿挂单、修复建议）
    - `data.execution_reconciliation_protection`：对账保护层状态（symbol/global 锁）
    - `data.execution_safe_recovery`：已自动执行的安全恢复动作（仅刷新/保护，不直接撤单或强平）
    - `data.decision_traces`：最近决策轨迹样本
    - `data.trace_learning_feedback`：学习引擎基于轨迹的反馈摘要
  - 支持 `limit_events` 参数控制 `execution_gateway.recent_events` 窗口大小。

- **`GET /api/v1/modules/commander/decision-traces`**
  - 最近 AI 决策轨迹聚合复盘接口。
  - 用途：
    - 查看 `guard_rejected` / `execution_failed` / `reconciliation_blocked` 分布
    - 查看 `top_guard_reasons` / `top_execution_failures` / `top_reconciliation_blocks`
    - 提取最近轨迹样本用于排障或验收

- **`GET /api/v1/modules/commander/decision-traces/{trace_id}`**
  - 查看单条 AI 决策链路。
  - 返回：
    - `intent`
    - `guard`
    - `execution`
    - `reconciliation`

- **`POST /api/v1/modules/commander/learning/seed-and-run`**
  - 验收/联调用的学习闭环触发接口。
  - 用途：
    - 注入少量 synthetic trade-close 样本
    - 立即触发学习引擎分析、报告与规则优化流程
  - 注意：
    - 不会下真实订单
    - 但会修改学习状态、记忆与部分运行时配置覆盖，不属于只读接口

- **`GET /api/v1/modules/ai/learning-feedback`**
  - 返回止损复盘与信号惩罚状态：
    - `stop_loss_hits`
    - `penalty_steps`
    - `extra_confidence_threshold`
  - 2026-04-20 补充 summary 可观测字段：
    - `penalized_ratio`
    - `total_stop_loss_hits`
    - `penalty_rule.step_hits`
    - `penalty_rule.step_threshold`
    - `penalty_rule.max_threshold`
  - 用于验收“连续止损后提高开仓门槛”的学习反馈机制。

### AI 对话接口时延定位（2026-04-20 更新）

- **`POST /api/v1/ai/chat`**
  - 请求体支持 `timeout_sec`（5~90，默认 20）。
  - 成功响应新增：
    - `data.trace.path`：实际命中路径（`core_brain_router` / `ai_command_executor` / `llm_direct`）
    - `data.trace.core_router_ms` / `executor_ms` / `llm_direct_ms`：分段耗时
    - `latency_ms_total`：本次接口总耗时
  - 超时响应 `status=timeout` 时仍返回 `trace` 与 `latency_ms_total`，用于快速定位卡点阶段。

### 治理与托管接口（2026-04-15 更新）

- **托管与自动化**
  - `GET /api/v1/modules/commander/hosting-mode`
  - `POST /api/v1/modules/commander/hosting-mode`
  - `GET /api/v1/modules/commander/automation-profile`
  - `POST /api/v1/modules/commander/automation-profile`

- **统一风控红线**
  - `GET /api/v1/modules/commander/risk-redlines`
  - `POST /api/v1/modules/commander/risk-redlines`

- **治理审计与工具契约**
  - `GET /api/v1/modules/commander/governance-audit`
  - `GET /api/v1/modules/commander/tool-contract`

- **托管守护与架构/升级闭环（补充）**
  - `GET /api/v1/modules/commander/hosting-guard`
  - `POST /api/v1/modules/commander/hosting-guard`
  - `GET /api/v1/modules/commander/architecture/layers`
  - `GET /api/v1/modules/commander/upgrade/benchmark`
  - `POST /api/v1/modules/commander/upgrade/run`
  - `GET /api/v1/modules/commander/openclaw-integration`
  - 用途：用于托管守护参数巡检、L1-L5 分层状态验收、升级闭环执行与 OpenClaw 推送链路就绪度检查。

- **验收建议**
  - 日常值守可直接执行 `docs/DAILY_HOSTING_ACCEPTANCE.md`，以最少命令完成托管可用性确认。

### OpenClaw 对接最小接口集（2026-04-16 更新）

- **读取能力/契约**
  - `GET /api/v1/modules/commander/capabilities`
  - `GET /api/v1/modules/commander/tool-contract`
  - `GET /api/v1/modules/surface/channels`
  - `GET /api/v1/modules/surface/registry`

- **读取状态/对账**
  - `GET /api/v1/modules/commander/snapshot`
  - `GET /api/v1/modules/commander/account-diagnostics`
  - `GET /api/v1/trade/events`

- **写入入口**
  - `POST /api/v1/modules/commander/dispatch`
  - `GET /api/v1/modules/commander/dispatch/jobs/{job_id}`
  - 建议 body 带 `source=openclaw`，便于治理审计与链路追踪

- **完整操作流程**
  - 见 `docs/OPENCLAW_INTEGRATION_GUIDE.md`。

### WebSocket（OpenAPI 中不展开）

- **URL:** `ws://<host>:8000/ws`（生产若走 HTTPS 则为 `wss://`）
- **鉴权:** 默认要求携带 token（`?token=<jwt>` 或 `Authorization: Bearer <jwt>`），未携带/无效会以 `1008` 关闭连接。
- **用途:** 实时推送；连接后发送 JSON，支持 `subscribe` / `unsubscribe` / `heartbeat`（与 `WebSocketEventType` 一致，详见 `src/modules/api/server.py` 中 `_handle_websocket_connection`）。
- **频道匹配:** 支持精确频道与前缀通配，例如 `trade.*`、`market.*`。
- **建议生产基线:** WebSocket 与 `GET /api/v1/trade/events` 并用（前者实时、后者补偿与回放），避免前端因连接抖动丢关键成交/止损事件。
- **出站消息约定（与 REST 对齐的兼容补齐）:** 服务端在保留原有字段（如 `type`、`channel`、`data`、`connection_id`、`channels`）的同时，为每条出站 JSON 补齐 `ok`、`success`、`status`、`timestamp` 等标准字段（实现上复用与 HTTP 相同的 `_normalize_api_payload` 逻辑）。

### REST JSON 网关标准化

- **范围:** 以 `/api` 为前缀的路径，响应体为 JSON 时，由中间件在**不删除原有字段**的前提下补齐 `ok`、`success`、`status`、`message`（按需）、`timestamp`。
- **响应头:** `X-OpenClaw-Standardized: 1` 表示该响应已按上述规则规范化。

### 鉴权与写接口策略（2026-04-26 更新）

- **登录配置:** `POST /api/v1/auth/login` 依赖管理员账号配置；若未配置会返回 `503`（`API auth is not configured`）。
- **写接口保护:** `POST/PUT/PATCH/DELETE` 命中受保护前缀时，默认强制 token 校验；无 token 返回 `401`，角色不满足返回 `403`。
- **内网白名单绕过（本机/内网对接用）:** 若请求来源 IP 命中 `config/config.yaml` 的 `api.auth_bypass_cidrs`（如默认 `127.0.0.1/32`、`::1/128`），则写接口可**绕过 token 鉴权**（仍建议仅用于内网环境）。
- **默认受保护前缀:** `/api/v1/modules`、`/api/v1/monitoring`、`/api/v1/commander`、`/api/v1/trade`。
- **角色策略:** 默认仅 `admin` 可执行受保护写操作（可由 `api.required_write_roles` 调整）。
- **策略可观测接口:**
  - `GET /api/v1/auth/status`
  - `GET /api/v1/auth/write-policy`
- **Commander 入口策略:** 镜像转发已移除，仅保留显式声明的 `/api/v1/modules/commander/*` 能力接口。

### 运行模式兼容说明（Docker / 裸机）

为避免历史容器化配置与当前裸机运行冲突，接口调用与代理请按以下基线区分：

- **API 基址**
  - Docker 常见：`http://localhost:8000`
  - 裸机（systemd/supervisor/python 直跑）常见：`http://127.0.0.1:8000`
- **代理变量**
  - 仅在需要外网代理时设置 `HTTP_PROXY` / `HTTPS_PROXY`。
  - `NO_PROXY` 必须包含 `127.0.0.1,localhost,redis`，避免本地 API/Redis 被错误走代理。
- **Docker 专属域名提示**
  - `host.docker.internal` 仅用于容器访问宿主机；裸机模式不应写入该地址。
- **文档权威顺序**
  - 以运行实例 `GET /openapi.json` 为准；
  - `docs/API_OPENAPI_FULL.json` 为当前仓库快照；
  - 本文用于链路与语义说明。

---

## 本次 API 对接复核（2026-04-21）

以下为当前裸机实例（`http://127.0.0.1:8000`）抽样复核结果（用于“是否对接正常”的快速证据）：

- **OpenAPI 与文档一致性**
  - `python3 scripts/check_docs_runtime_consistency.py` -> OK（snapshot）
  - `python3 scripts/check_docs_runtime_consistency.py --runtime` -> OK（runtime build）
  - 当前 OpenAPI：OpenAPI 3.1，约 181 条路径（与 `docs/API_OPENAPI_FULL.json` 一致）

- **系统状态**
  - `GET /api/v1/system/status` -> `running`（29/29 modules）
  - `GET /api/v1/system/acceptance` -> `PASS`

- **交易所对接**
  - `GET /api/v1/exchanges` -> OKX `connected`
  - `GET /api/v1/debug/exchange-binding` -> MainController 与 DataSourceHub 绑定一致、ticker 探针有值

- **交易闭环可观测性**
  - `GET /api/v1/trade/events?limit=...` -> 持续返回事件（用于前端与外部系统回放/对账）
  - `GET /api/v1/positions` -> 返回持仓结构（带 cache/stale 语义）
- **调用地址建议**
  - 推荐在脚本中统一声明：`BASE_URL=${BASE_URL:-http://127.0.0.1:8000}`，再用 `"$BASE_URL/..."` 访问接口，减少 Docker/裸机切换时的手工修改。

---

## 行情聚合接口的降级语义（重要）

为了避免外部网络/交易所抖动导致控制面阻塞，以下接口采用“**快返回 + 降级标志**”：

- **`GET /api/v1/market/state`**
  - **正常**：`{"ok": true, "state": {...}, "degraded": false, "latency_ms": 123}`
  - **降级**：`{"ok": true, "state": {...或{}}, "degraded": true, "message": "market_state_timeout_degraded", "timeout_sec": 3.2}`
  - `state` 中包含：
    - `symbols_attempted` / `symbols_considered` / `symbols_failed`
    - `symbol_views`：即便上游超时也会返回最小降级行（`partial=true` + `errors=["snapshot_timeout"]`），用于可解释与前端提示
    - 2026-04-20 起聚合优先快路径，降级行可能包含 `errors=["snapshot_skipped_fast_mode"]`（属于主动限时策略，不等同于交易所断连）

- **`GET /api/v1/market/symbol/{symbol}`**
  - **快返回语义（重要）**：为避免上游慢/抖动导致控制面阻塞，该接口采用“可用即回 + 后台刷新”的策略。
  - **`include_snapshot=false`（默认）**：
    - 优先返回缓存（`message="symbol_view_cached"`），保证响应快速。
  - **`include_snapshot=true`**：
    - **若缓存存在**：立即返回缓存（`message="symbol_view_cached_refreshing"`），同时后台触发一次完整刷新；响应 `view` 会携带 `cache_age_sec`（缓存年龄，秒）。
    - **若缓存不存在**：立即返回 warming stub（`message="symbol_view_fastpath_refreshing"`），同时后台触发完整刷新；后续请求会命中缓存并逐步补齐 `quality_score/atr_pct_1h/...`。
  - 判读建议：
    - `degraded=true` 不代表交易所断连，可能是“缓存/快路径返回”；
    - 请结合 `GET /api/v1/data-hub/unified-snapshot` 的 `collector.health/errors` 判断具体慢源与字段缺失原因。

### 调试：交易所与数据中心绑定一致性

- **`GET /api/v1/debug/exchange-binding`**：在**当前 API 进程**内探测 `MainController` 与 `DataSourceHub` 是否为同一绑定、交易所类型及 `hub.get_ticker("BTC/USDT")` 探针。用于排除「脚本另起 Python 进程与线上 API 不一致」类问题。

### 监控与告警 API

系统内存在两路监控，REST 已做**合并展示**（便于总控与外部系统单一入口）：

| 子系统 | 模块 | 典型场景 |
|--------|------|----------|
| `trading_monitor` | `TradingMonitor` | 订单长时间挂单、行情过期、点差/成交量异常、风险指标阈值等 |
| `enhanced_monitoring` | `EnhancedMonitoringSystem` | 回撤、仓位比例、连续亏损、API 错误率、余额等；默认规则可发 **Telegram** /日志 |

- **`GET /api/v1/monitoring/summary`**：在原有交易监控摘要基础上增加 `sources`（两路是否可用），并在增强监控可用时附带 `enhanced_monitoring` 状态块（`get_system_status()`）。
- **`GET /api/v1/monitoring/alerts`**、**`GET /api/v1/monitoring/alerts/history`**：返回**合并后的列表**，按时间倒序；每条告警含 **`source`**：`trading_monitor` 或 `enhanced_monitoring`，以及统一可读的 `details` / `timestamp`（Unix 秒，另附 `timestamp_iso` 便于阅读）。
- **`POST /api/v1/monitoring/alerts/{alert_id}/resolve`**：先在 `TradingMonitor` 活跃告警中查找，否则调用增强监控的 `resolve_alert`。

其他监控子路径（策略表现、市场数据状态、异常检测、proactive-ai 等）仍以 **`/api/v1/monitoring/...`** 为准，详见 OpenAPI。

### 已清理模块说明

`risk_api.py`、`backtest_api.py`、`enhanced_api.py` 已从主仓清理，避免僵尸接口与误用路径。接口权威以 `GET /openapi.json` 为准。

---

## 接口一览

| 方法 | 路径 | 摘要 | Tags |
|------|------|------|------|
| GET | `/api/metrics` | Get Metrics | api, metrics |
| POST | `/api/strategies/activate/{strategy_name}` | Activate Strategy | strategies |
| POST | `/api/strategies/add` | Add Strategy | strategies |
| POST | `/api/strategies/deactivate/{strategy_name}` | Deactivate Strategy | strategies |
| GET | `/api/strategies/list` | Get Strategies | strategies |
| GET | `/api/strategies/performance` | Get Strategy Performance | strategies |
| DELETE | `/api/strategies/remove/{strategy_name}` | Remove Strategy | strategies |
| POST | `/api/strategies/update/{strategy_name}` | Update Strategy | strategies |
| GET | `/api/v1/ai-models` | Get Ai Models | api, api-v1, ai-models |
| POST | `/api/v1/ai-models` | Add Ai Model | api, api-v1, ai-models |
| GET | `/api/v1/ai-models/default` | Get Default Ai Model | api, api-v1, ai-models |
| PUT | `/api/v1/ai-models/default` | Set Default Ai Model | api, api-v1, ai-models |
| DELETE | `/api/v1/ai-models/{id}` | Delete Ai Model | api, api-v1, ai-models |
| PUT | `/api/v1/ai-models/{id}` | Update Ai Model | api, api-v1, ai-models |
| POST | `/api/v1/ai/chat` | Ai Chat | api, api-v1, ai |
| POST | `/api/v1/ai/memory/disk-policy/run` | Memory Disk Policy Run | api, api-v1, ai-memory |
| POST | `/api/v1/ai/memory/instruction` | Add System Instruction | api, api-v1, ai-memory |
| POST | `/api/v1/ai/memory/preference` | Add User Preference | api, api-v1, ai-memory |
| GET | `/api/v1/ai/memory/quality` | Memory Quality Metrics | api, api-v1, ai-memory |
| POST | `/api/v1/ai/memory/recall` | Memory Recall | api, api-v1, ai-memory |
| GET | `/api/v1/ai/memory/stats` | Get Memory Stats | api, api-v1, ai-memory |
| POST | `/api/v1/ai/memory/store` | Memory Store | api, api-v1, ai-memory |
| GET | `/api/v1/ai/memory/summaries/status` | Memory Summaries Status | api, api-v1, ai-memory |
| GET | `/api/v1/ai/memory/trace` | Memory Trace | api, api-v1, ai-memory |
| GET | `/api/v1/ai/memory/trading-summary` | Get Trading Summary | api, api-v1, ai-memory |
| GET | `/api/v1/ai/memory/workspace-file/{filename}` | Get Workspace Memory File | api, api-v1, ai-memory |
| PUT | `/api/v1/ai/memory/workspace-file/{filename}` | Update Workspace Memory File | api, api-v1, ai-memory |
| GET | `/api/v1/ai/memory/workspace-files` | Get Workspace Memory Files | api, api-v1, ai-memory |
| POST | `/api/v1/ai/query` | Ai Query | api, api-v1, ai |
| POST | `/api/v1/auth/login` | Login | api, api-v1, auth |
| POST | `/api/v1/auth/logout` | Logout | api, api-v1, auth |
| GET | `/api/v1/auth/me` | Get Current User | api, api-v1, auth |
| POST | `/api/v1/auth/refresh` | Refresh Token | api, api-v1, auth |
| GET | `/api/v1/auth/status` | Auth Status | api, api-v1, auth |
| GET | `/api/v1/auth/write-policy` | Auth Write Policy | api, api-v1, auth |
| GET | `/api/v1/control-center/state` | Get Control Center State | api, api-v1, control-center |
| GET | `/api/v1/data-fusion/history` | Get Analysis History | api, api-v1, data-fusion |
| GET | `/api/v1/data-fusion/sources` | Get Data Sources | api, api-v1, data-fusion |
| GET | `/api/v1/data-hub/ai-analysis` | Data Hub Ai Analysis | api, api-v1, data-hub |
| GET | `/api/v1/data-hub/contract` | Data Hub Contract | api, api-v1, data-hub |
| GET | `/api/v1/data-hub/quality-advice` | Data Hub Quality Advice | api, api-v1, data-hub |
| GET | `/api/v1/data-hub/status` | Data Hub Status | api, api-v1, data-hub |
| GET | `/api/v1/data-hub/unified-snapshot` | Data Hub Unified Snapshot | api, api-v1, data-hub |
| GET | `/api/v1/exchanges` | Get Exchanges | api, api-v1, exchanges |
| GET | `/api/v1/executions` | Get Executions | api, api-v1, executions |
| GET | `/api/v1/external/analyze-trends` | External Analyze Trends | api, api-v1, external |
| POST | `/api/v1/external/indicators` | External Indicators | api, api-v1, external |
| GET | `/api/v1/external/signals` | External Signals | api, api-v1, external |
| GET | `/api/v1/market/data` | Get Market Data | api, api-v1, market |
| GET | `/api/v1/market/klines` | Get Market Klines Q | api, api-v1, market |
| GET | `/api/v1/market/klines/{symbol}` | Get Market Klines | api, api-v1, market |
| GET | `/api/v1/market/orderbook` | Get Market Orderbook Q | api, api-v1, market |
| GET | `/api/v1/market/orderbook/{symbol}` | Get Market Orderbook | api, api-v1, market |
| GET | `/api/v1/market/state` | Get Market State | market |
| GET | `/api/v1/market/symbol/{symbol}` | Get Market Symbol View | market |
| GET | `/api/v1/market/symbols` | Get Market Symbols | api, api-v1, market |
| GET | `/api/v1/market/ticker` | Get Market Ticker Q | api, api-v1, market |
| GET | `/api/v1/market/ticker/{symbol}` | Get Market Ticker | api, api-v1, market |
| GET | `/api/v1/metrics` | Get Metrics V1 | api, api-v1, metrics |
| GET | `/api/v1/models` | Get Models | api, api-v1, models |
| POST | `/api/v1/models/train` | Train Model | api, api-v1, models |
| DELETE | `/api/v1/models/{id}` | Delete Model | api, api-v1, models |
| PUT | `/api/v1/models/{id}` | Update Model | api, api-v1, models |
| GET | `/api/v1/models/{id}/performance` | Get Model Performance | api, api-v1, models |
| GET | `/api/v1/modules/ai/frequency-profile` | Get Ai Frequency Profile | modules |
| POST | `/api/v1/modules/ai/frequency-profile` | Set Ai Frequency Profile | modules |
| GET | `/api/v1/modules/ai/guards` | Get Ai Execution Guards | modules |
| POST | `/api/v1/modules/ai/guards` | Update Ai Execution Guards | modules |
| GET | `/api/v1/modules/commander/account-diagnostics` | Commander Account Diagnostics | modules |
| POST | `/api/v1/modules/commander/account-sync/run` | Commander Account Sync Run | modules |
| GET | `/api/v1/modules/commander/audit` | Commander Audit | modules |
| GET | `/api/v1/modules/commander/capabilities` | Commander Capabilities | modules |
| POST | `/api/v1/modules/commander/chores` | Commander Chores | modules |
| POST | `/api/v1/modules/commander/dispatch` | Commander Dispatch | modules |
| GET | `/api/v1/modules/commander/dispatch/jobs/{job_id}` | Commander Dispatch Job | modules |
| GET | `/api/v1/modules/commander/memory/persona-preview` | Commander Memory Persona Preview | modules |
| GET | `/api/v1/modules/commander/memory/status` | Commander Memory Status | modules |
| GET | `/api/v1/modules/commander/memory/workspace` | Commander Memory Workspace | modules |
| GET | `/api/v1/modules/commander/snapshot` | Commander Snapshot | modules |
| GET | `/api/v1/modules/data/hub/unified-snapshot` | Data Hub Unified Snapshot | modules |
| GET | `/api/v1/modules/data/integration/health` | Data Integration Health | modules |
| GET | `/api/v1/modules/data/onchain/status` | Data Onchain Status | modules |
| GET | `/api/v1/modules/execution/production-audit` | Get Production Execution Audit | modules |
| POST | `/api/v1/modules/execution/simulate-order` | Execution Simulate Order | modules |
| POST | `/api/v1/modules/intelligence/batch-analyze` | Intelligence Batch Analyze | modules |
| GET | `/api/v1/modules/list` | Get All Modules | modules |
| GET | `/api/v1/modules/memory/daily-summary` | Get Memory Daily Summary | modules |
| POST | `/api/v1/modules/memory/daily-summary/run` | Run Memory Daily Summary | modules |
| GET | `/api/v1/modules/memory/stats` | Get Memory Stats | modules |
| GET | `/api/v1/modules/models` | Get Ai Models | modules |
| POST | `/api/v1/modules/models/{model_id}/select` | Select Ai Model | modules |
| GET | `/api/v1/modules/plugins/status` | Plugins Status | modules |
| GET | `/api/v1/modules/reserved/{domain}/ping` | Reserved Domain Ping | modules |
| GET | `/api/v1/modules/risk/config` | Get Risk Config | modules |
| POST | `/api/v1/modules/risk/config` | Update Risk Config | modules |
| POST | `/api/v1/modules/risk/reset` | Reset Risk Counters | modules |
| GET | `/api/v1/modules/risk/status` | Get Risk Status | modules |
| GET | `/api/v1/modules/skills/catalog` | Skills Catalog | modules |
| POST | `/api/v1/modules/skills/invoke` | Skills Invoke Reserved | modules |
| GET | `/api/v1/modules/stop-loss/stats` | Get Stop Loss Stats | modules |
| GET | `/api/v1/modules/strategy/optimization-config` | Get Strategy Optimization Config | modules |
| POST | `/api/v1/modules/strategy/optimization-config` | Update Strategy Optimization Config | modules |
| GET | `/api/v1/modules/strategy/optimization-status` | Get Strategy Optimization Status | modules |
| POST | `/api/v1/modules/strategy/optimize-now` | Trigger Strategy Optimization Now | modules |
| GET | `/api/v1/modules/strategy/research-jobs` | List Strategy Research Jobs | modules |
| GET | `/api/v1/modules/strategy/research-jobs/{job_id}` | Get Strategy Research Job | modules |
| POST | `/api/v1/modules/strategy/research-run` | Run Strategy Research Now | modules |
| POST | `/api/v1/modules/strategy/trade-feedback` | Submit Strategy Trade Feedback | modules |
| GET | `/api/v1/modules/surface/channels` | Surface Channels | modules |
| GET | `/api/v1/modules/surface/registry` | Surface Registry | modules |
| GET | `/api/v1/modules/system/health` | Get System Health | modules |
| GET | `/api/v1/modules/trading/symbols` | Get Trading Symbols | modules |
| POST | `/api/v1/modules/trading/symbols/config` | Config Trading Symbols | modules |
| POST | `/api/v1/modules/{module_id}/control` | Control Module | modules |
| GET | `/api/v1/monitoring/alerts` | Get Active Alerts | monitoring |
| GET | `/api/v1/monitoring/alerts/history` | Get Alert History | monitoring |
| POST | `/api/v1/monitoring/alerts/{alert_id}/resolve` | Resolve Alert | monitoring |
| GET | `/api/v1/monitoring/anomalies` | Get Anomaly Events | monitoring |
| GET | `/api/v1/monitoring/anomalies/active` | Get Active Anomalies | monitoring |
| POST | `/api/v1/monitoring/anomalies/data` | Add Anomaly Data | monitoring |
| GET | `/api/v1/monitoring/anomalies/model/performance` | Get Model Performance | monitoring |
| POST | `/api/v1/monitoring/anomalies/{event_id}/resolve` | Resolve Anomaly | monitoring |
| GET | `/api/v1/monitoring/logs` | Get Monitoring Logs | api, api-v1, monitoring |
| GET | `/api/v1/monitoring/market-data` | Get Market Data Status | monitoring |
| POST | `/api/v1/monitoring/market-data/update` | Update Market Data | monitoring |
| GET | `/api/v1/monitoring/proactive-ai/best-strategy` | Get Best Strategy | monitoring |
| GET | `/api/v1/monitoring/proactive-ai/fear-greed` | Get Fear Greed Index | monitoring |
| GET | `/api/v1/monitoring/proactive-ai/insights` | Get Proactive Insights | monitoring |
| GET | `/api/v1/monitoring/proactive-ai/market-state` | Get Proactive Market State | monitoring |
| GET | `/api/v1/monitoring/proactive-ai/news` | Get Proactive News | monitoring |
| GET | `/api/v1/monitoring/proactive-ai/opportunities` | Get Proactive Opportunities | monitoring |
| GET | `/api/v1/monitoring/proactive-ai/sentiment` | Get Proactive Sentiment | monitoring |
| GET | `/api/v1/monitoring/proactive-ai/stats` | Get Proactive Stats | monitoring |
| GET | `/api/v1/monitoring/proactive-ai/status` | Get Proactive Ai Status | monitoring |
| GET | `/api/v1/monitoring/risk` | Get Risk Metrics | monitoring |
| POST | `/api/v1/monitoring/risk/update` | Update Risk Metrics | monitoring |
| GET | `/api/v1/monitoring/strategies` | Get Strategy Performance | monitoring |
| POST | `/api/v1/monitoring/strategy/update` | Update Strategy Performance | monitoring |
| GET | `/api/v1/monitoring/summary` | Get Monitoring Summary | monitoring |
| GET | `/api/v1/monitoring/trades` | Get Trade History | monitoring |
| GET | `/api/v1/protected` | Protected Route | api, api-v1, api |
| GET | `/api/v1/risk/metrics` | Get Risk Metrics | api, api-v1, risk |
| GET | `/api/v1/s1/verify` | S1 Full Verify | s1 |
| GET | `/api/v1/settings` | Get Settings | api, api-v1, settings |
| PUT | `/api/v1/settings` | Update Settings | api, api-v1, settings |
| GET | `/api/v1/strategies` | Get Strategies | api, api-v1, strategies |
| POST | `/api/v1/strategies` | Create Strategy | api, api-v1, strategies |
| DELETE | `/api/v1/strategies/{id}` | Delete Strategy | api, api-v1, strategies |
| GET | `/api/v1/strategies/{id}` | Get Strategy | api, api-v1, strategies |
| PUT | `/api/v1/strategies/{id}` | Update Strategy | api, api-v1, strategies |
| POST | `/api/v1/strategies/{id}/activate` | Activate Strategy | api, api-v1, strategies |
| POST | `/api/v1/strategies/{id}/deactivate` | Deactivate Strategy | api, api-v1, strategies |
| GET | `/api/v1/strategies/{id}/performance` | Get Strategy Performance | api, api-v1, strategies |
| GET | `/api/v1/system/health` | System Health V1 | api, api-v1, health |
| GET | `/api/v1/system/status` | Get Status | api, api-v1, system |
| GET | `/api/v1/trade/events` | Get Trade Events | trade |
| GET | `/api/v1/trade/execution_spine` | Get Execution Spine Snapshot | trade |
| GET | `/api/v1/trades` | Get Trades | api, api-v1, trades |
| GET | `/api/v1/trades/review` | Get Trade Review | api, api-v1, trades |
| GET | `/api/v1/trades/statistics` | Get Trade Statistics | api, api-v1, trades |
| GET | `/metrics` | Get Metrics | metrics |
