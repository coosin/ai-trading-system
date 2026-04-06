# OpenClaw Trading System

**全智能量化交易系统** - 基于AI的自主交易解决方案

[![Version](https://img.shields.io/badge/version-2.1.0-blue.svg)](https://github.com/openclaw-trading)
[![Python](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)

---

## 核心特性

- **AI智能决策** - 基于百度千帆 DeepSeek-V3.2 模型
- **自动化交易** - 7x24小时自主监控和执行
- **风险控制** - 多层次风险管理，自动平仓保护
- **记忆系统** - 长期记忆和上下文理解
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
# 使用Docker Compose启动
docker-compose up -d

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

## 文档导航

| 文档 | 描述 |
|------|------|
| [**系统架构文档**](./ARCHITECTURE.md) | 详细的系统架构、模块说明、配置指南 |
| [**快速开始指南**](./快速开始指南.md) | 环境搭建和开发流程 |
| [**AI记忆文件**](./workspace/) | AI核心信念、身份定义、交易知识 |

---

## 系统要求

- **操作系统**: Ubuntu 22.04+ / macOS 12+ / Windows 10+ (WSL2)
- **Python**: 3.11+
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

### 交易配置

```yaml
# data/config/default.yml
trading:
  mode: "simulation"    # simulation（模拟）/ live（实盘）
  exchange: "okx"
  max_positions: 5
  max_loss_per_trade: 0.02
```

### 配置覆盖（推荐）

- 推荐使用：`OPENCLAW__section__key=value`（例如 `OPENCLAW__api__port=8080`）
- 旧格式：`TRADING_SECTION_KEY=value` 仍兼容，但已弃用

### 记忆系统配置（MemoryGateway）

- **核心入口**：系统内部统一通过 `MemoryGateway` 读写记忆（带 `scope`、trace、可选 rerank）。
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
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看日志
docker logs -f openclaw-trading

# 进入容器
docker exec -it openclaw-trading bash
```

---

## 项目状态

- ✅ AI决策引擎 - 运行正常
- ✅ OKX交易所接口 - 已连接
- ✅ 风险控制系统 - 已启用
- ✅ Telegram通知 - 已配置
- ✅ 记忆系统 - 已初始化
- ✅ 真实回测指标 - 已接入（收益/回撤/夏普/胜率）
- ✅ 参数自动优化 - 已接入（基于行情网格搜索）
- ✅ 多源数据融合 - 初始化稳定（修复异步注册错误）

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

**版本**: 2.1.1 | **更新日期**: 2026-04-07
