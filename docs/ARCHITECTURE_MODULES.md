# 模块职责与 API 表面（2026-04）

本文档为开发与前后端对接的**单一结构参考**，与运行时一致路径以 `GET /api/v1/modules/surface/registry` 返回的 `catalog` 为准。

## 设计原则

1. **司令部主智能体**：统一入口 `process_user_command` → `CommanderAgentRuntime` → `AICommandExecutor` / 子专家。
2. **子专家服务化**：数据 / 分析 / 执行以 **invoke 契约** 对接，不必各挂一套对话。
3. **记忆共用**：`MemoryGateway` + tag/scope；写入策略遵守 S1/单写约定。
4. **API 发现**：`/api/v1/modules/surface/registry`（全表）+ `/surface/channels`（HTTP/WS/TG 约定摘要）。

## 编排与入口

| 组件 | 路径 / 类 | 职责 |
|------|-----------|------|
| MainController | `src/modules/main_controller.py` | 生命周期、事件、健康、配置、`execute_command`、`process_user_command` |
| CommanderAgentRuntime | `src/modules/commander_agent/runtime.py` | 阶段化回路、上下文组装、主链路执行 |
| AICommandExecutor | `src/modules/core/ai_command_executor.py` | 意图解析、交易/行情等指令、插件与记忆 scope |

## 统一 HTTP 前缀

| 前缀 | 用途 |
|------|------|
| `/api/v1/modules/*` | 模块控制、司令部、记忆、风控、策略、**surface/registry** |
| `/api/v1/trade/*` | 交易事件、执行脊柱 |
| `/api/v1/market/*` | 行情 / MI 视图 |
| `/api/v1/s1/*` | 全自动验收探针 |

### Surface 薄委托（已实现）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/modules/data/integration/health` | `DataIntegration.get_source_health_report` |
| GET | `/api/v1/modules/data/onchain/status` | 链上集成是否就绪、提供者数量 |
| GET | `/api/v1/modules/plugins/status` | 已加载插件列表摘要 |
| POST | `/api/v1/modules/intelligence/batch-analyze` | body: `{ "symbols": ["BTC/USDT", ...] }`，MI 多品种视图 |
| POST | `/api/v1/modules/execution/simulate-order` | body: `{ "symbol", "side", "size"|"quantity", "price"? }`，模拟盘 |

## 核心域（摘要）

- **数据**：`data/data_integration.py`、`data/data_source_hub.py` — 采集与聚合；`GET .../modules/data/hub/unified-snapshot` 为薄委托。
- **分析**：`core/market_intelligence_engine.py` — 视图与摘要；`GET .../market/symbol/{symbol}`。
- **执行**：`core/execution_verifier.py`、`core/execution_gateway.py`、`execution/trading_execution_engine.py` — 验证与下单脊柱。
- **策略**：`core/strategy_manager.py`、`research/strategy_research_pipeline.py`、`backtesting/backtest_engine.py`。
- **记忆**：`memory/memory_gateway.py`、`memory/memory_context_policy.py`。
- **技能**：`skills/*` — `GET/POST .../modules/skills/catalog|invoke`。
- **通知**：`notification/telegram_bot.py` — 与 `commander/dispatch` 同源链。

## 预留接口

- `GET /api/v1/modules/reserved/{domain}/ping` — 占位响应（`implemented: false`）。
- 注册表中 `status: reserved` 的路径为后续实现预留，**勿依赖当前行为**。

## 全量测试（全链路烟测）

- **单元 + E2E**：在项目根执行 `./scripts/run_full_test_suite.sh`（创建 `.venv_test`、安装测试依赖、运行 `pytest tests/ --no-cov`）。
- **E2E 范围**：`tests/e2e/test_api_surface_commander_chain.py` 覆盖 Surface 注册表、`commander/dispatch`、`commander/audit`、`s1/verify` 等 HTTP 链（Mock `MainController`，不连交易所）。
- **覆盖率**：需要 HTML/终端覆盖率时，在已激活 venv 下执行  
  `PYTEST_ADDOPTS='' python -m pytest tests/`（使用 `pyproject.toml` 默认 `--cov=src`）。

## 相关文档

- 记忆库使用：`docs/memory/MEMORY_LIBRARY_GUIDE.md`
- 契约版本：见 `surface/registry` 中 `contract_version`
