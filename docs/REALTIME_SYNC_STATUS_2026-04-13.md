# 实时链路与 API 同步状态（2026-04-13）

## 1) 当前系统能力结论

- 核心服务在线：`/api/v1/system/health`、`/api/v1/modules/system/health` 返回 healthy。
- 司令部主入口在线：`POST /api/v1/modules/commander/dispatch` 可直接驱动开平仓指令。
- 行情实时输出在线：`/api/v1/market/symbol/{symbol}`、`/api/v1/market/state`、`/api/v1/modules/data/hub/unified-snapshot` 正常返回最新判断与质量分。
- 开平仓通知在线：`/api/v1/trade/events` 可读到 `trade.fill` 事件；`/api/v1/modules/execution/production-audit` 可读到执行脊柱最新动作。
- 止盈止损通知在线：`/api/v1/trade/events` 可读到 `trade.position` + `sltp.create` / `sltp_stop_loss_triggered`；`/api/v1/modules/stop-loss/stats` 与审计快照一致递增。

## 2) 前端/司令部/API 对接建议（升级后统一）

- A 接口统一入口：`POST /api/v1/modules/commander/dispatch`
- 实时消费主通道：`GET /api/v1/trade/events`（建议 1~2s 轮询，带 cursor）
- 执行审计对账：`GET /api/v1/modules/execution/production-audit`
- 能力与路由发现：`GET /api/v1/modules/surface/registry`、`GET /api/v1/modules/surface/channels`

## 3) WebSocket 频道契约

- 地址：`ws://<host>:8000/ws`
- 订阅协议：发送
  - `{"type":"subscribe","channels":["trade.*","market.*"]}`
  - 支持前缀通配（`trade.*` 匹配 `trade.fill/trade.position/trade.intent`）。
- 生产建议：WebSocket + `/api/v1/trade/events` 双轨（实时 + 补偿回放）。

## 4) 本次同步涉及文档

- `docs/API_REFERENCE.md`（新增“升级后实时链路”）
- `docs/OPERATIONS.md`（新增“实时通知链路巡检”）
- 本文件（升级后现状快照）
