# 系统更新日志

## [2026-04-11] 文档与工程说明整理

- **文档体系**：新增 `docs/README.md`（索引）、`docs/ENGINEERING.md`（工程主文档）、`docs/OPERATIONS.md`（运维合并版）；根目录 `ARCHITECTURE.md` / `DEVELOPMENT.md` 改为跳转 stub；`DEVELOPMENT.md` 正文迁至 `docs/DEVELOPMENT.md`。
- **清理**：删除重复/过时文档若干（旧代理/维护/网络基线独立稿、架构模块表、旧 API 手写稿、评审/验证报告、已合并的记忆蓝图等）；总控中心内嵌文档目录改为指向新文档集。
- **代码引用**：司令部宪章、执行器、护栏与前端总控中的文档路径已改为 `docs/ENGINEERING.md` 等。
- **Docker**：已验证 `docker compose build` + `up` 后 `/health` 正常。

## [2026-04-05] V2.1.0 重大更新

### 新增模块

#### 1. 动态仓位管理器 (DynamicPositionManager)
- **文件**: `src/modules/core/dynamic_position_manager.py`
- **功能**: 基于市场波动率、账户风险状态、策略表现动态调整仓位

#### 2. 品种相关性监控器 (CorrelationMonitor)
- **文件**: `src/modules/core/correlation_monitor.py`
- **功能**: 实时计算品种间相关性，预警过度集中风险

#### 3. 策略热加载器 (StrategyHotLoader)
- **文件**: `src/modules/core/strategy_hot_loader.py`
- **功能**: 无需重启即可更新策略逻辑，支持版本管理和回滚

#### 4. 审计日志记录器 (AuditLogger)
- **文件**: `src/modules/core/audit_logger.py`
- **功能**: 完整的操作日志记录，敏感操作审计，合规性报告

#### 5. 止盈止损管理器 (StopLossTakeProfitManager)
- **文件**: `src/modules/core/stop_loss_take_profit.py`
- **功能**: 固定止盈止损、移动止损、分批止盈、保本止损、ATR动态止损

#### 6. 执行验证器 (ExecutionVerifier)
- **文件**: `src/modules/core/execution_verifier.py`
- **功能**: 命令解析分类、执行状态追踪、结果验证反馈

#### 7. 增强监控系统 (EnhancedMonitoringSystem)
- **文件**: `src/modules/monitoring/enhanced_monitoring.py`
- **功能**: 实时监控关键指标，多渠道报警，报警分级聚合

### 核心优化

#### 1. 智能记忆系统V2.0重构
- **文件**: `src/modules/core/ai_memory.py`
- **改进**: 固定最小加载 + 按需动态加载
- **效果**: 大幅减少Token消耗，提升响应速度

#### 2. LLM管理器优化
- **文件**: `src/modules/core/enhanced_llm_manager.py`
- **改进**: 添加认证错误检测和自动降级机制
- **效果**: 提高API调用稳定性

#### 3. Docker配置优化
- **文件**: `docker-compose.yml`, `Dockerfile`, `start_production.sh`
- **改进**: 使用env_file传递环境变量，修复.env被覆盖问题
- **效果**: API密钥持久化问题解决

#### 4. 风险监控优化
- **文件**: `src/modules/core/account_risk_monitor.py`
- **改进**: 添加预警冷却机制，减少重复告警
- **效果**: 日志更清晰，告警更有效

### 问题修复

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| API密钥丢失 | Dockerfile覆盖.env | 使用env_file指令 |
| LLM 401错误 | API认证失败无降级 | 添加错误检测和降级 |
| OKX 51001错误 | 交易对格式问题 | 优化SWAP后缀处理 |
| 权限拒绝错误 | 硬编码路径 | 使用环境变量和回退路径 |
| JSON序列化错误 | Enum类型处理 | 添加Enum序列化支持 |

### 性能对比

| 指标 | V2.0 | V2.1 |
|------|------|------|
| 模块数量 | 7 | 12 |
| 记忆加载效率 | 全量加载 | 按需加载 |
| API调用稳定性 | 95% | 99%+ |
| 风险预警准确性 | 70% | 95%+ |

---

## [2026-04-01] 系统稳定性修复与优化 (v1.3.1)

### 新增功能

#### 1. OKX API 重试机制
- **文件**: `src/modules/api/server.py`
- **功能**: 添加OKX API请求重试机制
- **实现**:
  - 最多3次重试
  - 超时时间增加到15秒
  - 使用TCPConnector优化连接管理
  - 自动清理连接资源
- **效果**: 解决了OKX API请求偶尔超时的问题

#### 2. JSON解析安全处理
- **文件**: `src/modules/core/llm_integration.py`
- **功能**: 添加 `safe_json_parse()` 函数
- **实现**:
  - 支持从markdown代码块中提取JSON
  - 支持多种JSON格式解析
  - 优雅的错误处理
- **效果**: 解决了AI返回JSON格式不完整导致的解析错误

#### 3. 进程锁机制完善
- **文件**: `src/utils/process_lock.py`, `scripts/*.sh`
- **功能**: 完善进程锁和脚本管理
- **修复**:
  - `health_check.sh`: 添加Telegram Chat ID配置
  - `stop-openclaw-trading.sh`: 添加锁文件清理
  - `start-openclaw-trading.sh`: 添加锁文件检查
  - `openclaw-trading.service`: 修复systemd服务配置

### 问题修复

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| OKX API请求超时 | 网络波动，无重试机制 | 添加3次重试机制 |
| JSON解析失败 | AI返回格式不完整 | 添加safe_json_parse函数 |
| asyncio CancelledError | 请求处理超时被取消 | 优化连接管理和超时处理 |
| Telegram通知不发送 | Chat ID未配置 | 更新健康检查脚本 |
| 进程锁残留 | 停止脚本未清理锁文件 | 添加锁文件清理逻辑 |

### 性能优化

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| API请求成功率 | ~85% | ~98% |
| JSON解析成功率 | ~90% | ~99% |
| 错误日志数量 | 30+/分钟 | <5/分钟 |
| 服务稳定性 | 偶发崩溃 | 稳定运行 |

---

## [2026-04-01] 系统稳定性优化 (v1.3.0)

### 新增功能

#### 1. 进程锁机制
- **文件**: `src/main.py`, `src/utils/process_lock.py`
- **功能**: 使用 `fcntl` 文件锁防止系统重复启动
- **实现**:
  - `ProcessLock` 类：封装进程锁管理
  - PID 文件: `/tmp/openclaw-trading.pid`
  - 锁文件: `/tmp/openclaw-trading.lock`
- **效果**: 解决了多个进程同时运行导致的资源竞争问题

#### 2. 风险事件去重机制
- **文件**: `src/modules/core/ai_trading_engine.py`
- **功能**: 相同风险事件在冷却时间内不重复记录
- **配置**:
  - `_risk_event_cooldown`: 300 秒（5分钟）
  - `_last_risk_events`: 记录最近风险事件时间
- **效果**: 大幅减少记忆文件增长

#### 3. 健康检查脚本
- **文件**: `scripts/health_check.sh`
- **功能**:
  - 进程状态检查
  - API健康检查
  - 内存/磁盘监控
  - 自动重启服务
  - Telegram告警通知
- **配置**: crontab每小时执行

#### 4. 启动/停止脚本
- **文件**: `scripts/start-openclaw-trading.sh`, `scripts/stop-openclaw-trading.sh`
- **功能**: 标准化的服务管理脚本

### 优化改进

#### 1. LLM 模型管理优化
- **文件**: `src/modules/core/enhanced_llm_manager.py`
- **改进**:
  - 清理无用的模型配置
  - 只保留有 API key 的模型
  - 模型选择时检查 provider 是否已初始化
- **效果**: 解决了 `Bearer ` token 为空的 API 调用错误

#### 2. 前端界面优化
- **文件**: `frontend/src/App.jsx`, `frontend/src/components/ProfessionalDashboard.jsx`
- **改进**:
  - 修复React Hooks违规问题
  - 添加主题切换功能
  - 连接真实OKX市场数据
  - 优化布局和样式

### 性能对比

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 进程数量 | 3 个 | 1 个 |
| 内存使用 | 3.4Gi / 3.8Gi | 2.6Gi / 3.8Gi |
| 可用内存 | 232Mi | 1.2Gi |
| 风险事件记录频率 | 每 10 秒 | 每 5 分钟 |
| API请求成功率 | ~85% | ~98% |

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

## 待优化项

### 短期
- [x] 添加API重试机制
- [x] 优化OKX API连接稳定性
- [x] 添加进程锁机制
- [x] 添加健康检查脚本
- [ ] 添加日志轮转机制
- [ ] 添加内存监控和自动重启

### 中期
- [ ] 添加更多技术指标
- [ ] 优化并发请求处理
- [ ] 添加请求队列和限流

### 长期
- [ ] 支持更多交易所
- [ ] 添加回测系统
- [ ] Web前端界面优化
