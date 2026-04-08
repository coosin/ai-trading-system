# OpenClaw Trading - 开发文档

## 目录

- [开发环境设置](#开发环境设置)
- [项目结构](#项目结构)
- [核心模块说明](#核心模块说明)
- [开发规范](#开发规范)
- [测试指南](#测试指南)
- [调试技巧](#调试技巧)
- [性能优化](#性能优化)
- [常见问题](#常见问题)

---

## 开发环境设置

### 系统要求

- Python 3.8+
- pip 21.0+
- Git
- 虚拟环境 (推荐)

### 环境搭建

```bash
# 1. 克隆项目
git clone https://github.com/your-username/openclaw-trading.git
cd openclaw-trading

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt
pip install -r requirements-dev.txt  # 开发依赖

# 4. 配置环境变量
cp .env.example .env
nano .env  # 填写必需的API密钥

# 5. 初始化数据库
python scripts/init_db.py

# 6. 运行测试
pytest tests/

# 7. 启动开发服务器
python start.py
```

### IDE配置

推荐使用 VSCode 或 PyCharm

**VSCode扩展:**
- Python
- Pylance
- Python Docstring Generator
- GitLens

**推荐设置:**
```json
{
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true
}
```

---

## 项目结构

```
openclaw-trading/
├── config/                    # 配置文件
│   ├── config.yaml           # 主配置文件
│   └── logging.yaml          # 日志配置
│
├── src/                      # 源代码
│   ├── modules/              # 功能模块
│   │   ├── core/            # 核心模块
│   │   │   ├── ai_trading_engine.py      # AI交易引擎
│   │   │   ├── ai_learning_engine.py     # AI学习引擎
│   │   │   ├── ai_memory.py              # AI记忆管理
│   │   │   ├── enhanced_llm_manager.py   # LLM管理器
│   │   │   ├── llm_integration.py        # LLM集成
│   │   │   ├── main_controller.py        # 主控制器
│   │   │   ├── config_manager.py         # 配置管理
│   │   │   ├── event_system.py           # 事件系统
│   │   │   └── risk_manager.py           # 风险管理
│   │   │
│   │   ├── data/            # 数据模块
│   │   │   ├── data_pipeline.py          # 数据管道
│   │   │   ├── historical_data_storage.py # 历史数据存储
│   │   │   └── multi_source_data_fusion.py # 多源数据融合
│   │   │
│   │   ├── strategies/       # 策略模块
│   │   │   ├── strategy_base.py          # 策略基类
│   │   │   ├── strategy_manager.py       # 策略管理器
│   │   │   └── strategy_optimizer.py     # 策略优化器
│   │   │
│   │   ├── exchanges/        # 交易所接口
│   │   │   ├── exchange_base.py          # 交易所基类
│   │   │   ├── okx.py                    # OKX交易所
│   │   │   └── binance.py                # Binance交易所
│   │   │
│   │   ├── monitoring/       # 监控模块
│   │   │   ├── trading_monitor.py        # 交易监控
│   │   │   └── account_risk_monitor.py   # 账户风险监控
│   │   │
│   │   ├── notification/     # 通知模块
│   │   │   ├── telegram_bot.py           # Telegram机器人
│   │   │   └── notification_manager.py   # 通知管理器
│   │   │
│   │   ├── api/              # API接口
│   │   │   ├── server.py                 # API服务器
│   │   │   └── routes/                   # API路由
│   │   │
│   │   └── intelligence/     # 智能模块
│   │       ├── natural_language_interface.py # 自然语言接口
│   │       └── anomaly_detection.py      # 异常检测
│   │
│   ├── utils/                # 工具函数
│   │   ├── env_config.py                 # 环境变量配置
│   │   ├── logger.py                     # 日志工具
│   │   └── helpers.py                    # 辅助函数
│   │
│   └── main.py               # 主入口
│
├── workspace/                # AI记忆文件
│   ├── SOUL.md              # 核心信念
│   ├── IDENTITY.md          # 身份定义
│   ├── USER.md              # 用户信息
│   ├── TRADING.md           # 交易知识库
│   └── INSTRUCTIONS.md      # 工作指令
│
├── data/                    # 数据存储
│   ├── historical/          # 历史数据
│   ├── memory/              # AI记忆数据
│   └── events.db            # 事件数据库
│
├── logs/                    # 日志文件
│   ├── trading.log          # 交易日志
│   ├── error.log            # 错误日志
│   └── system.log           # 系统日志
│
├── tests/                   # 测试文件
│   ├── unit/                # 单元测试
│   ├── integration/         # 集成测试
│   └── e2e/                 # 端到端测试
│
├── docs/                    # 文档
│   ├── ARCHITECTURE.md      # 架构文档
│   ├── DEPLOYMENT.md        # 部署文档
│   ├── API.md               # API文档
│   └── FAQ.md               # 常见问题
│
├── scripts/                 # 脚本工具
│   ├── init_db.py           # 初始化数据库
│   ├── backup.py            # 备份脚本
│   └── health_check.py      # 健康检查
│
├── .env.example             # 环境变量模板
├── requirements.txt         # 生产依赖
├── requirements-dev.txt     # 开发依赖
├── start.py                # 启动脚本
├── README.md               # 主文档
└── DEVELOPMENT.md          # 开发文档
```

---

## 核心模块说明

### 1. AI交易引擎 (ai_trading_engine.py)

**功能:**
- 完全自动化的交易流程
- AI驱动的市场分析
- 智能决策生成
- 自动订单执行

**关键方法:**
```python
async def _trading_loop(self) -> None:
    """主交易循环"""
    while self._running:
        for symbol in self.symbols:
            # 1. 数据采集
            market_data = await self._collect_market_data(symbol)
            
            # 2. AI分析
            context = await self._analyze_market(symbol, market_data)
            
            # 3. AI决策
            decision = await self._make_decision(symbol, context, position)
            
            # 4. 风险检查
            if await self._risk_check(decision):
                # 5. 执行交易
                await self._execute_decision(decision)
```

### 2. LLM管理器 (enhanced_llm_manager.py)

**功能:**
- 多模型支持和管理
- 动态模型切换
- 负载均衡和故障转移
- 使用统计和性能监控

**使用示例:**
```python
# 初始化
llm_manager = EnhancedLLMManager()
await llm_manager.initialize(config)

# 生成文本
response = await llm_manager.generate(
    prompt="分析BTC/USDT市场趋势",
    model_id="astron-code-latest",
    task_type=TaskType.MARKET_ANALYSIS
)
```

### 3. AI记忆管理 (ai_memory.py)

**功能:**
- 短期记忆: 对话上下文
- 长期记忆: 交易历史、用户偏好
- 文件化记忆: SOUL.md等
- 记忆检索和注入

**使用示例:**
```python
# 添加记忆
await memory_manager.add_long_term_memory(
    content="用户偏好保守策略",
    memory_type=MemoryType.USER_PREF,
    importance=0.8
)

# 检索记忆
memories = await memory_manager.retrieve_memory(
    query="交易策略",
    top_k=5
)
```

### 4. 风险管理 (risk_manager.py)

**功能:**
- 账户级风险控制
- 仓位级风险控制
- 实时风险监控
- 自动预警机制

**风险检查流程:**
```python
async def _risk_check(self, decision: AIDecision) -> bool:
    # 1. 检查最大持仓数
    if len(self.positions) >= self.max_positions:
        return False
    
    # 2. 检查仓位大小
    if decision.quantity > self.max_position_size:
        return False
    
    # 3. 检查风险敞口
    total_risk = self._calculate_total_risk()
    if total_risk > self.max_risk:
        return False
    
    return True
```

---

## 开发规范

### 代码风格

遵循 PEP 8 规范，使用以下工具:

```bash
# 代码格式化
black src/

# 代码检查
flake8 src/

# 类型检查
mypy src/
```

### 命名规范

- **模块名**: 小写下划线 `ai_trading_engine.py`
- **类名**: 大驼峰 `AITradingEngine`
- **函数名**: 小写下划线 `make_decision`
- **常量**: 大写下划线 `MAX_POSITIONS`
- **变量**: 小写下划线 `market_data`

### 文档字符串

使用Google风格文档字符串:

```python
def calculate_position_size(self, symbol: str, risk: float) -> float:
    """计算仓位大小
    
    Args:
        symbol: 交易对符号
        risk: 风险比例 (0-1)
    
    Returns:
        仓位大小
    
    Raises:
        ValueError: 如果risk不在0-1范围内
    
    Example:
        >>> size = calculate_position_size("BTC/USDT", 0.02)
        >>> print(size)
        0.001
    """
    pass
```

### 异步编程规范

- 所有IO操作使用async/await
- 使用asyncio.gather()并发执行
- 避免阻塞操作
- 正确处理异常和取消

```python
# 好的做法
async def fetch_data(self):
    try:
        async with asyncio.timeout(30):
            data = await self.api.get_data()
            return data
    except asyncio.TimeoutError:
        logger.error("请求超时")
        return None

# 不好的做法
async def fetch_data(self):
    data = await self.api.get_data()  # 没有超时处理
    return data
```

---

## 测试指南

### 测试结构

```
tests/
├── unit/                    # 单元测试
│   ├── test_ai_engine.py
│   ├── test_llm_manager.py
│   └── test_risk_manager.py
│
├── integration/             # 集成测试
│   ├── test_trading_flow.py
│   └── test_data_pipeline.py
│
└── e2e/                     # 端到端测试
    └── test_full_system.py
```

### 编写测试

```python
import pytest
from unittest.mock import Mock, AsyncMock, patch

@pytest.mark.asyncio
async def test_ai_decision():
    """测试AI决策生成"""
    # 准备
    engine = AITradingEngine()
    engine.llm_integration = Mock()
    engine.llm_integration.generate_trading_signal = AsyncMock(
        return_value={"signal": "buy", "confidence": 0.8}
    )
    
    # 执行
    context = MarketContext(
        symbol="BTC/USDT",
        price=50000,
        trend="bullish"
    )
    decision = await engine._make_decision("BTC/USDT", context, None)
    
    # 验证
    assert decision is not None
    assert decision.action == TradeAction.OPEN_LONG
    assert decision.confidence >= 0.65
```

### 运行测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/unit/test_ai_engine.py

# 运行并生成覆盖率报告
pytest --cov=src tests/

# 运行异步测试
pytest tests/ -v --asyncio-mode=auto
```

---

## 调试技巧

### 日志调试

```python
import logging

logger = logging.getLogger(__name__)

# 不同级别的日志
logger.debug("调试信息")
logger.info("一般信息")
logger.warning("警告信息")
logger.error("错误信息")
```

### 断点调试

在VSCode中设置断点，使用F5启动调试

**launch.json配置:**
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Current File",
      "type": "python",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal",
      "justMyCode": false
    }
  ]
}
```

### 性能分析

```python
import cProfile
import pstats

# 性能分析
profiler = cProfile.Profile()
profiler.enable()

# 运行代码
await main_function()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(10)
```

---

## 性能优化

### 异步优化

```python
# 并发执行
results = await asyncio.gather(
    fetch_data_1(),
    fetch_data_2(),
    fetch_data_3()
)

# 使用连接池
async with aiohttp.TCPConnector(limit=100) as connector:
    async with aiohttp.ClientSession(connector=connector) as session:
        # 使用session
        pass
```

### 缓存优化

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def calculate_indicator(klines_hash: str) -> Dict:
    """缓存技术指标计算结果"""
    return calculate(klines_hash)
```

### 数据库优化

- 使用索引
- 批量插入
- 连接池
- 查询优化

---

## 常见问题

### Q: 如何添加新的AI模型？

A: 在 `enhanced_llm_manager.py` 中添加新的Provider类:

```python
class NewAIProvider(BaseLLMProvider):
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        # 实现生成逻辑
        pass
```

### Q: 如何添加新的交易所？

A: 继承 `ExchangeBase` 类并实现所有方法:

```python
class NewExchange(ExchangeBase):
    async def get_market_data(self, symbol: str) -> MarketData:
        # 实现获取市场数据
        pass
```

### Q: 如何调试AI决策？

A: 启用详细日志并检查AI响应:

```python
logging.getLogger("src.modules.core.ai_trading_engine").setLevel(logging.DEBUG)
```

### Q: 如何优化性能？

A: 
1. 使用异步IO
2. 添加缓存
3. 优化数据库查询
4. 使用连接池

---

## 贡献代码

请参考 [贡献指南](CONTRIBUTING.md)

---

## 更新日志

请参考 [更新日志](docs/CHANGELOG.md)

---

## 2026-04-08 全量修复记录

本次修复覆盖 API、主控状态统计、记忆存储路径、数据库路径和 Telegram 连通性，目标是恢复生产可用性并消除关键告警。

### 已完成修复

- `src/modules/intelligence/natural_language_interface.py`
  - 增加宽松 JSON 解析（支持 ```json 包裹与前后缀文本）
  - 针对“最近执行/执行历史”增加直连执行查询路径，避免 `unknown` 误判
- `src/modules/api/server.py`
  - `/api/v1/ai/query` 增加解析失败回退，保证接口可用
- `src/modules/main_controller.py`
  - `get_system_status()` 增加模块统计回退逻辑，避免 `module_count=0/running_modules=0`
- `src/modules/core/database_manager.py`
  - 容器内优先使用 `/app/data/trading_system.db`，减少回退 `/tmp` 场景
- `src/modules/core/optimized_memory_system.py`
  - 重构存储目录可写探测，容器内优先 `/app/data/memory`、次选 `/app/workspace/memory`
- `src/modules/core/ai_memory.py`
  - 增强可写探测，统一容器目录优先级，降低权限抖动导致的降级
- `src/modules/core/llm_integration.py`
  - 兼容 `MemoryGateway` 与旧记忆接口，消除方法缺失告警
- `src/modules/notification/telegram_bot.py`
  - 连接初始化增加“代理失败后直连”回退
  - 未配置 token 时直接跳过，避免无意义报错

### 回归结果

- `GET /api/v1/status`：模块统计正常（`module_count=29`，`running_modules=29`）
- `POST /api/v1/ai/query`：查询可正常返回执行记录
- `GET /api/v1/s1/verify`：`all_passed=true`
- Telegram：可连接并返回机器人身份（`getMe` 通过）
- 最近启动日志中已不再出现：
  - `无法解析命令执行结果`
  - `module_count=0/running_modules=0`
  - `权限不足，使用备用路径: /tmp/openclaw_*`

### 运维建议

- 使用 Docker Compose v2：
  - 启动：`docker compose up -d`
  - 重建：`docker compose up -d --build`
  - 日志：`docker compose logs -f trading-system`
- 避免覆盖 `.env` 中真实密钥，开发脚本应只在 `.env` 不存在时初始化模板。

---

## 2026-04-08 阶段优化进度快照（总控闭环）

本阶段目标：先打通“策略研究 -> 优化 -> 生产审计 -> 交易反馈再优化”的前后端闭环，再进入数据源模块专项优化。

### 后端链路优化进度

- 研究任务异步化：
  - `POST /api/v1/modules/strategy/research-run` 改为异步任务提交，返回 `job_id`
  - 新增 `GET /api/v1/modules/strategy/research-jobs` 与 `GET /api/v1/modules/strategy/research-jobs/{job_id}`
- 优化与反馈接口：
  - 新增 `POST /api/v1/modules/strategy/optimize-now`（手动触发每日优化）
  - 新增 `POST /api/v1/modules/strategy/trade-feedback`（交易结果回灌触发自适应参数优化）
- 生产闭环可观测性：
  - 新增 `GET /api/v1/modules/execution/production-audit`
  - 风险侧动态 SL/TP（含波动、趋势、点差、深度不平衡）已纳入调整逻辑

### 前端总控优化进度

- `frontend/src/services/api.js` 已补齐模块接口封装：
  - `getStrategyResearchJobs`
  - `getStrategyResearchJob`
  - `triggerStrategyOptimizeNow`
  - `submitStrategyTradeFeedback`
  - `getExecutionProductionAudit`
  - `getStrategyOptimizationConfig`
- `frontend/src/modules/control-hub/ControlHubModule.jsx` 已补齐控制面板能力：
  - 研究任务提交后按 `job_id` 轮询状态
  - 手动触发每日优化批次
  - 手动提交交易反馈（含 `force_optimize`）
  - 展示研究任务队列与生产执行审计 JSON
  - 展示部署分层统计（paper/shadow/small/full）

### 当前缺口与下一阶段

- 当前缺口：数据源模块尚未完成“专项优化 + 深度融合门控”
- 下一阶段（立即执行）：
  1. 完整梳理数据源链路（market/external/data-fusion）
  2. 建立数据质量评分与可执行门控（研究/优化触发前置检查）
  3. 打通异常降级与缓存回退策略，降低外部数据抖动影响

---

## 2026-04-08 数据源统一化升级（双渠道）

### 目标

- 将分散的数据获取统一收口到一个模块中心，支持降级容错并提供中文可读输出给前端。

### 已实施

- 新增 `src/modules/data/data_source_hub.py`：
  - 统一交易所渠道（渠道A）：行情、K线、订单簿、持仓、挂单、未平仓量、资金费率、爆仓风险代理
  - 统一外部情报渠道（渠道B）：链上、新闻、舆情情绪
  - 提供 `get_unified_snapshot(symbol)`，输出：
    - `渠道A_交易所实时执行数据`
    - `渠道B_链上新闻舆情数据`
    - `统一分析判断`
    - `数据质量评估`
    - `数据来源状态`
- API 接口统一收口到 Hub：
  - 已改造 `market/ticker|klines|orderbook|symbols`
  - 已改造 `data-fusion/analyze`
  - 新增 `data-hub/status`
  - 新增 `data-hub/unified-snapshot`
  - 新增/补齐 `external/analyze-trends|signals|indicators`
  - 增加 query 参数兼容路由，避免前后端调用断裂
- 前端中文模块化接入：
  - `frontend/src/services/api.js` 新增 `dataHub` API
  - `frontend/src/modules/control-hub/ControlHubModule.jsx` 增加“统一双渠道快照（中文）”展示

### 降级策略

- 任一来源失败时不阻断总链路，自动退化到可用来源并标记 `provenance`。
- 数据质量分会反映通道退化原因（如订单簿缺失、链上退化、舆情退化）。
- 输出中保留来源状态说明，供策略与前端做风险提示。

---

## 2026-04-08 市场分析模块并入交易链路

### 已完成

- 保留并升级 `src/modules/data/own_market_analyzer.py`（不删除重做）：
  - 通过 `DataSourceHub` 纳入统一分析输出
  - 结果进入 `统一分析判断` 与 `大资金与大户监控`
- `DataSourceHub` 增强：
  - 自动回退读取 `ai_trading_engine` 已初始化的 `third_party_data` / `onchain_data`
  - 汇总链上大户活跃、交易所资金流样本、盘口大单监控
- 交易引擎联动：
  - `AITradingEngine._analyze_market` 引入 `get_unified_snapshot(symbol)` 作为统一分析输入
  - `AITradingEngine._make_decision` 新增数据质量门控（低质量数据禁止新开仓）
- 主控制器联动：
  - `MainController` 初始化 `data_source_hub`
  - 修正信息收集器初始化顺序后的分析器引用同步（`market_analyzer`/`onchain_integrator`）

### 作用

- 所有关键数据（交易所+链上+新闻舆情+市场分析）进入统一快照，再进入交易决策，减少分散取数导致的判断偏差。
- 在数据源退化时自动降级到“观望优先”，降低误开仓风险。

---

## 2026-04-08 数据质量评分与优化建议插件

### 已完成

- 新增 `src/modules/data/data_quality_advisor.py`：
  - 基于统一快照给出：
    - `quality_score`（当前数据质量）
    - `effectiveness_score`（对交易决策的作用）
    - `stability_score`（历史窗口稳定性）
    - `confidence/grade`
    - `suggestions`（可执行优化建议）
- `DataSourceHub` 已接入顾问模块：
  - 在 `get_unified_snapshot(symbol)` 输出新增 `数据质量与作用评分`
  - 支持短期历史表现评分（窗口化）
- API 已开放：
  - `GET /api/v1/data-hub/quality-advice?symbol=...`
- 前端总控已展示：
  - 评分等级、置信度、质量分、作用分、稳定性
  - 中文建议列表

### 说明

- 该能力采用“插件化风格”，可继续接入 plugin manager 做热插拔版本管理。
- 当前先以稳定接入为主，后续可扩展到“按策略维度评分”和“按执行结果回灌评分”。

---

## 2026-04-08 司令部总对接收尾（前端/TG/后端统一）

### 已完成

- 司令部统一接口（`module_control_api`）：
  - `GET /api/v1/modules/commander/snapshot`：统一状态快照
  - `POST /api/v1/modules/commander/chores`：司令部日常任务（可带优化）
  - `POST /api/v1/modules/commander/dispatch`：统一指令分发（前端/TG同入口）
  - `GET /api/v1/modules/commander/audit`：全链路接入审查
- 记忆复盘接口：
  - `GET /api/v1/modules/memory/daily-summary`
  - `POST /api/v1/modules/memory/daily-summary/run`
- 前端总控（`ControlHubModule`）对接司令部：
  - 指挥页新增：司令部任务按钮、司令部消息输入、审查结果、统一快照
  - 策略页新增：每日复盘记忆卡片 + 手动触发每日复盘
- TG/消息通道与司令部统一：
  - Telegram 继续走 `main_controller.process_user_command`
  - 前端 `dispatch` 同链路接入，形成统一中枢

### AI自主与安全边界

- AI执行器新增自然语言技能别名映射（chat 也可触发技能动作）：
  - 巡检 / 复盘 / 策略研发 / 回测 / 优化 / 强制开平仓 / SLTP状态
- 高风险动作确认模板：
  - 强制开仓/强制平仓需“确认/立即执行/批准”后执行
- 每日自动总结：
  - 自主循环中每日写入交易复盘记忆（交易数、胜率、盈亏、回撤）
  - 支持手动强制触发

### 记忆库统一化与恢复

- 已执行备份优先迁移：
  - `scripts/memory_unify_migrate.py`
  - `scripts/memory_restore_optimize.py`
- 统一结构保留：
  - `workspace/memory/{core,working,experience,history,trades,sessions,_archive}`
- 旧库已移除，备份与归档保留，可回滚。

### 审查结论（代码级）

- 后端语法检查通过（`py_compile`）
- 前端/后端 lints 无新增报错
- 司令部接口、前端入口、消息通道、记忆复盘链路已完成统一对接

---

**Happy Coding! 🚀**
