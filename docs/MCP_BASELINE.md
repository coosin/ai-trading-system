# OpenClaw MCP 基线

本文说明当前系统与 MCP 的关系。OpenClaw 的主系统仍是 FastAPI + 内部模块；MCP 是外部 AI 客户端调用工具的适配层，不是交易执行的绕行入口。

## 定位

- FastAPI 标准域接口是权威控制面。
- MCP/CLI 工具通过 HTTP fallback adapter 访问标准域和兼容只读接口。
- 默认 fallback 只允许只读 GET 工具。
- 写入工具即使出现在 manifest，也必须标记为 guarded write，并由系统鉴权和 ExecutionGateway 门禁处理。

## 当前文件与入口

- MCP fallback adapter：`mcp_adapter/openclaw_mcp_server.py`。
- 启动脚本：`start_mcp_server.sh`。
- 工具发现：`GET /api/v1/modules/surface/mcp-manifest`。
- 标准 API 发现：`GET /api/v1/surface/registry`。
- API 基址：`OPENCLAW_API_BASE`。

启动：

```bash
OPENCLAW_API_BASE=http://127.0.0.1:8000 ./start_mcp_server.sh restart
```

验收：

```bash
curl -s http://127.0.0.1:18888/health
curl -s http://127.0.0.1:18888/tools
curl -s -X POST http://127.0.0.1:18888/call \
  -H 'Content-Type: application/json' \
  -d '{"tool":"system_health","params":{}}'
```

## 推荐工具分级

只读工具：

- 系统健康、状态、surface registry。
- 账户快照、行情快照、数据快照。
- commander system-mastery、closed-loop、trading-workflow。
- strategy overview、trades lifecycle、agents effectiveness。

受保护写工具：

- 策略审批、启用、停用。
- 学习 backfill、trace attribution backfill。
- 交易执行类工具不得默认开放；如需开放，必须保留人工审批、source、trace、鉴权和 ExecutionGateway 门控。

## 安全边界

- MCP 不是交易所密钥持有者；密钥仍由 OpenClaw 运行进程和 `.env` 管理。
- MCP 不直接连接 OKX 下单。
- MCP 不绕过 `ai_brain.single_write_owner=ai_core`。
- MCP 写入必须被 API 鉴权和审计记录覆盖。
- MCP 工具返回降级状态时必须把 `hint`、`degraded`、`error` 原样传给客户端。

## 与 OKX Agent Trade Kit 的关系

- OKX Agent Trade Kit 更偏标准化交易工具底座。
- OpenClaw 更偏智能交易中台：数据融合、AI 决策、风险门控、执行脊柱、复盘学习。
- 推荐路线是保留 OpenClaw 智能核心，把 MCP/CLI 作为外部工具适配层，而不是替换内部 ExecutionGateway。

## 集成验收

- 客户端 30 分钟内可完成只读工具接入。
- 账户和持仓快照与交易所事实可解释一致。
- 降级响应不为空白，必须有 hint 或结构化 error。
- 写入操作有审计、trace、source 和执行后对账。

