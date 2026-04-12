# OpenClaw Trading System

**全智能量化交易系统** - 基于AI的自主交易解决方案

[![Version](https://img.shields.io/badge/version-2.1.0-blue.svg)](https://github.com/openclaw-trading)
[![Python](https://img.shields.io/badge/python-3.12+-green.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)

---

## 核心特性

- **AI智能决策** - 基于百度千帆 DeepSeek-V3.2 模型
- **自动化交易** - 7x24小时自主监控和执行
- **风险控制** - 多层次风险管理，自动平仓保护
- **记忆系统** - 长期记忆和上下文理解
- **自动策略研究** - 策略 DSL + 候选生成 + Walk-forward 门控 + 自动发布
- **可追溯审计/版本** - 策略参数优化自动版本递增，并写入审计/记忆
- **智能通知降噪** - 去重冷却 + 限流 + 摘要汇总，避免告警刷屏
- **容器化部署** - Docker一键部署，开箱即用

---

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-org/openclaw-trading.git
cd openclaw-trading
```

### 2. 配置环境

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑配置文件，填入API密钥
nano .env
```

### 3. 启动服务

```bash
# 使用Docker Compose启动（推荐 v2）
docker compose up -d

# 查看日志
docker logs -f openclaw-trading
```

### 4. 验证运行

```bash
# 健康检查
curl http://localhost:8000/health

# 查看API文档
open http://localhost:8000/docs
```

---

## 文档（统一入口）

**正式文档集**见 **[docs/README.md](./docs/README.md)**。核心文件：

| 文档 | 说明 |
|------|------|
| [docs/ENGINEERING.md](./docs/ENGINEERING.md) | **工程文档**：架构、启动流程、配置、对接、API 总览 |
| [docs/OPERATIONS.md](./docs/OPERATIONS.md) | 运维：Docker、代理/网络、巡检、排障 |
| [docs/DEVELOPMENT.md](./docs/DEVELOPMENT.md) | 开发与测试 |
| [docs/CHANGELOG.md](./docs/CHANGELOG.md) | 变更记录 |

根目录 [ARCHITECTURE.md](./ARCHITECTURE.md)、[DEVELOPMENT.md](./DEVELOPMENT.md) 为跳转 stub。运行时人格与信念类文本见 [workspace/](./workspace/)；记忆库维护见 [docs/memory/MEMORY_LIBRARY_GUIDE.md](./docs/memory/MEMORY_LIBRARY_GUIDE.md)。

---

## 系统要求

- **操作系统**: Ubuntu 22.04+ / macOS 12+ / Windows 10+ (WSL2)
- **Python**: 3.12（Docker 镜像）；本地开发 3.11+ 亦可
- **Docker**: 20.10+
- **内存**: 4GB+ (推荐8GB)
- **磁盘**: 10GB+

---

## 主要模块

```
src/modules/
├── core/              # 核心引擎（AI决策、交易执行、记忆系统）
├── exchanges/         # 交易所接口（OKX、Binance）
├── notification/      # 通知系统（Telegram Bot）
├── data/              # 数据采集和处理
├── strategies/        # 交易策略
├── risk/              # 风险管理
└── api/               # REST API服务
```

---

## 配置说明

### 必需配置

```bash
# 百度千帆API（AI决策）
QIANFAN_API_KEY=your-api-key

# OKX交易所
OKX_API_KEY=your-api-key
OKX_SECRET_KEY=your-secret
OKX_PASSPHRASE=your-passphrase

# Telegram Bot（可选）
TELEGRAM_BOT_TOKEN=your-token
TELEGRAM_CHAT_ID=your-chat-id
```

### 代理配置（可选，默认不启用）

为避免容器被宿主机 `HTTP_PROXY/HTTPS_PROXY` 等环境变量“误伤”导致网络不稳定，容器内默认不启用系统代理变量。  
如需代理，请显式配置：

```bash
# 仅在确实需要代理时设置
OPENCLAW_HTTP_PROXY=http://host.docker.internal:7890
OPENCLAW_HTTPS_PROXY=http://host.docker.internal:7890
```

代理与网络基线见 **[docs/OPERATIONS.md](./docs/OPERATIONS.md)**（含 Clash/DNS 要点与 `production_network_baseline.py`）。

### 交易配置

```yaml
# 主入口：config/openclaw.yml（可选 data/config/local.yml 本机覆盖；密钥在 .env）
# 详见 config/openclaw.yml 文件头注释与 .env.example
trading:
  paper_trading: true
  max_position_size: 0.1
```

### 配置覆盖（推荐）

- 推荐使用：`OPENCLAW__section__key=value`（例如 `OPENCLAW__api__port=8080`）
- 旧格式：`TRADING_SECTION_KEY=value` 仍兼容，但已弃用

### 记忆系统配置（MemoryGateway）

- **核心入口**：系统内部统一通过 `MemoryGateway` 读写记忆（带 `scope`、trace、可选 rerank）。
- **文件配置**：`data/config/memory.json` 必须以顶层 **`"memory": { ... }`** 与配置段对齐；详见 [*记忆库使用与维护指南*](./docs/memory/MEMORY_LIBRARY_GUIDE.md)。
- **推荐配置方式**：使用 `OPENCLAW__memory__...` 覆盖。

常用覆盖示例：

```bash
# 开启/关闭混合检索模式（native provider）
OPENCLAW__memory__retrieval__mode=hybrid
OPENCLAW__memory__retrieval__vector_weight=0.7
OPENCLAW__memory__retrieval__bm25_weight=0.3
OPENCLAW__memory__retrieval__min_score=0.3

# rerank 插槽（默认关闭）
OPENCLAW__memory__retrieval__rerank__enabled=false
OPENCLAW__memory__retrieval__rerank__candidate_pool_size=12
```

### 记忆 API（REST）

统一记忆 API（`/api/v1`）：

- **写入**：`POST /api/v1/ai/memory/store`
- **检索**：`POST /api/v1/ai/memory/recall`（支持 `include_trace=true`）

---

## 常用命令

```bash
# 启动服务
docker compose up -d

# 停止服务
docker compose down

# 重启服务
docker compose restart

# 查看日志
docker logs -f openclaw-trading

# 进入容器
docker exec -it openclaw-trading bash
```

---

## 项目状态

以运行环境为准：使用 `curl http://localhost:8000/health` 与 `GET /api/v1/modules/commander/audit` 自检。历史交付项与细粒度变更见 **[docs/CHANGELOG.md](./docs/CHANGELOG.md)**。

---

## 贡献指南

欢迎贡献！请查看 [贡献指南](CONTRIBUTING.md) 了解详情。

---

## 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

---

## 联系方式

- **Issues**: [GitHub Issues](https://github.com/your-org/openclaw-trading/issues)
- **文档**: [在线文档](https://docs.openclaw-trading.com)

---

**版本**: 2.2.x | **文档整理**: 2026-04-11
