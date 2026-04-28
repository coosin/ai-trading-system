# OpenClaw Trading — 文档中心

本目录为**正式文档集**。根目录 [README.md](../README.md) 仅保留简介与快速开始。

当前仓库默认维护两种运行模式：

- **本地化运行（当前主路径）**：`.venv` + `python -m src.main`
- **Docker 运行（兼容路径）**：`docker compose ...`

涉及地址/代理的说明请优先看 `docs/OPERATIONS.md` 的“运行模式选择”章节。

| 文档 | 说明 |
|------|------|
| [**ENGINEERING.md**](./ENGINEERING.md) | **工程主文档**：架构、配置模型、Docker、模块索引 |
| [**OPERATIONS.md**](./OPERATIONS.md) | 运维：Compose、网络/代理、健康检查、排障 |
| [**DEVELOPMENT.md**](./DEVELOPMENT.md) | 开发环境、测试（含 Pytest 9）、目录结构 |
| [**TRADING_TUNING_GUIDE.md**](./TRADING_TUNING_GUIDE.md) | 交易调参：开平仓门控、仓位/加仓、SLTP 与学习引擎验收 |
| [**CHANGELOG.md**](./CHANGELOG.md) | 变更记录 |
| [**memory/MEMORY_LIBRARY_GUIDE.md**](./memory/MEMORY_LIBRARY_GUIDE.md) | Memory：配置段与运维要点 |
| [**API_REFERENCE.md**](./API_REFERENCE.md) | API 与 WebSocket 约定、监控告警合并说明（权威以运行时 `/openapi.json` 为准） |
| [**MCP_BASELINE.md**](./MCP_BASELINE.md) | MCP 基础、OKX Agent Trade Kit 对标与落地方向 |
| [**DAILY_HOSTING_ACCEPTANCE.md**](./DAILY_HOSTING_ACCEPTANCE.md) | 每日托管验收清单（3~5 步快速确认） |
| [**OPENCLAW_INTEGRATION_GUIDE.md**](./OPENCLAW_INTEGRATION_GUIDE.md) | OpenClaw 对接手册（读写接口、验收与审计） |
| [**OKX_SOURCE_REFERENCE_MAP.md**](./OKX_SOURCE_REFERENCE_MAP.md) | OKX 字段/端点参考 |
| [**../deploy/HOST_CLASH_EGRESS.md**](../deploy/HOST_CLASH_EGRESS.md) | 宿主机 Clash 出站、容器代理与验收要点 |

## 非规范内容

- `../workspace/`：人格与运行时文本，非 API 规范。  
- `../USER_PROFILE.md`、`../TRADING_SOUL.md`：用户侧叙事，按需阅读。

## API 权威来源

**`GET /openapi.json`** 或浏览器 **`/docs`**。
