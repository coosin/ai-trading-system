# OpenClaw Trading — MCP 基础与对标基线

本文档用于统一说明当前系统与 MCP（Model Context Protocol）的关系、落地边界和后续方向。

---

## 1. MCP 基础概念（面向本仓库）

- **MCP 是协议层**：用于让 AI 客户端（Cursor / Claude / VSCode 等）调用外部工具。
- **本系统定位**：
  - 现阶段以 `FastAPI + 内部模块` 为主；
  - 可通过 MCP 客户端访问本系统 API 或外部交易工具；
  - 后续可补充 OpenClaw 自身 MCP Server（统一暴露行情、账户、风控、执行、复盘能力）。

---

## 2. 与 OKX Agent Trade Kit 的关系

参考来源（2026-04-15）：

- OKX Agent Trade Kit 页面：<https://www.okx.com/zh-hans/agent-tradekit>
- OKX Agent Trade Kit 仓库：<https://github.com/okx/agent-tradekit>
- MCP 官方入门：<https://modelcontextprotocol.io/docs/getting-started/intro>

结论：

- **OKX Agent Trade Kit 更偏“标准执行底座”**（MCP/CLI 工具化、模块化、快速接入）。
- **OpenClaw 更偏“智能交易中台”**（数据融合、AI 决策、风险门控、事件流、复盘学习）。
- 推荐路线：**保留 OpenClaw 智能核心，执行层与 MCP/CLI 标准接口兼容化**。

---

## 3. 当前运行态约束（重要）

- 账户与持仓权威来源仍是交易所接口（OKX）。
- 控制面快照 (`/api/v1/modules/commander/snapshot`) 在缓存为空时已支持多级回退：
  1. `_latest_account_state`
  2. `ai_trading_engine.positions`
  3. 交易所短超时直拉（2.5s）
- `account-diagnostics` 超时降级时返回 `hint=account_diagnostics_timeout`，并附带关键事实字段（如 `exchange`、`cached_position_count`），避免误判。

---

## 4. 建议的 MCP 工程落地顺序

1. **读路径先行**：行情、账户、风控状态、事件流（只读工具）
2. **写路径分级**：下单/撤单/改仓按模块权限开放
3. **安全护栏**：read-only 模式、模块白名单、速率限制、二次确认
4. **一致性校验**：写后强制对账（持仓/余额）并回写事件流

---

## 5. 验收基线（MCP 集成后）

- 客户端接入：可在 30 分钟内完成并调用行情只读工具
- 状态一致性：系统持仓数与交易所非零持仓数一致
- 超时降级可解释：返回降级标记与可读 hint，不返回空白结构
- 交易审计可追踪：每次写操作在事件流与审计接口有对应记录

