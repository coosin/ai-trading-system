# 系统更新日志

## [2026-04-01] 系统稳定性优化

### 新增功能

#### 1. 进程锁机制
- **文件**: `src/main.py`
- **功能**: 使用 `fcntl` 文件锁防止系统重复启动
- **实现**:
  - `acquire_lock()`: 获取进程锁，防止重复启动
  - `release_lock()`: 释放进程锁
  - PID 文件: `trading_system.pid`
- **效果**: 解决了多个进程同时运行导致的资源竞争问题

#### 2. 风险事件去重机制
- **文件**: `src/modules/core/ai_trading_engine.py`
- **功能**: 相同风险事件在冷却时间内不重复记录
- **配置**:
  - `_risk_event_cooldown`: 300 秒（5分钟）
  - `_last_risk_events`: 记录最近风险事件时间
- **效果**: 大幅减少记忆文件增长，从每 10 秒记录一次改为每 5 分钟记录一次

### 优化改进

#### 1. LLM 模型管理优化
- **文件**: `src/modules/core/enhanced_llm_manager.py`
- **改进**:
  - 清理无用的模型配置（gpt-4, deepseek, qwen 等）
  - 只保留有 API key 的模型
  - 模型选择时检查 provider 是否已初始化
- **效果**: 解决了 `Bearer ` token 为空的 API 调用错误

#### 2. 配置文件优化
- **文件**: `data/config/default.yml`
- **改进**: 精简 LLM 模型配置，移除无用模型

#### 3. 记忆文件清理
- **文件**: `data/memory/enhanced_memory.json`
- **清理**: 从 500 条记录减少到 429 条，移除重复风险事件

### 问题修复

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 重复进程运行 | 无进程锁机制 | 添加 fcntl 文件锁 |
| LLM API 调用失败 | 选择了无 API key 的模型 | 优化模型选择逻辑 |
| 风险事件过多 | 每 10 秒记录一次 | 添加去重和冷却机制 |
| 记忆文件过大 | 累积大量重复记录 | 清理旧数据 |

### 性能对比

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 进程数量 | 3 个 | 1 个 |
| 内存使用 | 3.4Gi / 3.8Gi | 2.6Gi / 3.8Gi |
| 可用内存 | 232Mi | 1.2Gi |
| 风险事件记录频率 | 每 10 秒 | 每 5 分钟 |
| 长期记忆数量 | 500+ 条 | 429 条 |

---

## [2026-04-01] Telegram 机器人集成

### 新增功能

#### 1. Telegram Bot 集成
- **文件**: `src/modules/notification/telegram_bot.py`
- **功能**:
  - 自然语言交互
  - 交易信号推送
  - 风险预警通知
  - 账户状态查询
- **配置**: `telegram.bot_token` in `default.yml`

#### 2. 代理支持
- **功能**: 支持 HTTP 代理连接 Telegram API
- **配置**: `telegram.proxy`

---

## [2026-04-01] AI 记忆系统增强

### 新增功能

#### 1. 增强记忆管理器
- **文件**: `src/modules/core/enhanced_memory_manager.py`
- **功能**:
  - 智能识别重要信息
  - 记忆分类和优先级
  - 交易记录存储
  - 策略优化记录
  - 风险事件记录

#### 2. 记忆类型
- `user_preference`: 用户偏好
- `trading_record`: 交易记录
- `strategy_optimization`: 策略优化
- `risk_event`: 风险事件
- `market_insight`: 市场洞察
- `system_instruction`: 系统指令

---

## [2026-04-01] 全智能交易引擎

### 新增功能

#### 1. AI 交易引擎
- **文件**: `src/modules/core/ai_trading_engine.py`
- **功能**:
  - 自主数据采集
  - AI 市场分析
  - 智能决策生成
  - 自动订单执行
  - 实时监控和风控
  - 策略自我优化

#### 2. 账户风险监控
- **文件**: `src/modules/core/account_risk_monitor.py`
- **功能**:
  - 实时账户权益监控
  - 持仓风险预警
  - 强平价格计算
  - 风险预警通知

#### 3. 策略优化器
- **文件**: `src/modules/core/strategy_optimizer.py`
- **功能**:
  - 策略自动优化
  - 新策略发现
  - 参数调优

---

## [2026-04-01] 技术指标系统

### 新增功能

#### 1. 技术指标计算器
- **文件**: `src/modules/data/technical_indicators.py`
- **功能**:
  - 移动平均线 (MA, EMA)
  - RSI 相对强弱指数
  - MACD 指标
  - 布林带
  - KDJ 指标
  - 成交量指标

#### 2. 历史数据存储
- **文件**: `src/modules/core/historical_data_storage.py`
- **功能**:
  - 多时间框架 K 线数据存储
  - 技术指标历史数据
  - 数据压缩和清理

---

## 待优化项

### 短期
- [ ] 添加日志轮转机制
- [ ] 添加内存监控和自动重启
- [ ] 优化记忆文件自动清理（超过 7 天）

### 中期
- [ ] 添加 API 重试机制
- [ ] 优化 OKX API 连接稳定性
- [ ] 添加更多技术指标

### 长期
- [ ] 支持更多交易所
- [ ] 添加回测系统
- [ ] 添加 Web 前端界面
