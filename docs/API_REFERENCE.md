# OpenClaw Trading API Reference

本文档对齐当前代码中的标准域接口。运行时 OpenAPI 仍是最终权威来源：

```bash
curl -s ${OPENCLAW_API_BASE:-http://127.0.0.1:8000}/openapi.json
```

## API 基线

- 推荐基址环境变量：`OPENCLAW_API_BASE`。
- 兼容回退变量：`ACCEPTANCE_BASE`、`BASE_URL`。
- 标准路径形态：`/api/v1/{domain}/...`。
- 标准接口注册来源：`src/modules/api/standard_registry.py`。
- 标准路由挂载入口：`src/modules/api/server.py` 调用 `attach_standard_domain_apis()`。
- 兼容能力面：modules 与 trade 的 v1 前缀以及旧 `/api/v1/balance`、旧 `/api/v1/positions` 仍存在，但新对接不得以旧路径作为主入口。

## 发现与巡检

| Method | Path | 用途 |
| --- | --- | --- |
| GET | `/api/v1/surface/registry` | 标准域、能力、核心路由和只读巡检链 |
| GET | `/api/v1/modules/surface/registry` | 兼容能力面注册表，含 `read_pipeline` 与 `api_base_env` |
| GET | `/api/v1/modules/surface/mcp-manifest` | MCP/CLI 工具清单 |
| GET | `/api/v1/system/health` | 进程、交易所绑定与基础健康 |
| GET | `/api/v1/system/status` | 模块运行摘要 |
| GET | `/api/v1/s1/verify` | 执行脊柱、单写者和核心门禁自检 |

推荐只读巡检顺序由 `src/modules/api/route_catalog.py` 维护，并通过 surface registry 暴露。脚本不要硬编码散落路径。

## 标准域接口

| Capability | Method | Path | 用途 |
| --- | --- | --- | --- |
| `system.health` | GET | `/api/v1/system/health` | 系统健康 |
| `system.status` | GET | `/api/v1/system/status` | 系统状态 |
| `surface.registry` | GET | `/api/v1/surface/registry` | 标准接口发现入口 |
| `account.snapshot` | GET | `/api/v1/account/snapshot` | 账户余额与持仓 |
| `market.snapshot` | GET | `/api/v1/market/snapshot` | 单品种行情快照 |
| `data.snapshot` | GET | `/api/v1/data/snapshot` | 多源数据快照 |
| `risk.status` | GET | `/api/v1/risk/status` | 风控状态 |
| `execution.spine` | GET | `/api/v1/execution/spine` | ExecutionGateway 单写执行脊柱状态 |
| `memory.overview` | GET | `/api/v1/memory/overview` | 记忆与知识层状态 |
| `learning.overview` | GET | `/api/v1/learning/overview` | 学习复盘与调优状态 |
| `learning.backfill_lessons` | POST | `/api/v1/learning/backfill-lessons` | 将后验复盘候选写入学习层 |
| `agents.effectiveness` | GET | `/api/v1/agents/effectiveness` | 智能体有效性 |
| `agents.advisory` | POST | `/api/v1/agents/advisory-snapshot` | 智能体当前判定 |
| `plugins.registry` | GET | `/api/v1/plugins/registry` | 插件与技能注册表 |

## 策略域

| Capability | Method | Path | 用途 |
| --- | --- | --- | --- |
| `strategy.overview` | GET | `/api/v1/strategy/overview` | 策略运行、评分与筛选总览 |
| `strategy.list` | GET | `/api/v1/strategy/list` | 策略列表 |
| `strategy.create` | POST | `/api/v1/strategy` | 创建策略 |
| `strategy.update` | PUT | `/api/v1/strategy/{strategy_id}` | 更新策略 |
| `strategy.delete` | DELETE | `/api/v1/strategy/{strategy_id}` | 删除策略 |
| `strategy.approve` | POST | `/api/v1/strategy/{strategy_id}/approve` | 审批策略 |
| `strategy.activate` | POST | `/api/v1/strategy/{strategy_id}/activate` | 启用策略 |
| `strategy.deactivate` | POST | `/api/v1/strategy/{strategy_id}/deactivate` | 停用策略 |

策略研究与上线受 `config/config.yaml -> research.rollout` 控制。当前配置允许发布后自动进入 paper 阶段，但 `force_paper_stage=true`，不会越过 paper 直接实盘激活。

## 交易闭环

| Capability | Method | Path | 用途 |
| --- | --- | --- | --- |
| `commander.system_mastery` | GET | `/api/v1/commander/system-mastery` | 全系统单接口总览 |
| `commander.closed_loop` | GET | `/api/v1/commander/closed-loop` | 司令闭环状态 |
| `commander.trading_workflow` | GET | `/api/v1/commander/trading-workflow` | 交易全链路、原因与优化动作 |
| `trades.lifecycle` | GET | `/api/v1/trades/lifecycle` | 开仓、平仓、SLTP、拒单后验 |
| `trades.backfill_trace_attribution` | POST | `/api/v1/trades/backfill-trace-attribution` | 回填平仓记录 trace 归因 |

交易写路径不在标准域中直接裸露。真实交易写入必须经过 `ExecutionGateway`，并受单写者、半自动/手动审批、分层开仓置信度、仓位上限、冷却、对账保护和鉴权共同约束。

## 关键兼容接口

| Method | Path | 用途 |
| --- | --- | --- |
| GET | `/api/v1/exchanges` | 交易所连接态 |
| GET | `/api/v1/balance` | 旧账户余额入口，推荐迁移到 `/api/v1/account/snapshot` |
| GET | `/api/v1/positions` | 旧持仓入口，推荐迁移到 `/api/v1/account/snapshot` |
| GET | `/api/v1/market/ticker` | 旧 ticker query 入口 |
| GET | `/api/v1/market/ticker/{symbol}` | 旧 ticker path 入口 |
| GET | `/api/v1/market/klines` | K 线兼容入口 |
| GET | `/api/v1/market/symbol/{symbol}` | 单品种 Market Intelligence 视图 |
| GET | `/api/v1/data-hub/status` | 数据源中心状态 |
| GET | `/api/v1/data-hub/unified-snapshot` | 数据融合快照 |
| GET | `/api/v1/monitoring/alerts` | 监控告警 |
| GET | `/api/v1/auth/status` | 鉴权策略状态 |
| GET | `/api/v1/auth/write-policy` | 写接口鉴权策略 |

## 鉴权与写保护

- 读接口默认允许本机值守脚本直接访问。
- 受保护写接口默认要求 token，角色默认为 `admin`。
- 受保护前缀包括 `/api/v1/modules`、`/api/v1/monitoring`、`/api/v1/commander`、`/api/v1/trade` 等控制面写路径。
- WebSocket `/ws` 默认要求 token。
- 新写接口应优先进入标准域服务或 `commander` 编排层，真实交易执行仍必须进入 `ExecutionGateway`。

## 响应与降级约定

- HTTP JSON 经中间件补齐标准字段，调用方应优先看 `success` / `status` / `data` / `error`。
- 降级不是空响应：超时、交易所不可达、缓存回退等应返回明确 `hint`、`degraded` 或结构化错误。
- 账户/持仓权威来源是交易所；控制面可使用缓存与短超时直拉回退，但必须可解释。
