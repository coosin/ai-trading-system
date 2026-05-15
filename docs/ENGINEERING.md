# OpenClaw 工程架构

本文描述当前仓库的运行架构、配置模型和模块边界。运维见 [OPERATIONS.md](./OPERATIONS.md)，API 见 [API_REFERENCE.md](./API_REFERENCE.md)，标准域规则见 [STANDARD_DOMAIN_ARCHITECTURE.md](./STANDARD_DOMAIN_ARCHITECTURE.md)。

## 运行时主链路

```text
src/main.py
  -> ConfigManager
  -> MainController
  -> APIServer(FastAPI)
  -> AI / data / risk / execution / memory / learning modules
```

核心组件：

| 组件 | 路径 | 责任 |
| --- | --- | --- |
| 进程入口 | `src/main.py` | 初始化配置、主控制器、API 和主循环 |
| 主控制器 | `src/modules/main_controller.py` | 装配交易所、AI、风控、记忆、学习、监控 |
| API 服务 | `src/modules/api/server.py` | FastAPI 应用、兼容路由、标准域挂载 |
| 标准域注册 | `src/modules/api/standard_registry.py` | `/api/v1/{domain}/...` capability 清单 |
| 路由目录 | `src/modules/api/route_catalog.py` | 只读巡检链和核心 HTTP catalog |
| 执行脊柱 | `src/modules/core/execution_gateway.py` | 单写者、交易门禁、下单、对账、审计 |
| 仓位限制 | `src/modules/core/trading_limits.py` | 统一仓位上限和分层置信度解析 |
| AI 交易引擎 | `src/modules/core/ai_trading_engine.py` | 决策、仓位计算、入场质量门控 |

## API 架构

当前公共接口标准化为 `/api/v1/{domain}/...`：

- 标准域 API 由 `src/modules/<domain>/api` 模块提供。
- 标准能力由 `standard_registry.canonical_routes()` 注册。
- `server.py` 初始化时调用 `attach_standard_domain_apis()` 挂载。
- modules v1 前缀仍保留为兼容能力面、深诊断和 MCP manifest 来源。

新增公共能力时必须同步 domain API、domain service、standard registry、文档和测试。

## 配置模型

主配置文件：

- `config/config.yaml`：仓库维护的主配置。
- `config/local.yaml`：本机覆盖，勿提交。
- `.env`：密钥、代理、本机环境变量。

环境变量可用 `OPENCLAW__section__key__nested=value` 覆盖 YAML。旧 `TRADING_` 前缀仅作兼容，不建议新增。

`ConfigManager` 默认扫描顺序：

```text
data/config -> config -> /app/data/config -> /app/config
```

同一 key 后加载者覆盖先加载者。生产建议只维护一份 `config/config.yaml`，不要在 `data/config` 再放业务主配置。

## 当前交易治理

交易执行是系统最高风险路径，当前硬规则如下：

- `ai_brain.primary_controller=ai_core`。
- `ai_brain.single_write_owner=ai_core`。
- `ai_brain.enable_secondary_controller=false`。
- `ai_brain.policy.allow_system_open=false`。
- `ai_brain.policy.enable_replace_worst_on_full_positions=true`。
- `ai_brain.policy.replace_worst_min_confidence=0.95`。
- `trading.position_limits.symbol_max_margin_ratio=0.2`。
- `max_same_direction_positions=5`。
- `max_positions_oneway=5`、`max_positions_hedge=8`、`hard_max_positions=8`。
- 第 1-5 笔开仓/加仓置信度：`0.72 / 0.77 / 0.82 / 0.87 / 0.92`。

`ai_trading_engine` 可以做入场筛选，但 `ExecutionGateway` 是最终硬门禁。

## 模块边界

| 模块 | 边界 |
| --- | --- |
| API | 协议适配、参数校验、响应包装；不堆业务决策 |
| Commander | 跨域聚合、诊断、系统掌控和闭环解释 |
| Strategy | 策略评分、审批、启停和研究发布状态 |
| Risk | 风控红线、账户风险、仓位限制 |
| Execution | 单写者、开平仓、失败记录、执行审计 |
| Trades | 生命周期、拒单后验、trace 归因 |
| Memory/Learning | 经验、复盘、课程化教训和调优反馈 |
| Agents | 智能体 verdict、建议和有效性统计 |
| Plugins | 插件和技能注册 |

## 持久化与目录

- `config/`：主配置和本机覆盖模板。
- `data/`：运行数据、交易记录和本地状态。
- `logs/`：主日志、健康审计、交易所事实账本。
- `runtime/`：PID 和运行期短状态。
- `scripts/`：启动、验收、巡检、迁移脚本。
- `tests/`：单元、集成和 e2e 测试。

## 可观测性

基础接口：

- `/api/v1/system/health`
- `/api/v1/system/status`
- `/api/v1/surface/registry`
- `/api/v1/s1/verify`
- `/api/v1/execution/spine`
- `/api/v1/trades/lifecycle`
- `/metrics`

日志：

- `logs/app.log`
- `logs/exchange_sync/exchange_truth.jsonl`
- `logs/health/health_suite_summary.md`

## 已弃用方向

- 不再新增 Flask 配置写接口。
- 不再把新增公共能力只挂到 modules v1 前缀下。
- 不再让脚本绕过 API 和 ExecutionGateway 直接执行交易写入。
- 不再依赖根目录旧 `openclaw-trading.json` 或多份分散 YAML 作为主配置。
