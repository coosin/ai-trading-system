# AI Trading Engine - 模块说明

## 概述

AI交易引擎是OpenClaw Trading系统的核心模块，负责执行智能交易决策。

## 核心功能

### 1. 交易决策
- 基于AI的市场分析
- 多维度技术指标计算
- 风险评估和仓位管理

### 2. 订单执行
- 自动下单
- 止损止盈管理
- 订单状态跟踪

### 3. 风险控制
- 实时风险监控
- 自动平仓机制
- 仓位限制管理

## 配置参数

```python
ai_config = {
    "enabled": True,                  # 是否启用AI
    "model_id": "astron-code-latest", # AI模型ID
    "analysis_interval": 60,          # 分析间隔（秒）
    "min_confidence": 0.65,           # 最小置信度
    "max_positions": 5,               # 最大持仓数
    "risk_per_trade": 0.02,           # 单笔风险（2%）
    "trade_mode": "real",             # 交易模式
    "auto_risk_management": True,     # 自动风险管理
    "critical_risk_auto_close": True  # 严重风险自动平仓
}
```

## 使用示例

```python
from src.modules.core.ai_trading_engine import AITradingEngine

# 初始化引擎
engine = AITradingEngine(config)

# 启动引擎
await engine.start()

# 执行交易决策
decision = await engine.make_decision(symbol="BTC/USDT")
await engine.execute_decision(decision)
```

## 依赖模块

- `exchange_base`: 交易所接口
- `technical_indicators`: 技术指标计算
- `risk_monitor`: 风险监控
- `data_storage`: 数据存储

## 注意事项

1. 确保交易所API配置正确
2. 监控系统资源使用情况
3. 定期检查交易日志
4. 注意风险控制参数设置

## 更新日志

- 2026-04-04: 添加自动风险管理功能
- 2026-04-04: 修复Order对象类型错误
- 2026-04-04: 优化持仓数据类型检查
