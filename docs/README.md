# OpenClaw Trading — 文档中心

本目录为**正式文档集**。根目录 [README.md](../README.md) 仅保留简介与快速开始。

当前仓库以**本地化运行**为主路径：`scripts/start-openclaw-trading.sh`（或调用同一脚本的 systemd）。`python -m src.main` 仅保留给前台调试，不建议作为长期托管入口。

涉及地址/代理的说明请优先看 `docs/OPERATIONS.md` 的“运行模式选择”章节。

## 1) 核心标准文档（长期维护）

| 文档 | 说明 |
|------|------|
| [**ENGINEERING.md**](./ENGINEERING.md) | 工程主文档：架构、配置模型、模块边界 |
| [**OPERATIONS.md**](./OPERATIONS.md) | 运维主文档：部署、网络、健康、巡检 |
| [**DEVELOPMENT.md**](./DEVELOPMENT.md) | 开发主文档：环境、测试、目录、规范 |
| [**API_REFERENCE.md**](./API_REFERENCE.md) | API 主文档：REST/WebSocket、鉴权、对接建议；含 **API 基址**（`OPENCLAW_API_BASE`）、**`surface/registry`** 的 `read_pipeline` / `api_base_env` 规范 |
| [**TRADING_TUNING_GUIDE.md**](./TRADING_TUNING_GUIDE.md) | 交易参数调优：开平仓门控、仓位、SLTP、学习闭环 |
| [**TRADING_DEBUG_PLAYBOOK.md**](./TRADING_DEBUG_PLAYBOOK.md) | 交易调试手册：开平仓排障、诊断路径、复测流程 |
| [**RESEARCH_EDUCATION_UPGRADE_BLUEPRINT_2026.md**](./RESEARCH_EDUCATION_UPGRADE_BLUEPRINT_2026.md) | 研究与教育升级蓝图：把学习科学方法嵌入交易研发、复盘和治理流程 |
| [**OPENCLAW_AGENTIC_CRYPTO_UPGRADE_PLAN_2026.md**](./OPENCLAW_AGENTIC_CRYPTO_UPGRADE_PLAN_2026.md) | 面向 AI 智能体、流式数据与加密市场结构的 OpenClaw 定制升级方案 |
| [**CHANGELOG.md**](./CHANGELOG.md) | 变更记录 |

配套模板：

- [**templates/WEEKLY_RESEARCH_REVIEW.md**](./templates/WEEKLY_RESEARCH_REVIEW.md)：每周研究复盘模板，现已纳入 `workflow_focus` / 对账阻断复盘位

## 2) 专题文档（按需）

| 文档 | 说明 |
|------|------|
| [**AI_HANDOFF_OPTIMIZATION_VERIFICATION_2026Q2.md**](./AI_HANDOFF_OPTIMIZATION_VERIFICATION_2026Q2.md) | **AI 维护交接**：2026 Q2 测试/优化结果固化、验证与调参方法 |
| [**OPENCLAW_INTEGRATION_GUIDE.md**](./OPENCLAW_INTEGRATION_GUIDE.md) | OpenClaw 对接（读写接口、验收、审计） |
| [**DAILY_HOSTING_ACCEPTANCE.md**](./DAILY_HOSTING_ACCEPTANCE.md) | 每日托管验收（值守快检） |
| [**MCP_BASELINE.md**](./MCP_BASELINE.md) | MCP 基线与落地建议 |
| [**OKX_SOURCE_REFERENCE_MAP.md**](./OKX_SOURCE_REFERENCE_MAP.md) | OKX 字段/端点映射 |
| [**memory/MEMORY_LIBRARY_GUIDE.md**](./memory/MEMORY_LIBRARY_GUIDE.md) | Memory 模块配置与运维要点 |
| [**../deploy/HOST_CLASH_EGRESS.md**](../deploy/HOST_CLASH_EGRESS.md) | 宿主机 Clash 出站与应用进程代理约定 |

## 3) 历史归档（只读）

| 文档 | 说明 |
|------|------|
| [**archive/HISTORICAL_STATUS_AND_CLEANUP_2026Q2.md**](./archive/HISTORICAL_STATUS_AND_CLEANUP_2026Q2.md) | 2026Q2 阶段性同步与清理历史摘要 |

## 非规范内容

- `../workspace/`：人格与运行时文本，非 API 规范。  
- `../USER_PROFILE.md`、`../TRADING_SOUL.md`：用户侧叙事，按需阅读。

## API 权威来源

**`GET /openapi.json`** 或浏览器 **`/docs`**。
