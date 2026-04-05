# OpenClaw Trading System - 系统架构文档

**版本**: 2.0.0  
**最后更新**: 2026-04-05  
**状态**: 生产运行中

---

## 目录

1. [系统概述](#1-系统概述)
2. [技术栈](#2-技术栈)
3. [系统架构](#3-系统架构)
4. [核心模块](#4-核心模块)
5. [数据流](#5-数据流)
6. [部署架构](#6-部署架构)
7. [配置说明](#7-配置说明)
8. [API接口](#8-api接口)
9. [安全机制](#9-安全机制)
10. [监控告警](#10-监控告警)

---

## 1. 系统概述

OpenClaw Trading System 是一个**全智能、自主运行的量化交易系统**，具备以下核心能力：

- **AI智能决策**: 基于百度千帆 DeepSeek-V3.2 模型的智能分析和决策
- **自动化交易**: 7x24小时自主监控和交易执行
- **风险控制**: 多层次风险管理和自动干预机制
- **记忆系统**: 长期记忆和上下文理解能力
- **自我进化**: 从交易经验中持续学习和优化

### 运行模式

- **模拟交易**: 当前运行模式，使用虚拟资金进行合约交易
- **交易所**: OKX（支持扩展其他交易所）

---

## 2. 技术栈

| 类别 | 技术选型 | 版本 |
|------|----------|------|
| **编程语言** | Python | 3.11+ |
| **异步框架** | asyncio, aiohttp | 最新 |
| **AI模型** | 百度千帆 DeepSeek-V3.2 | - |
| **数据库** | Redis | 7+ |
| **容器化** | Docker, Docker Compose | 20.10+ |
| **交易所** | OKX API | V5 |
| **消息通知** | Telegram Bot | - |

---

## 3. 系统架构

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    用户交互层 (UI Layer)                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Telegram Bot│  │  Web API    │  │   前端界面(可选)    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   核心决策层 (Core Layer)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ 主控制器    │  │ AI决策引擎  │  │ 交易引擎    │         │
│  │MainController│ │DecisionEngine│ │TradingEngine│         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ 记忆系统    │  │ 风险控制    │  │ 策略管理    │         │
│  │MemorySystem │ │RiskController│ │StrategyMgr  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    数据处理层 (Data Layer)                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ 数据采集    │  │ 数据融合    │  │ 数据存储    │         │
│  │DataCollector│ │DataFusion   │ │DataStorage  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    基础设施层 (Infrastructure)               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Docker容器  │  │ Redis缓存   │  │ 代理管理    │         │
│  │ Container   │  │ Cache       │  │ ProxyManager│         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 目录结构

```
/home/cool/.openclaw-trading/
├── src/
│   ├── main.py                    # 主入口
│   └── modules/
│       ├── core/                  # 核心模块
│       │   ├── ai_trading_engine.py       # AI交易引擎
│       │   ├── ai_core_decision_engine.py # AI决策引擎
│       │   ├── ai_memory.py               # AI记忆系统
│       │   ├── enhanced_llm_manager.py    # LLM管理器
│       │   ├── llm_integration.py         # LLM集成
│       │   ├── account_risk_monitor.py    # 账户风险监控
│       │   ├── unified_memory_system.py   # 统一记忆系统
│       │   ├── strategy_optimizer.py      # 策略优化器
│       │   └── ...
│       ├── exchanges/             # 交易所接口
│       │   ├── okx.py             # OKX交易所
│       │   ├── binance.py         # Binance交易所
│       │   └── exchange_base.py   # 交易所基类
│       ├── notification/          # 通知模块
│       │   └── telegram_bot.py    # Telegram机器人
│       ├── data/                  # 数据模块
│       │   ├── unified_data_manager.py    # 统一数据管理
│       │   ├── realtime_data_collector.py # 实时数据采集
│       │   └── ...
│       ├── strategies/            # 策略模块
│       ├── skills/                # 技能模块
│       ├── risk/                  # 风险管理
│       ├── api/                   # API服务
│       └── monitoring/            # 监控模块
├── workspace/                     # AI记忆文件
│   ├── SOUL.md                    # 核心信念
│   ├── IDENTITY.md                # 身份定义
│   ├── USER.md                    # 用户信息
│   ├── TRADING.md                 # 交易知识
│   └── INSTRUCTIONS.md            # 工作指令
├── data/
│   ├── config/                    # 配置文件
│   │   ├── default.yml            # 默认配置
│   │   └── proxy.json             # 代理配置
│   └── memory/                    # 记忆数据
├── logs/                          # 日志文件
├── docker-compose.yml             # Docker编排
├── Dockerfile                     # Docker镜像
├── requirements.txt               # Python依赖
└── .env                          # 环境变量
```

---

## 4. 核心模块

### 4.1 主控制器 (MainController)

**文件**: `src/modules/main_controller.py`

**职责**:
- 协调所有模块的运行
- 处理模块间通信和依赖
- 系统状态管理和故障恢复
- 提供统一的管理接口

### 4.2 AI决策引擎 (AICoreDecisionEngine)

**文件**: `src/modules/core/ai_core_decision_engine.py`

**职责**:
- 接收市场数据和用户指令
- 调用LLM进行智能分析
- 生成交易决策
- 风险评估和控制

### 4.3 AI交易引擎 (AITradingEngine)

**文件**: `src/modules/core/ai_trading_engine.py`

**职责**:
- 执行交易决策
- 订单管理
- 持仓监控
- 自动平仓和风险控制

### 4.4 记忆系统 (Memory System)

**文件**: 
- `src/modules/core/ai_memory.py`
- `src/modules/core/unified_memory_system.py`

**职责**:
- 长期记忆存储（workspace/*.md文件）
- 短期记忆管理
- 记忆检索和注入
- 上下文构建

**记忆文件说明**:
| 文件 | 用途 | 大小限制 |
|------|------|----------|
| SOUL.md | AI核心信念和价值观 | 800字符 |
| IDENTITY.md | AI身份定义和能力 | 600字符 |
| USER.md | 用户偏好和设置 | 400字符 |
| TRADING.md | 交易知识和经验 | 动态 |
| INSTRUCTIONS.md | 工作指令和任务 | 300字符 |

### 4.5 LLM管理器 (EnhancedLLMManager)

**文件**: `src/modules/core/enhanced_llm_manager.py`

**职责**:
- 多模型管理（百度千帆、讯飞星火等）
- API调用和错误处理
- 模型切换和负载均衡
- Prompt构建和优化

**当前配置**:
- 主模型: 百度千帆 DeepSeek-V3.2
- API端点: `https://qianfan.baidubce.com/v2/coding/chat/completions`

### 4.6 风险监控 (AccountRiskMonitor)

**文件**: `src/modules/core/account_risk_monitor.py`

**职责**:
- 实时监控账户风险
- 持仓风险评估
- 风险预警生成
- 自动风险处理

**风险等级**:
| 等级 | 触发条件 | 处理方式 |
|------|----------|----------|
| LOW | 正常状态 | 继续监控 |
| HIGH | 接近预警线 | 发送警告 |
| CRITICAL | 触及危险线 | 自动平仓 |

### 4.7 交易所接口 (Exchange Connector)

**文件**: `src/modules/exchanges/okx.py`

**职责**:
- OKX API对接
- 订单执行
- 持仓查询
- 账户管理

---

## 5. 数据流

### 5.1 交易决策流程

```
用户指令/市场数据
       │
       ▼
┌─────────────────┐
│   主控制器      │
│ MainController  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  数据采集层     │
│ DataCollector   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  记忆注入       │
│ MemoryInjection │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  AI决策引擎     │
│ DecisionEngine  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  风险评估       │
│ RiskAssessment  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  交易执行       │
│ TradeExecution  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  结果反馈       │
│ Feedback        │
└─────────────────┘
```

### 5.2 记忆注入流程

```
用户输入
    │
    ▼
┌─────────────────┐
│ 加载工作区文件  │
│ SOUL/IDENTITY   │
│ USER/TRADING    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 构建记忆上下文  │
│ ContextBuilder  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 注入到Prompt    │
│ PromptInjection │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   LLM处理       │
└─────────────────┘
```

---

## 6. 部署架构

### 6.1 Docker容器化部署

```yaml
# docker-compose.yml
services:
  openclaw-trading:
    build: .
    container_name: openclaw-trading
    restart: always
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./workspace:/app/workspace
    environment:
      - WORKSPACE_PATH=/app/workspace
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    container_name: openclaw-redis
    restart: always
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data

volumes:
  redis-data:
```

### 6.2 网络配置

- **代理**: Docker容器通过 `host.docker.internal:7890` 访问宿主机代理
- **Redis**: 容器内部通信
- **API**: 端口8000对外暴露

---

## 7. 配置说明

### 7.1 环境变量 (.env)

```bash
# 百度千帆API
QIANFAN_API_KEY=bce-v3/ALTAKSP-xxx/xxx

# OKX交易所
OKX_API_KEY=xxx
OKX_SECRET_KEY=xxx
OKX_PASSPHRASE=xxx

# Telegram Bot
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx

# 代理配置
HTTP_PROXY=http://host.docker.internal:7890
HTTPS_PROXY=http://host.docker.internal:7890
```

### 7.2 系统配置 (data/config/default.yml)

```yaml
# API服务器配置
api:
  host: "0.0.0.0"
  port: 8000
  enable_cors: true

# 控制器配置
controller:
  auto_restart_modules: true
  max_restart_attempts: 3
  health_check_interval: 30

# 交易配置
trading:
  mode: "simulation"  # simulation / live
  exchange: "okx"
  max_positions: 5
  max_loss_per_trade: 0.02

# 风险配置
risk:
  max_daily_loss: 0.05
  max_drawdown: 0.15
  critical_risk_auto_close: true

# LLM配置
llm:
  provider: "qianfan"
  model: "deepseek-v3.2"
  temperature: 0.7
  max_tokens: 4096
```

---

## 8. API接口

### 8.1 REST API

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/v1/status` | GET | 系统状态 |
| `/api/v1/positions` | GET | 当前持仓 |
| `/api/v1/orders` | GET | 订单历史 |
| `/api/v1/account` | GET | 账户信息 |

### 8.2 Telegram Bot命令

| 命令 | 描述 |
|------|------|
| `/start` | 启动系统 |
| `/stop` | 停止系统 |
| `/status` | 查看状态 |
| `/positions` | 查看持仓 |
| `/balance` | 查看余额 |

---

## 9. 安全机制

### 9.1 API密钥管理

- 所有API密钥存储在 `.env` 文件中
- 不提交到版本控制
- 容器运行时通过环境变量注入

### 9.2 风险控制

- 单笔交易最大亏损: 2%
- 日内最大亏损: 5%
- 最大回撤: 15%
- 黑名单机制: 禁止交易指定币种

### 9.3 自动保护

- CRITICAL风险自动平仓
- 异常检测自动告警
- 系统故障自动恢复

---

## 10. 监控告警

### 10.1 日志系统

- **应用日志**: `logs/app.log`
- **交易日志**: `logs/trading.log`
- **错误日志**: `logs/error.log`

### 10.2 Telegram通知

- 交易执行通知
- 风险预警通知
- 系统状态通知
- 错误告警通知

### 10.3 健康检查

```bash
# 检查容器状态
docker ps | grep openclaw

# 检查应用健康
curl http://localhost:8000/health

# 查看实时日志
docker logs -f openclaw-trading
```

---

## 附录

### A. 常见问题

**Q: 如何更新API密钥？**
A: 编辑 `.env` 文件，然后重启容器: `docker-compose restart`

**Q: 如何查看交易日志？**
A: `docker logs openclaw-trading | grep -i trade`

**Q: 如何手动平仓？**
A: 通过Telegram发送平仓指令，或调用API接口

### B. 维护指南

1. **日常检查**: 查看Telegram通知和日志
2. **周度检查**: 检查账户余额和持仓
3. **月度检查**: 备份数据和配置

### C. 相关文档

- [快速开始指南](./快速开始指南.md)
- [AI记忆文件](./workspace/)
- [配置参考](./data/config/)

---

**文档维护者**: OpenClaw Trading System Team  
**最后审核**: 2026-04-05
