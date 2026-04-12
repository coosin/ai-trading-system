# OpenClaw Trading — 工程文档

**版本**: 与仓库 `main` 同步  
**适用范围**: 容器化部署（Docker Compose）、Python 3.12 运行时、OKX v5 主链路  

本文档描述**当前代码与配置的真实结构**，作为开发、运维与对接的单一事实来源（与 OpenAPI 并列时，以 OpenAPI 为接口字段级权威）。

---

## 1. 系统目标与边界

- **目标**: 全链路量化交易栈 — 行情采集、情报聚合、AI 决策辅助、统一执行脊柱（S1）、风控/止盈止损、记忆与通知。
- **交易所主适配**: OKX（REST + 可选 WebSocket Hub）；可扩展其他交易所适配器。
- **部署形态**: 推荐 **仅 Docker** 运行：`trading-system` + `redis`；源码通过卷挂载热加载（见 `docker-compose.yml`）。

---

## 2. 启动流程（镜像 → 运行态）

### 2.1 容器入口

1. **镜像 CMD**: `./start_production.sh`  
2. **脚本**（`start_production.sh`）: 读取环境变量 `MODE`（默认由 Compose 注入），执行  
   `python3 src/main.py --mode "$MODE" --port "$API_PORT"`  
   （注：`main.py` 当前以环境变量与配置管理器为主；`MODE` 通过 Compose / `.env` 注入。）
3. **`src/main.py`**  
   - `load_dotenv(.env)`  
   - `ConfigManager.initialize()` → 加载 `config/`、`data/config/`、**`OPENCLAW__*` 环境嵌套键**  
   - `MainController.initialize()` — 装配子系统（事件总线、LLM、交易所、记忆网关、API 等）  
   - `APIServer.initialize()` + `start()` — 绑定 `0.0.0.0:8000`（默认）  
   - `MainController.start_system()` — 业务循环、同步任务、监控等  

### 2.2 健康与降级

- **Docker HEALTHCHECK**: `curl -f http://localhost:8000/health`  
- **启动顺序**: Compose `depends_on: redis (healthy)` 后再起交易容器。  
- **典型失败**: 代理不可达、OKX DNS/TLS、Redis 未就绪 — 见 `OPERATIONS.md`。

---

## 3. 逻辑架构（司令部中心化编排）

```
[ Telegram / HTTP / 前端 ]
           │
           ▼
  CommanderAgentRuntime  ←── process_user_command(command, source)
  (intake → context → route → execute → persist)
           │
     ┌─────┴─────┬──────────────┬────────────────┐
     ▼           ▼              ▼                ▼
 AICommandExecutor   specialists.*   get_primary_ai_brain   NaturalLanguageInterface
     │                    │              (fallback)              (fallback)
     └──────────┬─────────┴──────────────┴────────────────────┘
                ▼
        MainController 子系统
  (策略 / 执行网关 S1 / 风控 SLTP / 行情 MI / 数据 Hub / 记忆网关 / 通知 …)
                ▼
           OKXExchange (+ OKXWebSocketHub 可选)
```

- **司令部**: `src/modules/commander_agent/runtime.py` — 统一对话与指令入口；记忆写入 `memory_gateway`（用户轮/助手轮）。  
- **子智能体**: `src/modules/commander_agent/specialists.py` — 显式路由 `司令部子任务:<id>:...`。  
- **模块控制面 API**: `src/modules/api/module_control_api.py` — `/api/v1/modules/commander/*`（snapshot、dispatch、audit、memory 等）。  
- **实时消息**: 与 HTTP 同源应走 `POST /api/v1/modules/commander/dispatch`，`source` 区分渠道（如 `telegram`）。

能力清单（机器可读）: `GET /api/v1/modules/commander/capabilities`  
全链路审查: `GET /api/v1/modules/commander/audit`；增强质检: `?enrich=true`（含第三方限速诊断、记忆摘要）。

---

## 4. 执行脊柱 S1（单写者）

实盘开/平仓须经统一链路，避免绕开审计与幂等：

- **意图**: `AICoreDecisionEngine`（可配置 `ai_brain.primary_controller`）  
- **执行**: `ExecutionVerifier` → `ExecutionGateway` → `OKXExchange`  
- **止盈止损**: `StopLossTakeProfitManager` 触发平仓仍走 S1  

详细契约（历史文档合并摘要）见下节引用；完整约束以代码 `ExecutionGateway`、`ai_brain` 配置为准。

**原则**: `ai_brain.single_write_owner` 限制可写入源；扫描器/主动模块默认不自动开仓除非显式策略放行。

---

## 5. 仓库目录（代码）

| 路径 | 说明 |
|------|------|
| `src/main.py` | 进程入口、日志、ConfigManager、MainController、API 生命周期 |
| `src/modules/main_controller.py` | 主控制器：子系统装配、状态、账户同步、司令部委托 |
| `src/modules/core/` | 配置、AI 执行器、交易引擎、市场情报、风控相关核心逻辑 |
| `src/modules/commander_agent/` | 司令部运行时与子智能体 |
| `src/modules/exchanges/` | `okx.py`、`okx_websocket.py` |
| `src/modules/api/` | FastAPI 路由聚合（`server.py`、`module_control_api.py` 等） |
| `src/modules/data/` | `data_source_hub.py`、`third_party_data_integrator.py` 等 |
| `config/` | 默认 YAML 配置（合并进 ConfigManager） |
| `data/config/` | 运行时覆盖配置（卷挂载，优先级高） |
| `scripts/` | 部署、验收、清理、网络基线脚本 |
| `docker-compose.yml` | 服务定义、代理、OKX/司令部相关环境默认值 |

---

## 6. 配置与环境变量

### 6.1 层次

1. 内置默认（`src/modules/core/openclaw.embedded.yml`，由 `config/openclaw.yml` 经 `scripts/generate_openclaw_yaml.py` 同步）  
2. 各配置目录内 `default.*` → `openclaw.*` → 其它片段 → `local.*`  
3. 环境变量 **`OPENCLAW__section__key`**（双下划线分段，见 `config_manager.py`）  
4. Docker Compose `environment` 覆盖 `.env` 中同名键（Compose 行为以实际版本为准）

### 6.2 运行模式

- **`MODE`**: `live_trading` | `simulation` | `paper_trading` | `backtest`（`start_production.sh`）  
- **`OPENCLAW__trading__mode`**: 与配置 `trading.mode` 对齐（Compose 可注入）  
- **`OKX_TESTNET`**: `0` 主网；`1` 模拟盘（REST 头 `x-simulated-trading`）

### 6.3 OKX / WebSocket（摘要）

- `OPENCLAW_OKX_*`: 并发、间隔、重试、仅代理模式  
- `OPENCLAW_OKX_WS_ENABLED`、`OPENCLAW_OKX_WS_TICKER_*`: 公共 tickers / 快路径  

### 6.4 第三方数据源限速

- `OPENCLAW_THIRD_PARTY_MIN_INTERVAL_SEC`、`OPENCLAW_THIRD_PARTY_429_*`、`OPENCLAW_REDDIT_SUBREDDIT_PAUSE_SEC`  
- 诊断: `ThirdPartyDataIntegrator.get_diagnostics()` → 司令部 `audit?enrich=true` / `snapshot` 内 `data_hub.third_party.diagnostics`

### 6.5 司令部

- `OPENCLAW_COMMANDER_MINIMAL_MODE`、`OPENCLAW_COMMANDER_GROUNDED_CHAT`、`OPENCLAW_COMMANDER_HONESTY_STRICT`  
- `OPENCLAW_COMMANDER_ACTIVE_MEMORY`、`OPENCLAW_COMMANDER_UNRESTRICTED`  

完整模板: **`.env.example`**。

---

## 7. 对外对接关系

| 对接 | 模块/入口 | 说明 |
|------|-----------|------|
| OKX REST/WS | `OKXExchange`, `OKXWebSocketHub` | 代理与 `www.okx.com`；v5 路径 |
| Redis | `cache` / 事件 | Compose 服务名 `redis` |
| LLM 提供商 | `enhanced_llm_manager` | 多模型，API Key 自环境变量 |
| Telegram | `telegram_bot` | 配置 `config`/数据配置；消息应汇入 `process_user_command` |
| 第三方舆情 | `third_party_data_integrator` | Reddit/新闻/恐惧贪婪等，带限速 |
| 前端 | 静态 `frontend/dist` + API | 同源 API 前缀 `/api` |

---

## 8. API 总览

**权威**: `GET /openapi.json`、Swagger UI `/docs`。

### 8.1 常用前缀

| 前缀 | 用途 |
|------|------|
| `/health` | 进程健康 |
| `/api/v1/modules/` | 模块控制、司令部、surface、风险、策略辅助接口 |
| `/api/v1/market/`、`/api/v1/trade/` | 行情与交易相关封装 |
| `/api/v1/monitoring/` | 监控、主动 AI 状态等 |
| `/api/v1/commander` | 司令部镜像/兼容路由（见 OpenAPI） |
| `/api/v1/s1/verify` | S1 探针（脚本/监控） |

### 8.2 司令部（模块控制下）

- `GET .../commander/snapshot` — 快速/完整快照  
- `POST .../commander/dispatch` — body: `message`, `source`  
- `GET .../commander/audit` — 链路检查；`enrich=true` 附加诊断  
- `GET .../commander/capabilities` — 能力与子系统布尔标记  
- `GET .../commander/memory/status` — 记忆网关统计  

**注意**: Surface 类路径在 **`/api/v1/modules/surface/*`**，不是 `/commander/surface/*`。

---

## 9. 脚本与运维入口

| 脚本 | 用途 |
|------|------|
| `scripts/deploy_production_stack.sh` | build + up + 健康等待 + OKX 验收 |
| `scripts/verify_okx_container.sh` | 容器内 health / exchanges / ticker / 日志 / 单测片段 |
| `scripts/check_trading_host_health.sh` | 宿主机巡检 |
| `scripts/cleanup_trading_workspace.sh` | 日志与缓存清理 |
| `scripts/production_network_baseline.py` | 网络/代理基线检查或应用 |

---

## 10. 记忆系统

- **网关**: `MemoryGateway`（主控制器持有 `memory_gateway`）  
- **运维说明**: `docs/memory/MEMORY_LIBRARY_GUIDE.md`  
- **司令部侧**: `active_memory_block`、对话 scope `channel:{source}`  

---

## 11. 测试

- 全量: `./scripts/run_full_test_suite.sh`（宿主机 `.venv_test`）  
- 容器内: 挂载 `./tests` 时可 `pytest /app/tests/...`（见 `docker-compose.yml`）  

部分异步测试与 pytest-asyncio 版本存在兼容性，以 CI/本地输出为准。

---

## 12. 参考阅读

- **OKX 字段对照**: [OKX_SOURCE_REFERENCE_MAP.md](./OKX_SOURCE_REFERENCE_MAP.md)  
- **运维细节**: [OPERATIONS.md](./OPERATIONS.md)  

---

*文档维护: 架构或默认部署变更时，请同步更新本节与 `docs/CHANGELOG.md`。*
