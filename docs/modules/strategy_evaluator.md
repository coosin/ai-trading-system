# 策略评估器 (StrategyEvaluator) 模块

## 概述

策略评估器模块是全智能量化交易系统的核心组件之一，负责对交易策略的性能进行全面评估。它提供了丰富的评估指标，包括传统的风险调整收益指标和高级的风险度量指标，帮助用户全面了解策略的表现。

## 核心功能

### 1. 基础收益指标

- **总收益**：策略的总体收益
- **年化收益**：将策略收益年化，便于不同时间周期的策略比较
- **夏普比率**：衡量策略每承担一单位风险所获得的超额收益
- **索提诺比率**：类似夏普比率，但只考虑下行风险
- **卡玛比率**：年化收益与最大回撤的比值，衡量策略的风险调整收益
- **欧米茄比率**：考虑收益分布的所有矩，比夏普比率更全面

### 2. 风险指标

- **波动率**：策略收益的标准差，衡量策略的波动程度
- **最大回撤**：策略从峰值到谷值的最大损失
- **Value at Risk (VaR)**：在给定置信水平下，策略在一定时间内可能的最大损失
- **Conditional Value at Risk (CVaR)**：在VaR之外的平均损失，衡量极端风险
- **峰度**：收益分布的尾部厚度，衡量极端事件的可能性
- **偏度**：收益分布的不对称性，衡量收益的偏斜程度

### 3. 交易指标

- **胜率**：盈利交易占总交易的比例
- **盈利因子**：总盈利与总亏损的比值
- **平均盈亏比**：平均盈利与平均亏损的比值
- **总交易次数**：策略执行的总交易次数
- **平均交易规模**：平均每次交易的收益/损失大小

### 4. 高级指标

- **Alpha**：策略相对于市场基准的超额收益
- **Beta**：策略相对于市场基准的敏感度
- **信息比率**：策略相对于基准的超额收益与跟踪误差的比值

## 类结构

```python
class StrategyEvaluator:
    def __init__(self, strategy_name):
        # 初始化策略评估器
        
    def add_trade(self, trade):
        # 添加交易记录
        
    def add_returns(self, returns):
        # 添加收益数据
        
    def calculate_total_return(self):
        # 计算总收益
        
    def calculate_annual_return(self, trading_days=252):
        # 计算年化收益
        
    def calculate_sharpe_ratio(self, risk_free_rate=0.0, trading_days=252):
        # 计算夏普比率
        
    # 其他评估方法...
```

## 使用示例

### 基本使用

```python
from src.modules.strategies.strategy_evaluator import StrategyEvaluator

# 创建策略评估器实例
evaluator = StrategyEvaluator("my_strategy")

# 添加交易记录
trades = [
    {"pnl": 100},
    {"pnl": -50},
    {"pnl": 150},
    {"pnl": -25},
    {"pnl": 200}
]

for trade in trades:
    evaluator.add_trade(trade)

# 获取评估报告
report = evaluator.get_evaluation_report()
print("策略评估报告:")
print(report)

# 获取风险指标
risk_metrics = evaluator.get_risk_metrics()
print("\n风险指标:")
print(risk_metrics)

# 获取性能指标
performance_metrics = evaluator.get_performance_metrics()
print("\n性能指标:")
print(performance_metrics)

# 获取交易指标
trade_metrics = evaluator.get_trade_metrics()
print("\n交易指标:")
print(trade_metrics)
```

### 高级使用 - 与市场基准比较

```python
# 假设我们有市场基准的收益数据
market_returns = [0.01, -0.005, 0.008, -0.002, 0.012]

# 计算Alpha和Beta
alpha, beta = evaluator.calculate_alpha_beta(market_returns)
print(f"Alpha: {alpha}, Beta: {beta}")

# 计算信息比率
information_ratio = evaluator.calculate_information_ratio(market_returns)
print(f"信息比率: {information_ratio}")

# 获取包含市场基准比较的完整报告
report_with_benchmark = evaluator.get_evaluation_report(market_returns=market_returns)
print("\n包含市场基准比较的评估报告:")
print(report_with_benchmark)
```

## 与其他模块的集成

### 与策略管理器集成

策略评估器可以与多策略管理器集成，对每个策略进行独立评估：

```python
from src.modules.strategies.multi_strategy_manager import MultiStrategyManager

# 假设我们有一个策略管理器实例
strategy_manager = MultiStrategyManager({})

# 对每个策略进行评估
for strategy_name, strategy in strategy_manager.strategies.items():
    # 获取策略的交易记录和收益
    trades = strategy.get_trades()
    returns = [trade['pnl'] for trade in trades]
    
    # 创建评估器并评估
    evaluator = StrategyEvaluator(strategy_name)
    for trade in trades:
        evaluator.add_trade(trade)
    
    report = evaluator.get_evaluation_report()
    print(f"策略 {strategy_name} 的评估报告:")
    print(report)
```

### 与回测系统集成

策略评估器可以与增强回测系统集成，评估回测结果：

```python
from src.modules.backtesting.enhanced_backtester import EnhancedBacktester

# 假设我们有一个回测器实例
backtester = EnhancedBacktester()

# 运行回测
backtest_result = backtester.run_multi_strategy_backtest(...)

# 提取回测结果中的收益和交易
returns = backtest_result.trades['pnl']
trades = backtest_result.trades

# 创建评估器并评估
evaluator = StrategyEvaluator("backtest_result")
evaluator.add_returns(returns)
for trade in trades:
    evaluator.add_trade(trade)

report = evaluator.get_evaluation_report()
print("回测结果评估报告:")
print(report)
```

## 最佳实践

1. **定期评估**：定期对策略进行评估，及时发现策略性能的变化
2. **多维度评估**：综合考虑收益、风险和交易指标，全面评估策略
3. **基准比较**：与市场基准或其他策略进行比较，了解策略的相对表现
4. **风险控制**：关注风险指标，确保策略的风险在可接受范围内
5. **持续优化**：根据评估结果，不断优化策略参数和逻辑

## 常见问题

### Q: 如何处理不同时间周期的策略评估？

A: 使用年化收益和年化风险指标，将不同时间周期的策略标准化，便于比较。

### Q: 如何评估多策略组合的性能？

A: 可以对每个策略单独评估，也可以将组合视为一个整体进行评估。对于组合评估，需要考虑策略之间的相关性。

### Q: 如何解释评估指标？

A: 不同指标有不同的含义，需要综合考虑。例如，高夏普比率表示策略的风险调整收益较好，但如果最大回撤过大，可能意味着策略在极端情况下表现不佳。

### Q: 如何处理评估数据不足的情况？

A: 对于新策略，可能存在数据不足的问题。此时可以考虑使用模拟数据或缩短评估周期，但需要注意结果的可靠性。