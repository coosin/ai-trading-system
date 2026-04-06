# OpenClaw Trading System - 系统架构文档

**版本**: 2.1.0  
**最后更新**: 2026-04-05  
**状态**: 生产运行中

---

## 目录

1. [系统概述](#1-系统概述)
2. [技术栈](#2-技术栈)
3. [系统架构](#3-系统架构)
4. [核心模块](#4-核心模块)
5. [新增模块 (V2.1)](#5-新增模块-v21)
6. [数据流](#6-数据流)
7. [部署架构](#7-部署架构)
8. [配置说明](#8-配置说明)
9. [API接口](#9-api接口)
10. [安全机制](#10-安全机制)
11. [监控告警](#11-监控告警)

---

## 1. 系统概述

OpenClaw Trading System 是一个**全智能、自主运行的量化交易系统**，具备以下核心能力：

- **AI智能决策**: 基于百度千帆 DeepSeek-V3.2 模型的智能分析和决策
- **自动化交易**: 7x24小时自主监控和交易执行
- **风险控制**: 多层次风险管理和自动干预机制
- **记忆系统**: 智能记忆管理，按需动态加载
- **自我进化**: 从交易经验中持续学习和优化
- **执行验证**: 命令执行结果可验证、可追溯

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
│  │ 智能记忆    │  │ 风险控制    │  │ 策略管理    │         │
│  │SmartMemory  │ │RiskController│ │StrategyMgr  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ 执行验证器  │  │ 止盈止损    │  │ 审计日志    │         │
│  │ExecVerifier │ │StopLossMgr  │ │AuditLogger  │         │
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
│       │   ├── main_controller.py         # 主控制器
│       │   ├── ai_trading_engine.py       # AI交易引擎
│       │   ├── ai_core_decision_engine.py # AI决策引擎
│       │   ├── ai_memory.py               # 智能记忆系统 V2.0
│       │   ├── enhanced_llm_manager.py    # LLM管理器
│       │   ├── llm_integration.py         # LLM集成
│       │   ├── account_risk_monitor.py    # 账户风险监控
│       │   ├── dynamic_position_manager.py # 动态仓位管理器
│       │   ├── correlation_monitor.py     # 品种相关性监控器
│       │   ├── strategy_hot_loader.py     # 策略热加载器
│       │   ├── audit_logger.py            # 审计日志记录器
│       │   ├── stop_loss_take_profit.py   # 止盈止损管理器
│       │   ├── execution_verifier.py      # 执行验证器
│       │   └── ...
│       ├── exchanges/             # 交易所接口
│       │   ├── okx.py             # OKX交易所
│       │   ├── binance.py         # Binance交易所
│       │   └── exchange_base.py   # 交易所基类
│       ├── notification/          # 通知模块
│       │   └── telegram_bot.py    # Telegram机器人
│       ├── data/                  # 数据模块
│       ├── strategies/            # 策略模块
│       ├── skills/                # 技能模块
│       ├── risk/                  # 风险管理
│       ├── api/                   # API服务
│       └── monitoring/            # 监控模块
│           └── enhanced_monitoring.py     # 增强监控系统
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
│       ├── daily/                 # 每日记忆（保留30天）
│       ├── summary/               # 每日总结（保留30天）
│       ├── weekly/                # 周度汇总（保留12周）
│       ├── monthly/               # 月度汇总（永久）
│       ├── experience/            # 经验教训（永久）
│       ├── trades/                # 交易记录
│       └── sessions/              # 会话记录
├── logs/                          # 日志文件
│   └── audit/                     # 审计日志
├── docker-compose.yml             # Docker编排
├── Dockerfile                     # Docker镜像
├── requirements.txt               # Python依赖
├── ARCHITECTURE.md                # 本文档
└── .env                          # 环境变量
```

### 3.3 启动与配置加载（工作流对齐）

- **系统启动入口**：`src/main.py`
  - 初始化 `ConfigManager()`（自动探测并合并 `data/config`、`config`、`/app/data/config`、`/app/config`）。
  - 初始化 `MainController` 与 `APIServer`。
  - 运行阶段调用 `MainController.start_system()`（依赖顺序 + 状态管理 + 关键连接验证）。

- **开发启动建议**：
  - 使用 `make run`（内部调用 `./start_production.sh simulation`）或直接 `python3 src/main.py`。

- **前端静态资源交付**：
  - 后端会在启动时尝试挂载 `frontend/dist`（兼容 `/app/frontend/dist` 与 `/app/src/frontend/dist` 两种布局）。

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

### 4.4 智能记忆系统 V2.0 (SmartMemoryManager)

**文件**: `src/modules/core/ai_memory.py`

**职责**:
- 固定最小加载 + 按需动态加载
- 意图识别关键词匹配
- 30天每日记忆 + 自动总结
- 经验教训永久保留

**记忆加载策略**:
| 层级 | 内容 | 加载时机 | 字符限制 |
|------|------|----------|----------|
| 核心身份 | SOUL.md + IDENTITY.md | 每次对话 | 300字 |
| 用户期望 | USER.md | 每次对话 | 100字 |
| 对话上下文 | 最近3-5条对话 | 每次对话 | 动态 |
| 交易相关 | TRADING.md + 今日交易 | 交易关键词触发 | 800字 |
| 市场分析 | 今日市场观察 | 市场关键词触发 | 500字 |
| 风险相关 | 近期风险事件 | 风险关键词触发 | 500字 |
| 经验教训 | lessons_learned.md | 学习关键词触发 | 400字 |

**意图关键词**:
| 意图 | 关键词示例 |
|------|-----------|
| 交易 | 开仓、平仓、止损、止盈、仓位、做多、做空 |
| 市场 | 行情、走势、趋势、分析、支撑、阻力 |
| 风险 | 风险、亏损、预警、强平、爆仓 |
| 学习 | 为什么、原因、教训、改进、总结 |
| 指令 | 你要、我要求、我希望、记住 |

---

## 5. 新增模块 (V2.1)

### 5.1 动态仓位管理器 (DynamicPositionManager)

**文件**: `src/modules/core/dynamic_position_manager.py`

**功能**:
- 基于市场波动率动态调整仓位
- 基于账户风险状态调整仓位
- 基于策略表现动态调整仓位
- 支持多品种仓位分散

**配置**:
```python
DynamicPositionConfig:
    base_position_ratio: 0.1      # 基础仓位比例
    max_position_ratio: 0.3       # 单品种最大仓位
    max_total_position_ratio: 0.8 # 总仓位上限
```

### 5.2 品种相关性监控器 (CorrelationMonitor)

**文件**: `src/modules/core/correlation_monitor.py`

**功能**:
- 实时计算品种间相关性
- 检测相关性变化
- 预警过度集中风险
- 提供分散化建议和得分

**配置**:
```python
CorrelationMonitorConfig:
    correlation_threshold_high: 0.7  # 高相关性阈值
    lookback_periods: 30             # 回看周期
```

### 5.3 策略热加载器 (StrategyHotLoader)

**文件**: `src/modules/core/strategy_hot_loader.py`

**功能**:
- 无需重启即可更新策略逻辑
- 策略版本管理
- 策略回滚支持
- 自动备份和恢复

### 5.4 审计日志记录器 (AuditLogger)

**文件**: `src/modules/core/audit_logger.py`

**功能**:
- 完整的操作日志记录
- 敏感操作审计
- 日志查询和分析
- 合规性报告生成

**日志类型**:
| 事件类型 | 描述 |
|----------|------|
| TRADE_OPEN | 开仓 |
| TRADE_CLOSE | 平仓 |
| POSITION_UPDATE | 持仓更新 |
| RISK_ALERT | 风险预警 |
| STRATEGY_LOAD | 策略加载 |
| SYSTEM_ACTION | 系统操作 |

### 5.5 止盈止损管理器 (StopLossTakeProfitManager)

**文件**: `src/modules/core/stop_loss_take_profit.py`

**功能**:
- 固定止盈止损
- 移动止盈止损（追踪止损）
- 分批止盈
- 保本止损
- 时间止损
- ATR动态止损

**配置**:
```python
StopLossTakeProfitConfig:
    default_stop_loss_percent: 0.03   # 默认止损3%
    default_take_profit_percent: 0.06  # 默认止盈6%
    enable_trailing_stop: True         # 启用移动止损
    trailing_stop_offset: 0.02         # 移动止损偏移2%
    enable_breakeven: True             # 启用保本止损
    breakeven_trigger: 0.02            # 2%盈利触发保本
```

### 5.6 执行验证器 (ExecutionVerifier)

**文件**: `src/modules/core/execution_verifier.py`

**功能**:
- 命令解析和分类
- 执行状态追踪
- 结果验证和反馈
- 审计日志记录
- 执行状态查询

**命令类型**:
| 类型 | 描述 |
|------|------|
| OPEN_POSITION | 开仓 |
| CLOSE_POSITION | 平仓 |
| SET_STOP_LOSS | 设置止损 |
| SET_TAKE_PROFIT | 设置止盈 |
| QUERY_POSITION | 查询持仓 |
| QUERY_BALANCE | 查询余额 |
| ANALYZE_MARKET | 分析市场 |

**执行状态**:
| 状态 | 描述 |
|------|------|
| PENDING | 待执行 |
| EXECUTING | 执行中 |
| SUCCESS | 成功 |
| FAILED | 失败 |
| TIMEOUT | 超时 |

### 5.7 增强监控系统 (EnhancedMonitoringSystem)

**文件**: `src/modules/monitoring/enhanced_monitoring.py`

**功能**:
- 实时监控关键指标
- 多渠道报警（Telegram、邮件、Webhook）
- 报警分级和聚合
- 自动关联审计日志

---

## 6. 数据流

### 6.1 交易决策流程

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
│  智能记忆加载   │
│ SmartMemory     │
│ (按需动态加载)  │
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
│  动态仓位计算   │
│ PositionManager │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  相关性检查     │
│ CorrelationMon  │
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
│  执行验证器     │
│ ExecVerifier    │
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
│  止盈止损设置   │
│ StopLossManager │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  审计日志记录   │
│ AuditLogger     │
└─────────────────┘
```

### 6.2 记忆加载流程

```
用户输入
    │
    ▼
┌─────────────────┐
│ 意图识别        │
│ IntentAnalysis  │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌───────┐
│固定加载│ │动态加载│
│核心身份│ │按意图 │
└───┬───┘ └───┬───┘
    │         │
    └────┬────┘
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

## 7. 部署架构

### 7.1 Docker容器化部署

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

### 7.2 网络配置

- **代理**: Docker容器通过 `host.docker.internal:7890` 访问宿主机代理
- **Redis**: 容器内部通信
- **API**: 端口8000对外暴露

---

## 8. 配置说明

### 8.1 环境变量 (.env)

推荐规则（配置收敛后）：
- 推荐：`OPENCLAW__section__key=value`（支持多级嵌套）
- 兼容：`TRADING_SECTION_KEY=value`（已弃用，后续将移除）

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

### 8.2 系统配置 (data/config/default.yml)

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

# 止盈止损配置
stop_loss:
  default_stop_loss_percent: 0.03
  default_take_profit_percent: 0.06
  enable_trailing_stop: true
  trailing_stop_offset: 0.02

# 记忆系统配置
memory:
  daily_retention_days: 30
  weekly_retention_weeks: 12
  enable_auto_summary: true
  summary_time: "23:55"
```

---

## 9. API接口

### 9.1 REST API

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/v1/status` | GET | 系统状态 |
| `/api/v1/positions` | GET | 当前持仓 |
| `/api/v1/orders` | GET | 订单历史 |
| `/api/v1/account` | GET | 账户信息 |
| `/api/v1/executions` | GET | 执行记录 |
| `/api/v1/memory/stats` | GET | 记忆统计 |

### 9.2 Telegram Bot命令

| 命令 | 描述 |
|------|------|
| `/start` | 启动系统 |
| `/stop` | 停止系统 |
| `/status` | 查看状态 |
| `/positions` | 查看持仓 |
| `/balance` | 查看余额 |
| `/executions` | 查看执行记录 |

---

## 10. 安全机制

### 10.1 API密钥管理

- 所有API密钥存储在 `.env` 文件中
- 不提交到版本控制
- 容器运行时通过环境变量注入

### 10.2 风险控制

- 单笔交易最大亏损: 2%
- 日内最大亏损: 5%
- 最大回撤: 15%
- 黑名单机制: 禁止交易指定币种（当前已清空）

### 10.3 自动保护

- CRITICAL风险自动平仓
- 异常检测自动告警
- 系统故障自动恢复
- 止盈止损自动执行

### 10.4 审计追踪

- 所有交易操作记录审计日志
- 执行结果可验证、可追溯
- 日志保留90天

---

## 11. 监控告警

### 11.1 日志系统

- **应用日志**: `logs/app.log`
- **交易日志**: `logs/trading.log`
- **错误日志**: `logs/error.log`
- **审计日志**: `logs/audit/`

### 11.2 Telegram通知

- 交易执行通知
- 风险预警通知
- 系统状态通知
- 错误告警通知
- 止盈止损触发通知

### 11.3 健康检查

```bash
# 检查容器状态
docker ps | grep openclaw

# 检查应用健康
curl http://localhost:8000/health

# 查看实时日志
docker logs -f openclaw-trading

# 查看执行记录
curl http://localhost:8000/api/v1/executions
```

---

## 附录

### A. 版本更新日志

**V2.1.0 (2026-04-05)**
- 新增动态仓位管理器
- 新增品种相关性监控器
- 新增策略热加载器
- 新增审计日志记录器
- 新增止盈止损管理器
- 新增执行验证器
- 新增增强监控系统
- 重构智能记忆系统V2.0（按需动态加载）
- 优化记忆加载策略（固定最小+按需动态）
- 移除ETH/USDT黑名单

**V2.0.0**
- 初始版本

### B. 常见问题

**Q: 如何更新API密钥？**
A: 编辑 `.env` 文件，然后重启容器: `docker-compose restart`

**Q: 如何查看交易日志？**
A: `docker logs openclaw-trading | grep -i trade`

**Q: 如何手动平仓？**
A: 通过Telegram发送平仓指令，或调用API接口

**Q: 如何查询执行状态？**
A: 发送"最近执行了什么"或调用 `/api/v1/executions`

**Q: 如何验证止损是否设置？**
A: 发送"BTC的止损设置了吗"或调用 `verify_stop_loss_set()`

### C. 维护指南

1. **日常检查**: 查看Telegram通知和日志
2. **周度检查**: 检查账户余额和持仓
3. **月度检查**: 备份数据和配置
4. **定期清理**: 30天前的每日记忆自动清理

### D. 相关文档

- [快速开始指南](./快速开始指南.md)
- [AI记忆文件](./workspace/)
- [配置参考](./data/config/)

---

**文档维护者**: OpenClaw Trading System Team  
**最后审核**: 2026-04-05
