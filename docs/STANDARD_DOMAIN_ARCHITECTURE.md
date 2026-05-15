# OpenClaw 标准域架构

本文档定义当前系统的公共 API 架构边界。新增能力必须优先落在 `/api/v1/{domain}/...` 标准域下，旧 modules v1 前缀只作为兼容能力面和内部控制面保留。

## 当前标准域

| Domain | 责任 |
| --- | --- |
| `system` | 健康、状态、接口发现 |
| `account` | 账户余额、持仓、账户快照 |
| `market` | 单品种行情、ticker、订单簿摘要 |
| `data` | 多源数据融合与数据质量 |
| `strategy` | 策略列表、评分、审批、启停、研究发布状态 |
| `risk` | 风控状态、红线、仓位限制 |
| `execution` | ExecutionGateway 执行脊柱、单写者、门控状态 |
| `trades` | 交易生命周期、trace 归因、开平仓后验 |
| `memory` | 记忆层和知识库状态 |
| `learning` | 复盘、课程化经验、调优反馈 |
| `agents` | 智能体 verdict、覆盖率、有效性 |
| `commander` | 跨域聚合、系统掌控、闭环诊断、工作流解释 |
| `plugins` | 插件、技能、扩展注册表 |

## 分层规则

- API 层只做协议适配、参数校验和响应包装，不承载业务决策。
- 单域查询放在对应 domain service；跨域聚合放在 `commander`。
- 新公共能力必须在 `src/modules/api/standard_registry.py` 注册唯一 capability。
- 新标准域路由必须由对应 `src/modules/<domain>/api` 模块提供，并由 `attach_standard_domain_apis()` 挂载。
- 交易写入必须经过 `ExecutionGateway`，不能在 API、策略、智能体或脚本中直连交易所下单。
- 旧 modules 路由可继续提供深诊断和兼容能力，但不得成为新增公共 API 的唯一入口。

## 读路径

推荐读路径是：

1. `/api/v1/surface/registry` 获取标准域和 capability。
2. `/api/v1/system/health`、`/api/v1/system/status` 确认可用性。
3. `/api/v1/commander/system-mastery` 获取全局总览。
4. `/api/v1/account/snapshot`、`/api/v1/data/snapshot`、`/api/v1/strategy/overview` 分域定位。
5. `/api/v1/trades/lifecycle`、`/api/v1/execution/spine` 追踪交易闭环。

机器可读的完整只读巡检顺序由 `src/modules/api/route_catalog.py` 维护，并通过 surface registry 暴露。

## 写路径

写路径分为三层：

- 策略治理写入：`/api/v1/strategy`、`/api/v1/strategy/{strategy_id}/approve`、`activate`、`deactivate`。
- 学习与归因写入：`/api/v1/learning/backfill-lessons`、`/api/v1/trades/backfill-trace-attribution`。
- 交易执行写入：必须进入 `ExecutionGateway`，受 `ai_brain.single_write_owner=ai_core`、鉴权、人工审批、对账保护和仓位门控约束。

## 当前交易门控

生产配置的关键交易约束来自 `config/config.yaml`：

- `trading.position_limits.symbol_max_margin_ratio=0.2`：单币种最大保证金占用为 available 的 20%。
- `max_same_direction_positions=5`：long/short 分别最多 5 个同向 slot。
- `max_positions_oneway=5`、`max_positions_hedge=8`、`hard_max_positions=8`。
- 第 1-5 笔开仓/加仓置信度门槛：`0.72 / 0.77 / 0.82 / 0.87 / 0.92`。
- `ai_brain.single_write_owner=ai_core`：默认只有 ai_core 是交易写入所有者。
- `replace_worst_min_confidence=0.95`：满仓替弱必须达到更高置信度。

这些规则由 ai_core 与 ExecutionGateway 双层执行；ExecutionGateway 是最终硬门禁。

## 兼容与迁移

- 外部新系统只应依赖标准域接口。
- 老前端、脚本和 MCP fallback 可继续读取 `/api/v1/modules/surface/*`。
- 旧 `/api/v1/balance`、`/api/v1/positions`、`/api/v1/market/ticker/*` 仍保留，但文档和新脚本应迁移到标准域。
