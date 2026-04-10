# Trade module single-writer contract

目标：**实盘开/平仓只允许经 `AICoreDecisionEngine` 发起意图**，并且所有交易执行都走统一链路 `ExecutionVerifier` → `ExecutionGateway(S1)` → `OKXExchange`（或其他交易所适配器）。

## 关键模块与职责边界

- **`AICoreDecisionEngine`**
  - **职责**：唯一的“开仓意图来源”（TradeIntent），生成 `trace_id`，把 `write_source="ai_core"` 贯穿到执行与事件。
  - **不做**：不直接触达交易所 API。

- **`ExecutionVerifier`**
  - **职责**：对“命令执行”做统一封装与记录，**强制**开/平仓只走 `ExecutionGateway`。
  - **不做**：不允许开/平仓回退到 `exchange.create_order`（防止绕过 S1 策略与幂等/可观测性）。

- **`ExecutionGateway`（S1）**
  - **职责**：统一的实盘下单脊柱（policy + preflight + idempotency + metrics + event publishing）。
  - **策略**：依据 `ai_brain.single_write_owner` 限制可写入源（默认 `ai_core`）。
  - **不做**：不做行情分析/信号决策。

- **`StopLossTakeProfitManager`（SLTP）**
  - **职责**：软件 SL/TP 状态机；触发时 **只允许通过 S1 平仓**。
  - **关键约束**：以 **`instId + posSide`**（或等价唯一仓位键）作为唯一索引键，避免 `symbol`/`symbol|side` 混用导致保护遗漏/重复。

- **`ProactiveMarketScanner`（`proactive_ai_system.py`）**
  - **职责**：产出机会（hints/opportunities），经过 Gate 初筛后 **只转发给 `ai_core`**。
  - **硬约束**：默认且在 `single_write_owner=ai_core` 时**强制**关闭自动开仓。

- **`MarketIntelligenceEngine`（MI）**
  - **职责**：统一的只读行情情报输出（SymbolView/MarketState），为 ai_core 决策提供证据；可给扫描机会提供 guard 建议。
  - **不做**：不直接下单。

- **`TradeEventHub`**
  - **职责**：所有交易生命周期事件的统一发布（intent/fill/position_update/market_update），为前端/Telegram/API 提供契约化数据。

## 实盘开/平仓“唯一链路”

```text
AICoreDecisionEngine
  -> MainController.execute_command(write_source="ai_core", trace_id=...)
      -> ExecutionVerifier.execute()
          -> ExecutionGateway.open_swap/close_swap()
              -> OKXExchange.open_swap_position/close_swap_position
              -> TradeEventHub.publish_intent/fill/position_update
```

## 允许/禁止的写入者（默认）

- **允许开仓**：`ai_core`（默认唯一），`manual`（人工显式触发时可开）。
- **默认禁止开仓**：`system` / `scanner` / `active_trader` / 其他来源（避免“遗漏即特权”）。
- **允许平仓**：`ai_core`、`sltp`、`manual`（风险处置需要）。

> 说明：如需临时启用 `system` 开仓（例如运维工具），应通过 `ai_brain.policy.allow_system_open=true` 显式开启。

