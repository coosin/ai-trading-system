# OpenClaw Trading 文档中心

本目录是当前系统的正式文档集。根目录 `README.md` 只保留快速启动和核心入口。

## 当前系统基线

- 运行方式：裸机 `.venv` + `scripts/start-openclaw-trading.sh`，systemd 调用同一脚本。
- 主配置：`config/config.yaml`；本机覆盖：`config/local.yaml`；密钥：根目录 `.env`。
- API 基址：优先使用 `OPENCLAW_API_BASE`，默认 `http://127.0.0.1:8000`。
- 标准接口：`/api/v1/{domain}/...`。
- 接口发现：`GET /api/v1/surface/registry` 和兼容 `GET /api/v1/modules/surface/registry`。
- 交易执行：真实写入必须经过 `ExecutionGateway`，默认单写者为 `ai_core`。

## 核心文档

| 文档 | 用途 |
| --- | --- |
| [ENGINEERING.md](./ENGINEERING.md) | 工程架构、配置模型、模块边界 |
| [STANDARD_DOMAIN_ARCHITECTURE.md](./STANDARD_DOMAIN_ARCHITECTURE.md) | 标准域、接口分层、写路径规则 |
| [API_REFERENCE.md](./API_REFERENCE.md) | 标准 REST API、兼容接口、鉴权与响应约定 |
| [OPERATIONS.md](./OPERATIONS.md) | 部署、systemd、网络、巡检、排障 |
| [DEVELOPMENT.md](./DEVELOPMENT.md) | 本地开发、测试、文档一致性要求 |
| [OPENCLAW_INTEGRATION_GUIDE.md](./OPENCLAW_INTEGRATION_GUIDE.md) | 外部控制面、机器人、MCP/CLI 对接 |
| [MCP_BASELINE.md](./MCP_BASELINE.md) | MCP 定位、fallback adapter、工具安全边界 |
| [TRADING_TUNING_GUIDE.md](./TRADING_TUNING_GUIDE.md) | 交易门控、仓位、SLTP、学习闭环调参 |
| [TRADING_DEBUG_PLAYBOOK.md](./TRADING_DEBUG_PLAYBOOK.md) | 交易排障与复测流程 |
| [DAILY_HOSTING_ACCEPTANCE.md](./DAILY_HOSTING_ACCEPTANCE.md) | 每日托管快验收 |
| [CHANGELOG.md](./CHANGELOG.md) | 重要变更记录 |

## 专题文档

| 文档 | 用途 |
| --- | --- |
| [AI_HANDOFF_OPTIMIZATION_VERIFICATION_2026Q2.md](./AI_HANDOFF_OPTIMIZATION_VERIFICATION_2026Q2.md) | AI 维护交接、验证命令与调参方法 |
| [OPENCLAW_AGENTIC_CRYPTO_UPGRADE_PLAN_2026.md](./OPENCLAW_AGENTIC_CRYPTO_UPGRADE_PLAN_2026.md) | Agentic crypto 升级路线 |
| [RESEARCH_EDUCATION_UPGRADE_BLUEPRINT_2026.md](./RESEARCH_EDUCATION_UPGRADE_BLUEPRINT_2026.md) | 研究、教育和复盘体系 |
| [OKX_SOURCE_REFERENCE_MAP.md](./OKX_SOURCE_REFERENCE_MAP.md) | OKX 字段和端点映射 |
| [memory/MEMORY_LIBRARY_GUIDE.md](./memory/MEMORY_LIBRARY_GUIDE.md) | Memory 模块配置与运维 |
| [../deploy/HOST_CLASH_EGRESS.md](../deploy/HOST_CLASH_EGRESS.md) | 宿主机 Clash 出站约定 |

## 模板与归档

- [templates/WEEKLY_RESEARCH_REVIEW.md](./templates/WEEKLY_RESEARCH_REVIEW.md)
- [templates/TRADING_RESEARCH_EXPERIMENT_CARD.md](./templates/TRADING_RESEARCH_EXPERIMENT_CARD.md)
- [archive/HISTORICAL_STATUS_AND_CLEANUP_2026Q2.md](./archive/HISTORICAL_STATUS_AND_CLEANUP_2026Q2.md)

## 文档一致性

修改 API、配置或启动方式后至少执行：

```bash
python3 scripts/check_docs_runtime_consistency.py
pytest -q tests/unit/test_standard_domain_api.py tests/e2e/test_api_surface_commander_chain.py
```

运行时接口权威来源始终是 `/openapi.json` 和 `/docs`。

