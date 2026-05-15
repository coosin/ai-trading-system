# OpenClaw 对接与验收指南

本文面向外部控制面、值守机器人、MCP/CLI 工具和 Dashboard。接口细节见 [API_REFERENCE.md](./API_REFERENCE.md)，架构边界见 [STANDARD_DOMAIN_ARCHITECTURE.md](./STANDARD_DOMAIN_ARCHITECTURE.md)。

## 对接原则

- 新集成优先使用 `/api/v1/{domain}/...` 标准域接口。
- 只读巡检顺序不要硬编码，优先读取 `/api/v1/surface/registry` 或兼容 `/api/v1/modules/surface/registry`。
- 写入能力必须区分策略治理、学习归因和真实交易执行。
- 真实交易执行必须经过 `ExecutionGateway`，不能绕过单写者和风控门禁。
- 自动化脚本统一使用 `OPENCLAW_API_BASE`。

## 最小只读接入

```bash
OPENCLAW_API_BASE=${OPENCLAW_API_BASE:-http://127.0.0.1:8000}
curl -s "$OPENCLAW_API_BASE/api/v1/surface/registry"
curl -s "$OPENCLAW_API_BASE/api/v1/system/health"
curl -s "$OPENCLAW_API_BASE/api/v1/system/status"
curl -s "$OPENCLAW_API_BASE/api/v1/account/snapshot"
curl -s "$OPENCLAW_API_BASE/api/v1/commander/system-mastery?symbol=BTC/USDT"
curl -s "$OPENCLAW_API_BASE/api/v1/trades/lifecycle"
```

旧控制面如仍依赖 modules 能力，可读取：

```bash
curl -s "$OPENCLAW_API_BASE/api/v1/modules/surface/registry"
curl -s "$OPENCLAW_API_BASE/api/v1/modules/commander/capabilities"
curl -s "$OPENCLAW_API_BASE/api/v1/modules/commander/tool-contract"
```

## 外部系统推荐数据链路

1. `system.health`：确认进程和交易所基础绑定。
2. `surface.registry`：获取能力、推荐巡检顺序和核心路由。
3. `commander.system-mastery`：获取系统、账户、行情、决策、执行和收益闭环总览。
4. `account.snapshot`：读取余额与持仓。
5. `strategy.overview`：读取策略评分、筛选、审批和上线状态。
6. `execution.spine`：读取单写者、开仓门控和执行脊柱状态。
7. `trades.lifecycle`：读取开平仓、SLTP、拒单和后验归因。
8. `agents.effectiveness`、`learning.overview`：读取智能体和学习闭环效果。

## 写入能力

策略治理写入：

```bash
curl -s -X POST "$OPENCLAW_API_BASE/api/v1/strategy/{strategy_id}/approve"
curl -s -X POST "$OPENCLAW_API_BASE/api/v1/strategy/{strategy_id}/activate"
curl -s -X POST "$OPENCLAW_API_BASE/api/v1/strategy/{strategy_id}/deactivate"
```

学习与归因写入：

```bash
curl -s -X POST "$OPENCLAW_API_BASE/api/v1/learning/backfill-lessons"
curl -s -X POST "$OPENCLAW_API_BASE/api/v1/trades/backfill-trace-attribution"
```

交易执行写入不建议外部系统直接调用。若确需自动化执行，必须走系统现有 commander/ExecutionGateway 链路，并保留 `source`、审批状态、trace 和审计记录。

## 上线验收

```bash
python3 scripts/check_docs_runtime_consistency.py
pytest -q tests/unit/test_standard_domain_api.py
pytest -q tests/e2e/test_api_surface_commander_chain.py
curl -s "$OPENCLAW_API_BASE/api/v1/s1/verify"
```

验收通过标准：

- `/api/v1/system/health` 返回健康或可解释降级。
- `/api/v1/surface/registry` 能列出标准 domains 和 routes。
- `/api/v1/s1/verify` 不报告单写者或执行脊柱硬门禁失败。
- `commander.system-mastery` 能给出账户、行情、执行和优化建议。
- 写接口鉴权策略符合当前部署要求。

## 常见迁移

- `/api/v1/balance`、`/api/v1/positions` 迁移到 `/api/v1/account/snapshot`。
- `/api/v1/modules/commander/closed-loop-summary` 迁移到 `/api/v1/commander/closed-loop` 和 `/api/v1/trades/lifecycle`。
- `/api/v1/modules/surface/registry` 可继续作为兼容发现入口，但新系统应优先使用 `/api/v1/surface/registry`。

