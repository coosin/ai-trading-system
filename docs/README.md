# OpenClaw Trading — 文档中心

本目录为**唯一规范的正式文档集**。根目录 `README.md` 仅保留项目简介与快速开始；细节以本文档索引为准。

| 文档 | 说明 |
|------|------|
| [**ENGINEERING.md**](./ENGINEERING.md) | **工程文档（主文档）**：架构、启动流程、目录与模块、配置与环境变量、对接关系、API 总览 |
| [**OPERATIONS.md**](./OPERATIONS.md) | 运维：Docker 部署、网络/代理基线、健康检查、脚本、排障要点 |
| [**DEVELOPMENT.md**](./DEVELOPMENT.md) | 开发环境、测试、调试与项目结构说明 |
| [**CHANGELOG.md**](./CHANGELOG.md) | 变更记录 |
| [**memory/MEMORY_LIBRARY_GUIDE.md**](./memory/MEMORY_LIBRARY_GUIDE.md) | MemoryGateway：结构、写入/召回、维护 |
| [**OKX_SOURCE_REFERENCE_MAP.md**](./OKX_SOURCE_REFERENCE_MAP.md) | OKX 字段/端点对照（深度参考，可选阅读） |

## 非规范内容（运行时/人格）

- `../workspace/`：司令部人格、交易信念等运行时文本，**不属于** API/架构规范文档。
- `../USER_PROFILE.md`、`../TRADING_SOUL.md`：用户侧叙事/设定，按需阅读。

## API 权威来源

运行时 OpenAPI：**`GET /openapi.json`** 或浏览器 **`/docs`**。工程说明中的路由表为摘要，以 OpenAPI 为准。
