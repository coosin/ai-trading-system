# OpenClaw 运维命令白名单模板（交易系统）

目标：让 OpenClaw 成为交易系统唯一运维入口，同时保证“可维护、可审计、可回滚”。

---

## 1. 使用原则

- 只允许调用交易系统 API 与只读巡检命令，不允许绕过 API 直接改库。
- 写操作必须携带 Bearer token，并在审计中标记 `source=openclaw`。
- 高风险动作（开平仓、模式切换、风控阈值调整）必须经过二次确认或审批。
- 所有请求日志保留 `request_id/source/operator/result`，便于追溯。

---

## 2. 环境变量基线

```bash
export DISPATCH_BASE="${DISPATCH_BASE:-http://127.0.0.1:8000}"
export OPENCLAW_API_TOKEN="<admin_jwt>"
export OPENCLAW_SOURCE="openclaw"
```

---

## 3. 白名单分级（建议）

### L1 只读巡检（默认放开）

- `GET /api/v1/system/health`
- `GET /api/v1/s1/verify`
- `GET /api/v1/auth/status`
- `GET /api/v1/auth/write-policy`
- `GET /api/v1/modules/commander/audit?enrich=true`
- `GET /api/v1/modules/commander/snapshot?symbol=BTC/USDT`
- `GET /api/v1/modules/commander/account-diagnostics`
- `GET /api/v1/trade/events?limit=20`
- `GET /api/v1/market/state?timeout_sec=3.2`
- `GET /api/v1/monitoring/alerts`

### L2 低风险控制（可放开到值班账号）

- `POST /api/v1/modules/commander/dispatch`
  - 仅允许“巡检/查询/诊断”类语义
  - `timeout_sec` 限制在 `2~20`
  - 必须携带 `source=openclaw`

### L3 高风险控制（需审批/二次确认）

- 通过 `dispatch` 触发的实际交易动作（开仓/平仓/撤单/模式切换）
- 风控参数变更与托管模式变更
- 批量重试、批量补单、强制止损等操作

---

## 4. OpenClaw 调用模板

### 4.1 统一 Dispatch（推荐）

```bash
python3 scripts/commander_dispatch_client.py \
  "系统巡检并输出账户与风险摘要" \
  --source "${OPENCLAW_SOURCE:-openclaw}" \
  --base-url "${DISPATCH_BASE:-http://127.0.0.1:8000}" \
  --token "${OPENCLAW_API_TOKEN}"
```

### 4.2 鉴权自检（上线前/轮换后必跑）

```bash
BASE_URL="${DISPATCH_BASE:-http://127.0.0.1:8000}" \
OPENCLAW_API_TOKEN="${OPENCLAW_API_TOKEN}" \
./scripts/openclaw_auth_selfcheck.sh
```

---

## 5. 拒绝策略（建议直接落地）

- 无 token、token 无效、角色不足：直接拒绝并告警。
- 命中非白名单路径：直接拒绝并记录请求上下文。
- 高风险动作未审批：拒绝执行，返回“需要人工确认”。
- 同一来源短时高频写请求：触发速率限制与冷却。

---

## 6. 审计记录字段（最小集）

- `timestamp`
- `operator`（人/机器人标识）
- `source`（固定 `openclaw`）
- `endpoint` / `message`
- `request_id`
- `result`（success/denied/failed）
- `reason`（拒绝或失败原因）

---

## 7. 推荐接入流程

1. 配置 token 与 base URL。
2. 运行 `openclaw_auth_selfcheck.sh` 确认鉴权链路可用。
3. 先放开 L1 + L2，观察 1~3 天。
4. L3 动作接审批流后再放开。
5. 每次 token 轮换后重复步骤 2。
