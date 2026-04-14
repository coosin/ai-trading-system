# 全智能量化交易系统API
量化交易系统的RESTful API接口
**版本:** 1.0.0

**在线文档（若服务已启动）:** `http://<host>:8000/docs`（Swagger UI）、`http://<host>:8000/redoc`

**机器可读规范（与线上一致，由运行中服务导出）:** 同目录下 [`API_OPENAPI_FULL.json`](./API_OPENAPI_FULL.json)（OpenAPI 3.1，约 160 条路径；含请求体、查询参数、422 校验模型等）。

## 升级后实时链路（2026-04-13）

以下为当前版本实测可用的“实时信息与通知”主链路，优先作为前端与司令部集成基线：

- **司令部统一入口（A 接口）**
  - `POST /api/v1/modules/commander/dispatch`
  - body: `{"message":"...", "source":"api_chat|telegram|control_hub|..." }`
  - 用途：统一接收开仓/平仓/行情问询/巡检指令。

- **交易/风控事件流（前端与外部 API 推荐）**
  - `GET /api/v1/trade/events?limit=...`
  - 事件类型含：`trade.fill`（开平仓成交）、`trade.position`（含 `sltp.create` / `sltp_stop_loss_triggered` 等）、`market.update`（行情判断与质量摘要）。
  - 该接口为环形缓冲读取，适合作为前端轮询与外部系统对账源。

- **执行脊柱与审计快照**
  - `GET /api/v1/trade/execution_spine`
  - `GET /api/v1/modules/execution/production-audit`
  - 用途：读取最新一笔开平仓来源、原因、成败、策略单写入状态（S1）与 SLTP 统计。

- **行情与判断输出**
  - `GET /api/v1/market/symbol/{symbol}`
  - `GET /api/v1/market/state`
  - `GET /api/v1/modules/data/hub/unified-snapshot`
  - 用途：提供实时行情、质量分、执行成本、风险建议与“是否可交易”判断依据。

- **模拟盘联调入口（升级验证用）**
  - `POST /api/v1/modules/execution/simulate-order`
  - 用于压测行情波动、触发止盈止损链路、验证通知与事件输出。

### 二次验收快照（2026-04-13 21:31 UTC+8）

以下接口已在当前运行环境复核通过（HTTP 200 且返回结构有效）：

- **系统与链路**
  - `GET /health` -> `healthy`
  - `GET /api/v1/s1/verify` -> `all_passed=true`
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

- **迁移兼容接口说明（重要）**
  - `GET /api/v1/data-fusion/analyze{,/symbol}` 当前为兼容路由，返回 `status=deprecated` 与迁移提示。
  - 生产调用请切换至：`GET /api/v1/market/symbol/{symbol}` 与 `POST /api/v1/modules/intelligence/batch-analyze`。

### WebSocket（OpenAPI 中不展开）

- **URL:** `ws://<host>:8000/ws`（生产若走 HTTPS 则为 `wss://`）
- **用途:** 实时推送；连接后发送 JSON，支持 `subscribe` / `unsubscribe` / `heartbeat`（与 `WebSocketEventType` 一致，详见 `src/modules/api/server.py` 中 `_handle_websocket_connection`）。
- **频道匹配:** 支持精确频道与前缀通配，例如 `trade.*`、`market.*`。
- **建议生产基线:** WebSocket 与 `GET /api/v1/trade/events` 并用（前者实时、后者补偿与回放），避免前端因连接抖动丢关键成交/止损事件。
- **出站消息约定（与 REST 对齐的兼容补齐）:** 服务端在保留原有字段（如 `type`、`channel`、`data`、`connection_id`、`channels`）的同时，为每条出站 JSON 补齐 `ok`、`success`、`status`、`timestamp` 等标准字段（实现上复用与 HTTP 相同的 `_normalize_api_payload` 逻辑）。

### REST JSON 网关标准化

- **范围:** 以 `/api` 为前缀的路径，响应体为 JSON 时，由中间件在**不删除原有字段**的前提下补齐 `ok`、`success`、`status`、`message`（按需）、`timestamp`。
- **响应头:** `X-OpenClaw-Standardized: 1` 表示该响应已按上述规则规范化。

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

### 代码中存在但未挂到当前主应用的模块

仓库内另有 `risk_api.py`、`backtest_api.py` 等路由定义；**当前 `APIServer` 未 `include_router` 时不会出现在上述 OpenAPI 中**。以 `GET /openapi.json` 为准。

---

## 接口一览

| 方法 | 路径 | 摘要 | Tags |
|------|------|------|------|
| GET | `/api/health` | Health Check | api, health |
| GET | `/api/metrics` | Get Metrics | api, metrics |
| GET | `/api/status` | Get Status | api, system |
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
| DELETE | `/api/v1/commander` | Commander Mirror Root | api, api-v1, commander |
| GET | `/api/v1/commander` | Commander Mirror Root | api, api-v1, commander |
| HEAD | `/api/v1/commander` | Commander Mirror Root | api, api-v1, commander |
| OPTIONS | `/api/v1/commander` | Commander Mirror Root | api, api-v1, commander |
| PATCH | `/api/v1/commander` | Commander Mirror Root | api, api-v1, commander |
| POST | `/api/v1/commander` | Commander Mirror Root | api, api-v1, commander |
| PUT | `/api/v1/commander` | Commander Mirror Root | api, api-v1, commander |
| GET | `/api/v1/commander/_audit` | Commander Mirror Audit | api, api-v1, commander |
| DELETE | `/api/v1/commander/{path}` | Commander Mirror | api, api-v1, commander |
| GET | `/api/v1/commander/{path}` | Commander Mirror | api, api-v1, commander |
| HEAD | `/api/v1/commander/{path}` | Commander Mirror | api, api-v1, commander |
| OPTIONS | `/api/v1/commander/{path}` | Commander Mirror | api, api-v1, commander |
| PATCH | `/api/v1/commander/{path}` | Commander Mirror | api, api-v1, commander |
| POST | `/api/v1/commander/{path}` | Commander Mirror | api, api-v1, commander |
| PUT | `/api/v1/commander/{path}` | Commander Mirror | api, api-v1, commander |
| GET | `/api/v1/control-center/state` | Get Control Center State | api, api-v1, control-center |
| GET | `/api/v1/data-fusion/analyze` | Analyze Market Q | api, api-v1, data-fusion |
| GET | `/api/v1/data-fusion/analyze/{symbol}` | Analyze Market | api, api-v1, data-fusion |
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
| GET | `/api/v1/health` | Health Check V1 | api, api-v1, health |
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
| GET | `/api/v1/status` | Get Status | api, api-v1, system |
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
| GET | `/api/v1/trading/history` | Get Trading History Compat | api, api-v1, trades |
| POST | `/auth/login` | Login | auth |
| POST | `/auth/logout` | Logout | auth |
| GET | `/auth/me` | Get Current User | auth |
| POST | `/auth/refresh` | Refresh Token | auth |
| GET | `/health` | Health Check | health |
| GET | `/metrics` | Get Metrics | metrics |
