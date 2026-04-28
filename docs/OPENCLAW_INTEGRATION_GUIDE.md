# OpenClaw 对接手册（生产版）

本文档用于把 OpenClaw 客户端/智能体接入当前交易系统，作为统一控制与编排入口。

> 运行地址建议使用变量：`BASE_URL=${BASE_URL:-http://127.0.0.1:8000}`  
> 鉴权建议使用变量：`TOKEN=${OPENCLAW_API_TOKEN:-<admin_jwt>}`  
> Docker 环境可覆盖为 `http://localhost:8000` 或实际反向代理地址。

---

## 1. 对接目标

- 统一入口：所有指令走 `commander/dispatch`
- 统一读面：状态、能力、工具契约、审计流可读取
- 统一补偿：实时消息 + 事件流回放并用
- 统一安全：托管模式、风控红线、治理审计可追溯

---

## 2. 上线前最小检查

```bash
BASE_URL=${BASE_URL:-http://127.0.0.1:8000}
curl -s "$BASE_URL/api/v1/system/health"
curl -s "$BASE_URL/api/v1/s1/verify"
curl -s "$BASE_URL/api/v1/modules/commander/audit?enrich=true"
```

通过标准：

- `/api/v1/system/health` 返回 `success=true` 且 `data.status=healthy`
- `s1/verify.all_passed=true`
- `commander/audit.all_passed=true`

---

## 3. OpenClaw 必接读取接口

```bash
curl -s "$BASE_URL/api/v1/modules/commander/capabilities"
curl -s "$BASE_URL/api/v1/modules/commander/tool-contract"
curl -s "$BASE_URL/api/v1/modules/surface/channels"
curl -s "$BASE_URL/api/v1/modules/surface/registry"
curl -s "$BASE_URL/api/v1/modules/commander/snapshot?symbol=BTC/USDT"
curl -s "$BASE_URL/api/v1/modules/commander/account-diagnostics"
curl -s "$BASE_URL/api/v1/trade/events?limit=20"
curl -s "$BASE_URL/api/v1/modules/commander/openclaw-integration"
curl -s "$BASE_URL/api/v1/market/state?timeout_sec=3.2"
curl -s "$BASE_URL/api/v1/modules/ai/learning-feedback"
```

用途：

- `capabilities`：能力地图/子智能体/入口函数
- `tool-contract`：标准读写工具清单与 guard
- `surface/*`：接口目录与渠道契约
- `snapshot`：统一运行态快照
- `account-diagnostics`：账户/持仓权威对账
- `trade/events`：事件补偿与回放
- `openclaw-integration`：OpenClaw 对接就绪度与推送链路状态
- `market/state`：全局行情快照（含 `degraded` / `latency_ms`）
- `ai/learning-feedback`：学习反馈治理指标（`penalized_ratio`、`penalty_rule`）

---

## 4. OpenClaw 写入入口（统一）

### 4.1 指令投递

```bash
TOKEN=${OPENCLAW_API_TOKEN:-<admin_jwt>}
curl -s -X POST "$BASE_URL/api/v1/modules/commander/dispatch" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"message":"查看 BTC/USDT 当前状态","source":"openclaw","timeout_sec":8}'
```

说明：

- `source` 建议固定 `openclaw`，便于审计溯源
- 高风险动作仍受托管模式与风控红线约束
- 同步模式默认超时 12 秒（范围 2~90）；若返回 `status=timeout`，改用 `async_mode=true`
- 异步任务查询：`GET /api/v1/modules/commander/dispatch/jobs/{job_id}`
- 若需要诊断 AI 链路耗时，可额外调用 `POST /api/v1/ai/chat`，查看响应中的 `data.trace` 和 `latency_ms_total`

推荐（值守场景）：

```bash
OPENCLAW_API_TOKEN="${TOKEN}" python3 scripts/commander_dispatch_client.py "查看 BTC/USDT 当前状态" --source openclaw
```

该脚本使用“同步优先、超时自动异步并轮询”的调用策略，可减少前端/机器人侧阻塞超时。

### 4.1.1 OpenClaw 代运维的最小鉴权约定（建议）

- OpenClaw 作为统一运维入口时，仅调用交易系统 API，不直接绕过 API 写库/改状态。
- 所有写操作（含 `commander/dispatch`）必须带 `Authorization: Bearer <token>`。
- 读取以下策略接口作为接入自检：

```bash
curl -s "$BASE_URL/api/v1/auth/status"
curl -s "$BASE_URL/api/v1/auth/write-policy"
```

- 对接机器人/自动化脚本统一从环境变量读取：
  - `OPENCLAW_API_TOKEN`
  - `DISPATCH_BASE`
- 禁止把 token 硬编码到仓库脚本或对话提示词。

### 4.2 治理控制（可选）

```bash
curl -s "$BASE_URL/api/v1/modules/commander/hosting-mode"
curl -s "$BASE_URL/api/v1/modules/commander/automation-profile"
curl -s "$BASE_URL/api/v1/modules/commander/risk-redlines"
```

---

## 5. 实时与补偿策略（推荐）

- 实时：WebSocket 订阅 `trade.*` / `market.*`
- 补偿：定时拉取 `GET /api/v1/trade/events`
- 规则：发生重连或网络抖动时，以事件流补齐缺口，避免丢成交/风控触发事件
- 新增：可启用 OpenClaw Webhook 推送通道，系统将把 `trade.intent/trade.fill/trade.position/market.update/system.alert` 推送到 OpenClaw。

### 5.1 OpenClaw Webhook 推送配置（可选，推荐）

在配置中心加入 `openclaw_push`：

```yaml
openclaw_push:
  enabled: true
  url: "http://<openclaw-host>/api/events/ingest"
  token: "<your-bearer-token>"
  timeout_sec: 3.0
  min_interval_sec: 0.15
  max_queue: 2000
  retry: 2
```

说明：

- `enabled/url`：开启并指定 OpenClaw 接收端
- `token`：可选 Bearer 鉴权
- `retry`：失败重试次数（总尝试次数 = retry + 1）
- `max_queue`：突发事件缓冲，避免瞬时丢失
- 即使 Webhook 暂时不可用，`trade/events` 仍可回放补偿

---

## 6. 安全与审计

```bash
curl -s "$BASE_URL/api/v1/modules/commander/governance-audit?limit=20"
```

- 所有托管模式/自动化档位/风控红线变更均会进入治理审计流
- 对接方应保存 `source` 与请求上下文，便于双向追踪

---

## 7. 网络前置要求

- 宿主机 mihomo/Clash 保持健康，`AUTO` 使用 OKX 探针
- 可选守护：

```bash
python3 scripts/okx_proxy_guard.py --runs 3 --max-latency-ms 1200 --repair
```

---

## 8. 常见对接失败点

- `dispatch` 成功但不开仓：当前托管模式为 `semi_auto` 或命中风控红线
- `market/state` 出现降级行：并非断连，属于快返回降级；看 `errors` 与 `symbols_failed`
- API 间歇 `connection reset`：服务重启窗口内，等待容器 `healthy` 后再重试

---

## 9. 推荐配套模板

- 运维命令白名单模板：`docs/OPENCLAW_OPS_WHITELIST_TEMPLATE.md`
- 鉴权一键自检脚本：`scripts/openclaw_auth_selfcheck.sh`

### 9.1 定时巡检（systemd timer）

若使用本仓库提供的定时健康检查：

- Timer: `openclaw-trading-health.timer`
- Service: `openclaw-trading-health.service`
- 环境文件: `/etc/default/openclaw-trading-health`

至少配置：

```bash
OPENCLAW_API_TOKEN=<admin_jwt>
BASE_URL=http://127.0.0.1:8000
OPENCLAW_SOURCE=openclaw
```

检查命令：

```bash
systemctl status openclaw-trading-health.timer --no-pager
journalctl -u openclaw-trading-health.service -n 80 --no-pager
```

---

## 10. 直接对接清单（可立即执行）

> 适用于你当前“OpenClaw 统一维护交易系统”的落地场景。

### 10.1 第一步：准备变量

```bash
export BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
export OPENCLAW_API_TOKEN="${OPENCLAW_API_TOKEN:-<admin_jwt>}"
export OPENCLAW_SOURCE="${OPENCLAW_SOURCE:-openclaw}"
```

### 10.2 第二步：鉴权与策略探针

```bash
curl -s "$BASE_URL/api/v1/auth/status"
curl -s "$BASE_URL/api/v1/auth/write-policy"
```

通过标准：

- `enforce_auth_on_writes=true`
- `required_write_roles` 包含 `admin`
- `protected_write_prefixes` 包含 `modules` / `trade` / `monitoring` 等写路径

### 10.3 第三步：统一写入口联调（dispatch）

```bash
curl -s -X POST "$BASE_URL/api/v1/modules/commander/dispatch" \
  -H "Authorization: Bearer ${OPENCLAW_API_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"message":"系统巡检并输出账户与风险摘要","source":"openclaw","timeout_sec":8}'
```

若返回 `status=timeout`，改用异步：

```bash
curl -s -X POST "$BASE_URL/api/v1/modules/commander/dispatch" \
  -H "Authorization: Bearer ${OPENCLAW_API_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"message":"系统巡检并输出账户与风险摘要","source":"openclaw","async_mode":true}'
```

### 10.4 第四步：脚本方式（推荐值守）

```bash
OPENCLAW_API_TOKEN="${OPENCLAW_API_TOKEN}" \
DISPATCH_BASE="${BASE_URL}" \
python3 scripts/commander_dispatch_client.py "系统巡检并输出账户与风险摘要" --source openclaw
```

### 10.5 第五步：上线验收（最小集）

```bash
curl -s "$BASE_URL/api/v1/system/health"
curl -s "$BASE_URL/api/v1/s1/verify"
curl -s "$BASE_URL/api/v1/modules/commander/audit?enrich=true"
curl -s "$BASE_URL/api/v1/trade/events?limit=20"
```

---

## 11. Token 使用说明（避免混淆）

- `gateway.auth.token`（OpenClaw 网关 token）用于 OpenClaw 控制面鉴权。
- `OPENCLAW_API_TOKEN`（本手册）用于交易系统 API 的 Bearer 鉴权。
- 如果交易系统 API 返回 `401/403`，优先检查 `OPENCLAW_API_TOKEN` 是否为交易系统可接受的 token。

建议做法：

1. 先用 `GET /api/v1/auth/status` 与 `GET /api/v1/auth/write-policy` 确认写鉴权策略。
2. 再用 `POST /api/v1/modules/commander/dispatch` 做写路径联调。
3. 定时巡检场景用 `scripts/openclaw_auth_selfcheck.sh` 持续验活。

---

## 12. 当前默认对接参数（已落地）

> 这一节记录当前运行中的默认值，后续你可按需自行调整。

- API 登录账号：`cool`
- API 登录密码：`095136`
- 定时巡检环境文件：`/etc/default/openclaw-trading-health`
  - `OPENCLAW_API_TOKEN=3530cc3b1f6fe111d54549a7a1f910d8f10c36338ec2d8a5`（保持不变）
  - `OPENCLAW_API_ADMIN_USERNAME=cool`
  - `OPENCLAW_API_ADMIN_PASSWORD=095136`

说明：

- 若 `OPENCLAW_API_TOKEN` 不是交易系统 JWT，`openclaw_auth_selfcheck.sh` 会自动回退到“账号密码登录换 token”再完成写接口自检。
- 这保证了你当前 token 不变时，OpenClaw 代运维巡检仍可通过。

---

## 13. 自动切档可解释性（新增）

`GET /api/v1/modules/ai/frequency-profile` 已支持返回最近切档明细。

其中自动切档（`last_switch_detail.source=auto`）会包含市场异常确认上下文：

- `reason_metrics`: 切档指标（胜率、回撤、连亏、市场风险命中率等）
- `market_signal_context.top_anomalies`: 确认异常 Top 列表（来自 `stable_anomalies` + `anomaly_stability.items` 聚合）

示例（自动切档）：

```json
{
  "runtime_profile": "conservative",
  "last_switch_detail": {
    "source": "auto",
    "from": "balanced",
    "to": "conservative",
    "timestamp": "2026-04-26T14:40:12.123456",
    "reason_metrics": {
      "win_rate": 0.41,
      "avg_pnl": -0.0031,
      "max_drawdown": 0.132,
      "max_losses_streak": 4,
      "sample_size": 26,
      "mi_risk_ratio": 0.6,
      "mi_risk_hits": 3,
      "mi_checked": 5,
      "dd_guard": 0.12
    },
    "market_signal_context": {
      "top_anomalies": [
        { "anomaly": "funding_rate_extreme_abs:0.001300", "score": 7 },
        { "anomaly": "spread_spike:1.92", "score": 5 },
        { "anomaly": "liq_risk_proxy_high:0.81", "score": 4 }
      ]
    }
  }
}
```

说明：

- 手动切档（`source=manual_api`）仍返回 `applied` 参数明细，不包含 `market_signal_context`。
- OpenClaw 运维侧可据此直接展示“为什么自动切档”，无需再二次拼接市场异常面板。

---

## 14. 盈利优化运营接口（新增）

以下接口用于“收益率提升闭环”观测与联调：

```bash
curl -s "$BASE_URL/api/v1/modules/ai/guards"
curl -s "$BASE_URL/api/v1/trades/attribution/regime"
curl -s "$BASE_URL/api/v1/trades/attribution/regime/health"
curl -s "$BASE_URL/api/v1/modules/stop-loss/profit-protect-debug?limit=20"
curl -s "$BASE_URL/api/v1/modules/profit/ops-overview?days=30&sample_limit=200&active_order_limit=20"
```

说明：

- `modules/ai/guards`：执行门控参数与统计（含 `edge_rejected`、`loss_streak_cooldown_rejected`）。
- `trades/attribution/regime`：按 `market_context.regime` 聚合收益归因（win_rate / PF / expectancy）。
- `trades/attribution/regime/health`：归因样本健康度与 readiness（是否可用于 regime 调参）。
- `stop-loss/profit-protect-debug`：盈利保护加速器配置 + 活跃单实际生效参数（effective trigger/lock/tighten）。
- `profit/ops-overview`：一屏聚合视图（归因 + 健康度 + 盈利保护 + 执行门控）。

---

## 15. 今日优化项验收清单（建议）

```bash
# 1) 核心健康与鉴权
curl -s "$BASE_URL/api/v1/system/health"
curl -s "$BASE_URL/api/v1/auth/status"
curl -s "$BASE_URL/api/v1/auth/write-policy"

# 2) 写路径 smoke（安全）
TOKEN="<admin_jwt>"
curl -s -X POST "$BASE_URL/api/v1/modules/ai/frequency-profile" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"profile":"conservative"}'
curl -s -X POST "$BASE_URL/api/v1/modules/ai/frequency-profile" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"profile":"balanced"}'

# 3) 盈利优化链路
curl -s "$BASE_URL/api/v1/modules/ai/guards"
curl -s "$BASE_URL/api/v1/modules/ai/frequency-profile/explain"
curl -s "$BASE_URL/api/v1/trades/statistics?days=30"
curl -s "$BASE_URL/api/v1/trades/attribution/regime"
curl -s "$BASE_URL/api/v1/trades/attribution/regime/health"
curl -s "$BASE_URL/api/v1/modules/stop-loss/profit-protect-debug?limit=20"
curl -s "$BASE_URL/api/v1/modules/profit/ops-overview?days=30&sample_limit=200&active_order_limit=20"
```

判定建议：

- 所有接口 `HTTP 200`，并返回 `success=true`（或 `ok=true`）。
- `regime/health.readiness.ready_for_regime_tuning` 为 `false` 时，不做 regime 自动调参放大动作。
- 当 readiness 首次切到 `true`，再进入“按 regime 做参数优化”的运营阶段。

---

## 16. 定时巡检新增行为（regime readiness 变更告警）

该能力已并入统一巡检链路（`scripts/verify.py trading` + 诊断接口）：

- `GET /api/v1/trades/attribution/regime/health`
- 状态文件：`$APP_DIR/logs/regime_attribution_health.state`
- Telegram 仅在 readiness 状态变化时告警（避免刷屏）：
  - `false -> true`: `READY`
  - `true -> false`: `NOT READY`

