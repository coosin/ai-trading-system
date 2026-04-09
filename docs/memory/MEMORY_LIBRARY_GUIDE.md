# 记忆库（MemoryGateway 单一真源）使用与维护指南

本系统的“记忆库”不是单一文件，而是一套**统一入口 + 分层落盘 + 可检索/可总结/可治理**的机制。
本文档面向开发/运维/策略迭代，解释整体结构、写入与召回方式、维护与修改方法，以及常见问题排查。

---

## 目标与边界

- **单一真源**：所有结构化记忆读写都应通过 `MemoryGateway` 入口完成（避免多套并行记忆实现导致口径不一致）。
- **交易优先**：交易动作、SL/TP、风险事件、策略变更/复盘等是记忆重点；系统运维日志只存“摘要+指针”，避免把海量日志灌进记忆。
- **短而原子**：每条记忆尽量短、可检索、可汇总（给日/周总结留空间）。

---

## 零、分层读取策略（启动 / 对话 / 任务 / 精华文件）

**整体方向正确**：应采用「固定小预算 + 按需召回」，而不是条数越大越好。代码入口：`src/modules/memory/memory_context_policy.py`，数值可由 `data/config/memory.json` 的 `memory.context_policy` 覆盖。

### 启动后必读（Workspace — 人格 / 职责 / 经验锚点）

从 `paths.workspace_path` 下按顺序加载文本摘要（文件缺失则跳过）：  
`IDENTITY.md` → `SOUL.md` → `INSTRUCTIONS.md` → `TRADING.md` → `USER.md` → **`LESSONS_ESSENCE.md`**。  
总长度由 `startup_bundle_max_total_chars`、单文件 `startup_max_chars_per_file` 限制。

### 启动后结构化规则

高重要性「黑名单 / 授权」等仍通过 **`MemoryGateway.retrieve_memories`** 加载（见指令执行器初始化）。

### 日常对话

- **硬注入（最近对话）**：默认 **12 轮**（`conversation_recent_limit`）。这比固定 50 条更常见也更省：多数会话的指代与情绪在十余轮内；再增大边际收益递减、噪声与成本上升。若你有极端长会话场景，再单独调配置。  
- **软注入（与当前输入相关）**：默认 **8 条**（`conversation_recall_limit`）。  
- **规则 / 偏好**：默认 **5 条**（`rules_recall_limit` + `rules_recall_query`）。  

以上在 `EnhancedLLMIntegration.generate` 中执行；`MainController` 会将 `policy_config_manager` 注入 LLM 集成以读取配置。

### 特定任务（交易 / 风控 / 策略 / 回测）

意图为 `trade`、`risk`、`strategy_create`、`strategy_optimize`、`backtest`、`market_analysis` 等时，额外拼接 **任务定向记忆**（`task_memory` 内多 query + `limit_each`），专门覆盖开平仓、SLTP、策略教训等；闲聊路径不强制拉满。

### 决策引擎（`ai_core`）

`_learn_from_memory` 使用 **`decision_engine_recall`**：交易经验条数、策略表现条数、以及单独一条「经验教训」query，与对话侧 budget 分离。

### 经验教训：双轨

- **结构化精华**：`lesson_learned` / `risk_event` / `trade_record` 等在 `data/memory`，供召回与汇总。  
- **小文件锚点**：`workspace/LESSONS_ESSENCE.md` 由人 / AI 偶尔把结论合并进去；**启动期读摘要**，日常以 **按需结构化召回** 为主，避免每次对话整文件塞满上下文。

---

## 一、整体结构（两层：结构化召回层 + 工作空间治理层）

### 1) 结构化召回层（Structured Recall Layer）

- **对外入口**：`src/modules/memory/memory_gateway.py`
- **落盘后端**：`src/modules/core/optimized_memory_system.py`
- **召回 provider**：`src/modules/memory/providers/native.py`（当前为 BM25/keyword overlap + “hybrid”权重框架）
- **落盘目录（宿主机开发态）**：`data/memory/`
  - `data/memory/core/`：长期不变的规则/偏好（CORE）
  - `data/memory/working/`：短期工作记忆（WORKING）
  - `data/memory/experience/`：可复用交易经验（EXPERIENCE）
  - `data/memory/history/`：历史事件（HISTORY）
- **落盘目录（容器/生产态）**：`/app/data/memory/`（容器内路径）

> 说明：你在宿主机看到的 `data/memory/*` 是结构化记忆的主落盘；容器内同样会生成 `/app/data/memory/*`。

### 2) 工作空间治理层（Journal/Governance Layer）

这些是“人格/规则/操作说明”的**人类可读文档**，用于约束与治理，不作为主语义召回库的唯一来源：

- `workspace/SOUL.md`
- `workspace/IDENTITY.md`
- `workspace/USER.md`
- `workspace/INSTRUCTIONS.md`
- `workspace/TRADING.md`
- `workspace/MEMORY.md`（人工摘要/里程碑记录）

---

## 二、统一分类与 schema（category / tags / metadata）

### 1) schema 辅助工具

统一的 tag/metadata 规范集中在：

- `src/modules/memory/memory_schema.py`

它提供：
- `base_metadata(...)`：统一写入 `created_at/source_module/kind/symbol/...`
- `kind_tag(...)` / `symbol_tag(...)` / `tags(...)`：统一 tag 生成与去重
- `SummaryKey`：日/周总结幂等键（避免重复生成）

### 2) 常用 category（建议口径）

结构化写入 `MemoryGateway.add_memory/store` 时使用字符串 category：

- **对话**：`conversation`
- **交易动作/开平仓**：`trade_record`
- **风险/SLTP/风控事件**：`risk_event`
- **策略决策/变更/复盘**：`decision`、`lesson_learned`
- **市场观察/洞察/数据质量事件**：`market_observation`
- **规则/授权/黑名单**：`trading_rule`（CORE）
- **用户偏好**：`user_preference`（CORE）
- **系统运维摘要**：`system_state`
- **每日摘要（working）**：`daily_summary`

> 实际映射由 `MemoryGateway` 完成：category -> layer（CORE/WORKING/EXPERIENCE/HISTORY）与内部 enum。

### 3) tags 约定（强烈推荐）

tag 的目标是让召回“更准、更可控”。推荐至少包含：

- `symbol:<SYMBOL>`：例如 `symbol:BTC-USDT`
- `kind:<KIND>`：例如 `kind:trade`、`kind:open`、`kind:sltp`、`kind:risk`、`kind:weekly`
- `module:<MODULE>`（可选）：例如 `module:ai_trading_engine`

---

## 三、写入（如何把信息放进记忆库）

### 1) 代码内写入（推荐）

所有业务写入应走 `MemoryGateway`：

- `await memory_gateway.add_memory(memory_type=..., content=..., metadata=..., tags=...)`
- 或 `await memory_gateway.store(content=..., scope=..., category=..., importance=..., metadata=...)`

关键写入点（已按规范化接入/统一 tags & metadata）：

- 交易执行/记录：
  - `src/modules/core/active_trader.py`
  - `src/modules/core/ai_trading_engine.py`
- 交易复盘/决策：
  - `src/modules/core/ai_core_decision_engine.py`
- SL/TP 触发（risk_event）：
  - `src/modules/core/stop_loss_take_profit.py`
- 对话与动作结果沉淀：
  - `src/modules/core/ai_command_executor.py`

### 2) 通过 API 写入（运维/外部工具）

统一记忆 API（`/api/v1`）：

- `POST /api/v1/ai/memory/store`

请求体示例：

```json
{
  "content": "开仓: BTC/USDT long @ 68000 qty=0.01",
  "scope": "channel:telegram",
  "category": "trade_record",
  "importance": 0.9,
  "metadata": {"order_id":"123", "kind":"trade_open", "symbol":"BTC/USDT"}
}
```

---

## 四、召回（如何在对话/决策中用起来）

### 1) 应用内召回（短期上下文注入）

系统采用“硬注入 + 软注入”：

- **硬注入**：`recent_conversation(...)` 最近 N 条对话（防止“瞬时失忆”）
- **软注入**：`retrieve_memories(query=...)` 相关记忆召回（规则/交易优先）

已在 `src/modules/core/llm_integration.py` 中实现组合注入逻辑。

### 2) 通过 API 召回（运维/调试）

- `POST /api/v1/ai/memory/recall`
  - 支持 `include_trace=true`，返回召回解释（候选池/权重/阈值等）

额外可观测接口：

- `GET /api/v1/ai/memory/trace`：最近一次 recall 的 trace

---

## 五、总结晋升（短→中→长：日/周总结）

### 1) 每日总结（daily）

由 `AICommandExecutor` 自动生成（幂等）：

- 1 条 `daily_summary`（WORKING，近几天快速回顾）
- 1 条 `lesson_learned`（EXPERIENCE，经验/教训沉淀）

### 2) 每周总结（weekly）

同样由 `AICommandExecutor` 自动生成（幂等）：

- 1 条 `lesson_learned`（EXPERIENCE，周度规律/策略有效性/风险暴露）

总结状态查询：

- `GET /api/v1/ai/memory/summaries/status`

---

## 六、维护（清理、容量策略、备份、排障）

### 1) 过期清理（retention）

后端 `OptimizedMemorySystem.cleanup_expired()` 会按 layer retention 清理低 keep_score 的过期条目（CORE 不清）。

### 2) 磁盘阈值清理（disk policy，仅 WORKING/HISTORY）

当磁盘压力大时，优先清理低重要度的 `conversation/daily_summary` 等 WORKING/HISTORY 条目：

- 后端实现：`OptimizedMemorySystem.cleanup_by_disk_threshold(...)`
- 网关入口：`MemoryGateway.enforce_disk_policy()`
- 手动触发 API：`POST /api/v1/ai/memory/disk-policy/run`

配置（建议通过环境变量覆盖）：

- `OPENCLAW__memory__disk_policy__max_bytes`
- `OPENCLAW__memory__disk_policy__min_importance`

> 默认 `max_bytes=0` 表示不启用阈值清理。

### 3) 备份建议（强烈建议）

- **结构化记忆**：定期备份 `data/memory/`（或容器内 `/app/data/memory/`）
- **治理层文档**：备份 `workspace/*.md`
- 重要升级/迁移前做一次快照（可配合 `backups/`）

### 4) 常见问题

- **API 端口未监听 / health 不稳定**：外部依赖（交易所网络）可能阻塞启动链路。当前系统已调整为 **先启动 API 再启动交易系统主流程**，确保排障入口可用。
- **召回结果不相关**：
  - 检查写入时是否带 `symbol:*`、`kind:*` tags
  - 调整 `OPENCLAW__memory__retrieval__min_score` 与权重
  - 用 `include_trace=true` 或 `/ai/memory/trace` 观察召回过程

### 5) 配置固化（`data/config/memory.json`）

- 路径：`data/config/memory.json`（与 `default.yml` 等一起被 `ConfigManager` 加载）。
- **重要**：该文件必须以顶层 **`"memory": { ... }`** 包裹，以便深合并到 `DEFAULT_CONFIG["memory"]`（与 section 名一致）。
- 建议在此维护的块：
  - **`retrieval`**：混合检索权重、`min_score`、rerank 插槽
  - **`auto_capture`**：噪音过滤、按 category 的最小 importance
  - **`disk_policy`**：`max_bytes`（0 表示不启用）、`min_importance`
  - **`dedup`**：交易类写入幂等（见下节）
  - **`quality_metrics`**：如 `short_content_threshold`（质量统计用）

环境变量仍可用 `OPENCLAW__memory__...` 覆盖文件中的值（适合密钥与临时调参）。

### 6) 交易/风控写入幂等（dedup）

`MemoryGateway.store` 对 **`trade_record` / `risk_event`**（可在配置中扩展 `dedup.categories`）在 **`dedup.window_sec`** 时间窗内按指纹去重：若已存在相同指纹的记忆，则 **返回已有 `memory_id`**，不再新建条目。

指纹生成逻辑：`src/modules/memory/memory_schema.py` 的 `trade_idempotency_fingerprint`（优先级：`idempotency_key` > `order_id` > `client_oid` > `position_key` > SLTP 相关字段 > 开平仓价位数量时间片）。

SL/TP 触发写入会显式带上 `metadata.idempotency_key`（见 `stop_loss_take_profit`）。

### 7) 质量指标与召回命中率（可观测）

- **`GET /api/v1/ai/memory/quality`**：返回 `quality`（分布、空内容占比、重复 `idempotency_key` Top 列表等）与进程内 **`recall` 命中率**（自进程启动以来统计，重启清零）。
- **`GET /api/v1/ai/memory/stats`**：一并包含 `quality` 与 `gateway.recall`，适合总览。

### 8) 盘点与可选归档脚本

只读扫描 + 可选把「记忆根目录下的零散文件」移到归档目录（不删 JSON 分层内的记忆文件）：

```bash
python3 scripts/memory_inventory_archive.py --roots data/memory workspace/memory --report /tmp/memory_inventory.json
python3 scripts/memory_inventory_archive.py --roots data/memory --archive --archive-to data/memory/_archive/manual_$(date +%Y%m%d)
```

---

## 七、修改与扩展（开发者指南）

### 1) 新增/调整分类与 tags 规范

优先修改：

- `src/modules/memory/memory_schema.py`
- `src/modules/memory/memory_gateway.py`（category -> layer/category 映射）

### 2) 新增“自动捕获/提取”写入点

原则：
- **事件完成后写**（成功/失败都应记录，失败记录为 risk_event 或 system_state）
- **带幂等信息**（订单号、日期、策略 id、trace key）
- **短而原子**（长内容交给 daily/weekly summary 汇总）

### 3) Provider 升级路线（可选增强）

当前 `native` provider 以 BM25/keyword overlap 为主。后续可扩展：

- `src/modules/memory/providers/` 新增向量库 provider（如 LanceDB）
- 开启/接入 rerank（目前为插槽/框架位）
- 增强“数据质量”条目与召回权重（交易优先）

---

## 八、与现有文档关系

- 对齐/迁移背景：
  - `docs/MEMORY_UNIFICATION_BLUEPRINT.md`
  - `docs/MEMORY_ARCHITECTURE_ALIGNMENT.md`

本文档是**日常使用与运维/开发的“操作手册”**版本。

