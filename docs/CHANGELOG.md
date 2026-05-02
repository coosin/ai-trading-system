# 变更记录

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
- **Docker**：恢复/提供根目录 `docker-compose.yml`，默认 `MODE`/`TRADING_MODE`/`SYSTEM_MODE` 为 **simulation**（部署实盘前请在 `.env` 显式覆盖）；挂载 `./config:/app/config`。
- **测试**：Pytest 9 要求异步 fixture 使用 `pytest_asyncio.fixture`；`NaturalLanguageInterface` 单测改为 `IsolatedAsyncioTestCase`。
- **工具**：`src/web/app.py` 改为读取主 YAML；新增 `scripts/network_connectivity_smoke.py`。
- **文档**：补回 `docs/ENGINEERING.md`、`docs/CHANGELOG.md`、`docs/memory/MEMORY_LIBRARY_GUIDE.md`；更新 `OPERATIONS`、`DEVELOPMENT`、`README` 索引；`status.sh` / `check-dual-system.sh` 改为检查 `config/config.yaml`。
- **仓库**：新增根 `.gitignore`（含 `config/local.*`、`data/config/local.*` 等）。
