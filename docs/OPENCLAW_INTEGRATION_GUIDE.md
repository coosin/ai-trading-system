# OpenClaw 对接手册（生产版）

本文档用于把 OpenClaw 客户端/智能体接入当前交易系统，作为统一控制与编排入口。

---

## 1. 对接目标

- 统一入口：所有指令走 `commander/dispatch`
- 统一读面：状态、能力、工具契约、审计流可读取
- 统一补偿：实时消息 + 事件流回放并用
- 统一安全：托管模式、风控红线、治理审计可追溯

---

## 2. 上线前最小检查

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/api/v1/s1/verify
curl -s http://localhost:8000/api/v1/modules/commander/audit?enrich=true
```

通过标准：

- `health.status=healthy`
- `s1/verify.all_passed=true`
- `commander/audit.all_passed=true`

---

## 3. OpenClaw 必接读取接口

```bash
curl -s http://localhost:8000/api/v1/modules/commander/capabilities
curl -s http://localhost:8000/api/v1/modules/commander/tool-contract
curl -s http://localhost:8000/api/v1/modules/surface/channels
curl -s http://localhost:8000/api/v1/modules/surface/registry
curl -s 'http://localhost:8000/api/v1/modules/commander/snapshot?symbol=BTC/USDT'
curl -s 'http://localhost:8000/api/v1/modules/commander/account-diagnostics'
curl -s 'http://localhost:8000/api/v1/trade/events?limit=20'
```

用途：

- `capabilities`：能力地图/子智能体/入口函数
- `tool-contract`：标准读写工具清单与 guard
- `surface/*`：接口目录与渠道契约
- `snapshot`：统一运行态快照
- `account-diagnostics`：账户/持仓权威对账
- `trade/events`：事件补偿与回放

---

## 4. OpenClaw 写入入口（统一）

### 4.1 指令投递

```bash
curl -s -X POST http://localhost:8000/api/v1/modules/commander/dispatch \
  -H 'Content-Type: application/json' \
  -d '{"message":"查看 BTC/USDT 当前状态","source":"openclaw"}'
```

说明：

- `source` 建议固定 `openclaw`，便于审计溯源
- 高风险动作仍受托管模式与风控红线约束

### 4.2 治理控制（可选）

```bash
curl -s http://localhost:8000/api/v1/modules/commander/hosting-mode
curl -s http://localhost:8000/api/v1/modules/commander/automation-profile
curl -s http://localhost:8000/api/v1/modules/commander/risk-redlines
```

---

## 5. 实时与补偿策略（推荐）

- 实时：WebSocket 订阅 `trade.*` / `market.*`
- 补偿：定时拉取 `GET /api/v1/trade/events`
- 规则：发生重连或网络抖动时，以事件流补齐缺口，避免丢成交/风控触发事件

---

## 6. 安全与审计

```bash
curl -s 'http://localhost:8000/api/v1/modules/commander/governance-audit?limit=20'
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

