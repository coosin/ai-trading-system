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

## 文档导航

| 文档 | 描述 |
|------|------|
| [**系统架构文档**](./ARCHITECTURE.md) | 详细的系统架构、模块说明、配置指南 |
| [**快速开始指南**](./快速开始指南.md) | 环境搭建和开发流程 |
| [**AI记忆文件**](./workspace/) | AI核心信念、身份定义、交易知识 |
| [**记忆库使用与维护指南**](./docs/memory/MEMORY_LIBRARY_GUIDE.md) | MemoryGateway 单一真源：结构、写入/召回、总结晋升、清理与扩展 |

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

### 代理配置（可选，默认不启用）

为避免容器被宿主机 `HTTP_PROXY/HTTPS_PROXY` 等环境变量“误伤”导致网络不稳定，容器内默认不启用系统代理变量。  
如需代理，请显式配置：

```bash
# 仅在确实需要代理时设置
OPENCLAW_HTTP_PROXY=http://host.docker.internal:7890
OPENCLAW_HTTPS_PROXY=http://host.docker.internal:7890
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

- ✅ AI决策引擎 - 运行正常
- ✅ OKX交易所接口 - 已连接
- ✅ 风险控制系统 - 已启用
- ✅ Telegram通知 - 已配置
- ✅ 记忆系统 - 已初始化
- ✅ 真实回测指标 - 已接入（收益/回撤/夏普/胜率）
- ✅ 参数自动优化 - 已接入（基于行情网格搜索）
- ✅ 多源数据融合 - 初始化稳定（修复异步注册错误）

---

## 2026-04-07 当日更新

- ✅ **S1 执行主干稳定化**：`ai_core` 作为单一写入所有者（SWO），`ExecutionGateway` 作为统一下单出口，`/api/v1/s1/verify` 可直接校验执行链路。
- ✅ **止盈止损跟踪对账增强**：启动同步时会将本地 `active` 跟踪单与交易所实时持仓对账，自动清理陈旧跟踪单（返回 `stale_cancelled`）。
- ✅ **系统状态口径修正**：状态报告兼容 `data_fusion`/`multi_source_fusion` 与 `third_party_data`/`third_party_integrator`，避免模块“误报离线”。
- ✅ **健康检查告警降噪**：将“缺少人工请求”的工具技能与真实故障分离；仅在关键失败达到阈值时标记 `critical`，其余为 `warning`。
- ✅ **风险日志语义修正**：风险监控日志改为“当前未发现高风险持仓”，不再误导为“黑名单风险”。
- ✅ **外部数据源退化可观测**：新增数据源健康状态与退化标记，状态输出可展示退化源列表，便于排障。
- ✅ **开仓时机与仓位跟踪联动优化**：`ai_core` 开仓成功后，自动将自适应门控（分组/时段阈值、实时盘口）映射为该仓位的 SL/TP 跟踪配置，确保“开仓判断”与“后续风控执行”一致。
- ✅ **止盈止损实时动态调整**：`StopLossTakeProfitManager` 增加基于实时订单簿的动态调整（价差/深度失衡），在浮盈阶段可自动收紧止损或小幅延展止盈，减少震荡回吐并跟随趋势延续。
- ✅ **策略开发与执行流程文档化**：将“门控阈值 -> 开仓 -> 跟踪 -> 动态SL/TP -> 触发平仓”链路纳入统一执行说明，便于后续策略迭代直接复用。
- ✅ **巡检与日报自动化**：新增 `continuous_system_probe.py` 与 `system_probe_daily_summary.py`，支持关键接口巡检、峰值统计与中文日报输出。
- ✅ **Telegram 巡检推送闭环**：新增 `probe_report_to_tg.py`，支持“一条命令”完成巡检 + 报告生成 + TG 推送。
- ✅ **止盈止损统计接口**：新增 `/api/v1/modules/stop-loss/stats`，供巡检、可视化面板与告警系统统一读取。
- ✅ **代理订阅更新运维脚本**：新增 `update_clash_subscriptions.sh`，支持订阅更新后自动 reload Clash，便于定时任务托管。
- ✅ **多类型策略研发放宽**：DSL 与研究候选扩展为趋势/波动/剥头皮/抓针（`volatility_breakout`、`scalp_reversion`、`pinbar_reversal`），支持并行筛选高分策略。
- ✅ **研究发布类型修复**：修复研究发布 `strategy_type` 映射，避免无效类型导致策略无法正确入池。
- ✅ **策略池治理上线**：低分淘汰 + 总量上限（当前 30）+ 每小时清理窗口，防止策略无限累积。
- ✅ **每日固定优化 + 回撤优化**：全策略每日执行参数与回撤联合优化，持续写入 `metadata.daily_optimization`。
- ✅ **回撤任务资源保护**：每日优化改为“分批 + 时间预算 + 让出事件循环”，降低 CPU 峰值与主链路抖动。
- ✅ **前端对接接口预留**：
  - `GET /api/v1/modules/strategy/optimization-status`（查询策略池与每日优化状态）
  - `POST /api/v1/modules/strategy/optimization-config`（热更新批处理/周期/上限参数，无需重启）

---

## 2026-04-08/09 最新状态（交付前最终审查）

- ✅ **重启接管**：系统启动后会强制同步 **钱包余额 + 持仓**，并接管 SL/TP 跟踪与仓位管理建议输出。
- ✅ **司令部快照增强**：`GET /api/v1/modules/commander/snapshot?mode=fast` 将返回：
  - `account.balance / account.positions / account.synced_at`
  - `risk.sltp` 与 `risk.position_recommendations`
- ✅ **OKX 稳定性增强**：修复 GET 签名未包含 query string、以及 instId/`-SWAP-SWAP` 混用导致的错误噪音。
- ✅ **代理策略调整**：默认不启用系统代理变量；使用 `OPENCLAW_HTTP_PROXY/OPENCLAW_HTTPS_PROXY` 显式开启，降低不稳定因素。

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
