# OpenClaw Trading — 每日托管验收清单（3~5 步）

这是一份面向日常值守的“傻瓜化”验收手册。  
目标：每天花 1-3 分钟，快速确认系统是否可以继续全自动托管。

---

## 0) 验收前提

- API 服务地址：默认 `http://127.0.0.1:8000`（可通过 `BASE_URL` 覆盖）
- 控制面已部署最新版本（含治理审计与工具契约接口）
- 如为生产环境，先确保网络与 OKX 连通性基础正常

---

## 1) 一键总验收（推荐）

优先执行：

```bash
python3 scripts/verify.py trading --base-url http://127.0.0.1:8000
```

通过标准：

- 输出 `OVERALL: PASS`
- 关键阶段全部 `PASS`（尤其是 `force_sync_account_state`、`run_ai_commander_chores`、`hosting_guard_status`、`governance_profile_check`）

补充（快速只读总验收，适合 API 值守探活）：

```bash
curl -s http://localhost:8000/api/v1/system/acceptance
```

若失败，先不要继续全自动，转到“第 4 节：失败时处理”。

---

## 2) 托管与风控红线（两键确认）

### 2.1 当前托管模式 / 自动化档位

```bash
curl -s http://localhost:8000/api/v1/modules/commander/hosting-mode
curl -s http://localhost:8000/api/v1/modules/commander/automation-profile
```

通过标准（默认设计）：

- `hosting_mode` 为 `full_auto` 或符合你当前策略
- `automation_profile` 与预期一致（保守/半自动/全自动）

### 2.2 统一风控红线

```bash
curl -s http://localhost:8000/api/v1/modules/commander/risk-redlines
```

通过标准：

- 返回成功，且关键红线字段存在（如 `max_positions`、`single_order_max_ratio`、`total_exposure_max_ratio`、`min_open_interval_sec`）

---

## 3) 账户/持仓与交易链路（两键确认）

### 3.1 账户与持仓同步

```bash
curl -s 'http://localhost:8000/api/v1/modules/commander/account-diagnostics'
curl -s 'http://localhost:8000/api/v1/modules/commander/snapshot?symbol=BTC/USDT'
```

通过标准：

- `account-diagnostics` 可返回有效结构（允许短时 `degraded=true`，但必须有可解释 `hint`）
- `snapshot.data.account.positions` 与实际交易所持仓规模一致或可解释

### 3.2 事件流活性

```bash
curl -s 'http://localhost:8000/api/v1/trade/events?limit=20'
```

通过标准：

- 持续有 `market.update` / `trade.position` / `trade.fill` 等事件
- 事件内容可用于前端与外部系统回放

---

## 4) 失败时处理（固定动作）

任一关键项失败时，按顺序处理：

1. 立即切换半自动（保护）：

```bash
curl -s -X POST http://localhost:8000/api/v1/modules/commander/hosting-mode \
  -H 'Content-Type: application/json' \
  -d '{"mode":"semi_auto","reason":"daily_acceptance_failed"}'
```

2. 再跑回归脚本定位问题面：

```bash
python3 scripts/verify.py trading --base-url http://127.0.0.1:8000
```

3. 查看治理审计与工具契约（确认变更可追溯）：

```bash
curl -s 'http://localhost:8000/api/v1/modules/commander/governance-audit?limit=20'
curl -s 'http://localhost:8000/api/v1/modules/commander/tool-contract'
```

4. 网络异常优先执行：

```bash
python3 scripts/network_connectivity_smoke.py
```

---

## 5) 每日最小执行模板（建议直接照抄）

```bash
BASE_URL=${BASE_URL:-http://127.0.0.1:8000}
python3 scripts/verify.py trading --base-url "$BASE_URL"
curl -s "$BASE_URL/api/v1/modules/commander/hosting-mode"
curl -s "$BASE_URL/api/v1/modules/commander/risk-redlines"
curl -s "$BASE_URL/api/v1/modules/commander/account-diagnostics"
curl -s "$BASE_URL/api/v1/trade/events?limit=20"
```

全部通过后，再保持或切回 `full_auto`。
