# 变更记录

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
