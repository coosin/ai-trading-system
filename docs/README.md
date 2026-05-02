# OpenClaw Trading — 文档中心

本目录为**正式文档集**。根目录 [README.md](../README.md) 仅保留简介与快速开始。

当前仓库默认维护两种运行模式：

- **本地化运行（当前主路径）**：`.venv` + `python -m src.main`
- **Docker 运行（兼容路径）**：`docker compose ...`

涉及地址/代理的说明请优先看 `docs/OPERATIONS.md` 的“运行模式选择”章节。

## 1) 核心标准文档（长期维护）

| 文档 | 说明 |
|------|------|
| [**ENGINEERING.md**](./ENGINEERING.md) | 工程主文档：架构、配置模型、模块边界 |
| [**OPERATIONS.md**](./OPERATIONS.md) | 运维主文档：部署、网络、健康、巡检 |
| [**DEVELOPMENT.md**](./DEVELOPMENT.md) | 开发主文档：环境、测试、目录、规范 |
| [**API_REFERENCE.md**](./API_REFERENCE.md) | API 主文档：REST/WebSocket、鉴权、对接建议 |
| [**TRADING_TUNING_GUIDE.md**](./TRADING_TUNING_GUIDE.md) | 交易参数调优：开平仓门控、仓位、SLTP、学习闭环 |
| [**TRADING_DEBUG_PLAYBOOK.md**](./TRADING_DEBUG_PLAYBOOK.md) | 交易调试手册：开平仓排障、诊断路径、复测流程 |
| [**CHANGELOG.md**](./CHANGELOG.md) | 变更记录 |

## 2) 专题文档（按需）

| 文档 | 说明 |
|------|------|
| [**AI_HANDOFF_OPTIMIZATION_VERIFICATION_2026Q2.md**](./AI_HANDOFF_OPTIMIZATION_VERIFICATION_2026Q2.md) | **AI 维护交接**：2026 Q2 测试/优化结果固化、验证与调参方法 |
| [**OPENCLAW_INTEGRATION_GUIDE.md**](./OPENCLAW_INTEGRATION_GUIDE.md) | OpenClaw 对接（读写接口、验收、审计） |
| [**DAILY_HOSTING_ACCEPTANCE.md**](./DAILY_HOSTING_ACCEPTANCE.md) | 每日托管验收（值守快检） |
| [**MCP_BASELINE.md**](./MCP_BASELINE.md) | MCP 基线与落地建议 |
| [**OKX_SOURCE_REFERENCE_MAP.md**](./OKX_SOURCE_REFERENCE_MAP.md) | OKX 字段/端点映射 |
| [**memory/MEMORY_LIBRARY_GUIDE.md**](./memory/MEMORY_LIBRARY_GUIDE.md) | Memory 模块配置与运维要点 |
| [**../deploy/HOST_CLASH_EGRESS.md**](../deploy/HOST_CLASH_EGRESS.md) | 宿主机 Clash 出站与容器代理规范 |

## 3) 历史归档（只读）

| 文档 | 说明 |
|------|------|
| [**archive/HISTORICAL_STATUS_AND_CLEANUP_2026Q2.md**](./archive/HISTORICAL_STATUS_AND_CLEANUP_2026Q2.md) | 2026Q2 阶段性同步与清理历史摘要 |

## 非规范内容

- `../workspace/`：人格与运行时文本，非 API 规范。  
- `../USER_PROFILE.md`、`../TRADING_SOUL.md`：用户侧叙事，按需阅读。

## API 权威来源

**`GET /openapi.json`** 或浏览器 **`/docs`**。
