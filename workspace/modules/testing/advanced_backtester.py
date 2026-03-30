#!/usr/bin/env python3
"""
高级回测框架
支持多参数优化、滚动窗口、蒙特卡洛模拟等高级功能
"""

import asyncio
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
import json
import itertools
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

@dataclass
class BacktestResult:
    """回测结果"""
    strategy_name: str
    parameters: Dict[str, Any]
    start_date: datetime
    end_date: datetime
    
    # 性能指标
    total_return: float = 0.0
    annual_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    calmar_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    avg_trade_return: float = 0.0
    
    # 风险指标
    volatility: float = 0.0
    downside_risk: float = 0.0
    var_95: float = 0.0  # 95% VaR
    cvar_95: float = 0.0  # 95% CVaR
    
    # 交易统计
    long_trades: int = 0
    short_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_winning_trade: float = 0.0
    avg_losing_trade: float = 0.0
    
    # 资金曲线
    equity_curve: List[float] = field(default_factory=list)
    drawdown_curve: List[float] = field(default_factory=list)
    
    # 交易记录
    trades: List[Dict] = field(default_factory=list)

@dataclass
class ParameterGrid:
    """参数网格"""
    parameter_name: str
    values: List[Any]
    value_type: str  # 'discrete', 'continuous', 'log'

@dataclass
class WalkForwardResult:
    """滚动窗口回测结果"""
    window_index: int
    in_sample_result: BacktestResult
    out_of_sample_result: BacktestResult
    parameter_drift: float = 0.0
    performance_decay: float = 0.0

class AdvancedBacktester:
    """高级回测器"""
    
    def __init__(self, data_provider, commission_rate: float = 0.001, slippage: float = 0.001):
        self.data_provider = data_provider
        self.commission_rate = commission_rate
        self.slippage = slippage
        
        # 回测结果存储
        self.results: Dict[str, List[BacktestResult]] = defaultdict(list)
        
        # 优化器
        self.optimizers = {
            'grid_search': self._grid_search_optimization,
            'random_search': self._random_search_optimization,
            'bayesian': self._bayesian_optimization,
            'genetic': self._genetic_optimization
        }
        
    async def backtest_strategy(self, strategy: Callable, parameters: Dict[str, Any], 
                              start_date: datetime, end_date: datetime, 
                              symbol: str = 'BTCUSDT', timeframe: str = '1h') -> BacktestResult:
        """回测单个策略"""
        
        print(f"🎯 开始回测策略: {strategy.__name__}")
        print(f"   参数: {parameters}")
        print(f"   期间: {start_date.date()} 至 {end_date.date()}")
        print(f"   品种: {symbol}, 周期: {timeframe}")
        
        # 获取历史数据
        historical_data = await self._get_historical_data(
            symbol, timeframe, start_date, end_date
        )
        
        if historical_data.empty:
            print("❌ 无历史数据")
            return None
        
        print(f"   数据量: {len(historical_data)} 条")
        
        # 初始化回测状态
        state = self._initialize_backtest_state(historical_data.iloc[0])
        
        # 运行回测
        trades = []
        equity_curve = []
        drawdown_curve = []
        
        for i in range(1, len(historical_data)):
            current_data = historical_data.iloc[i]
            previous_data = historical_data.iloc[i-1]
            
            # 更新状态
            state = self._update_state(state, current_data, previous_data)
            
            # 执行策略
            signal = await strategy(current_data, state, parameters)
            
            if signal:
                # 执行交易
                trade = self._execute_trade(signal, state, current_data)
                if trade:
                    trades.append(trade)
                    state = self._update_state_after_trade(state, trade)
            
            # 记录资金曲线
            equity_curve.append(state['equity'])
            
            # 计算回撤
            drawdown = self._calculate_drawdown(state)
            drawdown_curve.append(drawdown)
        
        # 计算性能指标
        result = self._calculate_performance_metrics(
            strategy.__name__, parameters, start_date, end_date,
            trades, equity_curve, drawdown_curve, historical_data
        )
        
        print(f"✅ 回测完成:")
        print(f"   总收益: {result.total_return:.2%}")
        print(f"   夏普比率: {result.sharpe_ratio:.2f}")
        print(f"   最大回撤: {result.max_drawdown:.2%}")
        print(f"   交易次数: {result.total_trades}")
        
        return result
    
    async def optimize_parameters(self, strategy: Callable, param_grids: List[ParameterGrid],
                                start_date: datetime, end_date: datetime,
                                optimization_method: str = 'grid_search',
                                n_iterations: int = 100,
                                metric: str = 'sharpe_ratio') -> Dict[str, Any]:
        """参数优化"""
        
        print(f"🔧 开始参数优化")
        print(f"   优化方法: {optimization_method}")
        print(f"   评估指标: {metric}")
        print(f"   迭代次数: {n_iterations}")
        
        if optimization_method not in self.optimizers:
            print(f"❌ 不支持的优化方法: {optimization_method}")
            return {}
        
        # 调用优化器
        optimizer = self.optimizers[optimization_method]
        optimal_params = await optimizer(
            strategy, param_grids, start_date, end_date, n_iterations, metric
        )
        
        print(f"✅ 参数优化完成")
        print(f"   最优参数: {optimal_params}")
        
        return optimal_params
    
    async def walk_forward_analysis(self, strategy: Callable, parameters: Dict[str, Any],
                                  start_date: datetime, end_date: datetime,
                                  window_size_days: int = 180, step_size_days: int = 30,
                                  validation_ratio: float = 0.3) -> List[WalkForwardResult]:
        """滚动窗口分析"""
        
        print(f"📊 开始滚动窗口分析")
        print(f"   窗口大小: {window_size_days} 天")
        print(f"   步长: {step_size_days} 天")
        print(f"   验证比例: {validation_ratio}")
        
        results = []
        current_start = start_date
        
        window_index = 0
        
        while current_start + timedelta(days=window_size_days) <= end_date:
            window_end = current_start + timedelta(days=window_size_days)
            
            # 划分训练集和验证集
            in_sample_end = current_start + timedelta(
                days=int(window_size_days * (1 - validation_ratio))
            )
            
            # 训练集回测
            print(f"   窗口 {window_index + 1}: {current_start.date()} 至 {window_end.date()}")
            print(f"     训练集: {current_start.date()} 至 {in_sample_end.date()}")
            
            in_sample_result = await self.backtest_strategy(
                strategy, parameters, current_start, in_sample_end
            )
            
            if not in_sample_result:
                print(f"     训练集回测失败，跳过此窗口")
                current_start += timedelta(days=step_size_days)
                window_index += 1
                continue
            
            # 验证集回测
            print(f"     验证集: {in_sample_end.date()} 至 {window_end.date()}")
            
            out_of_sample_result = await self.backtest_strategy(
                strategy, parameters, in_sample_end, window_end
            )
            
            if not out_of_sample_result:
                print(f"     验证集回测失败，跳过此窗口")
                current_start += timedelta(days=step_size_days)
                window_index += 1
                continue
            
            # 计算参数漂移和性能衰减
            parameter_drift = self._calculate_parameter_drift(
                in_sample_result, out_of_sample_result
            )
            
            performance_decay = self._calculate_performance_decay(
                in_sample_result, out_of_sample_result
            )
            
            # 保存结果
            walk_forward_result = WalkForwardResult(
                window_index=window_index,
                in_sample_result=in_sample_result,
                out_of_sample_result=out_of_sample_result,
                parameter_drift=parameter_drift,
                performance_decay=performance_decay
            )
            
            results.append(walk_forward_result)
            
            print(f"     参数漂移: {parameter_drift:.4f}, 性能衰减: {performance_decay:.4f}")
            
            # 移动到下一个窗口
            current_start += timedelta(days=step_size_days)
            window_index += 1
        
        print(f"✅ 滚动窗口分析完成，共 {len(results)} 个窗口")
        
        return results
    
    async def monte_carlo_simulation(self, strategy: Callable, parameters: Dict[str, Any],
                                   start_date: datetime, end_date: datetime,
                                   n_simulations: int = 1000,
                                   confidence_level: float = 0.95) -> Dict[str, Any]:
        """蒙特卡洛模拟"""
        
        print(f"🎲 开始蒙特卡洛模拟")
        print(f"   模拟次数: {n_simulations}")
        print(f"   置信水平: {confidence_level}")
        
        # 获取基准回测结果
        baseline_result = await self.backtest_strategy(
            strategy, parameters, start_date, end_date
        )
        
        if not baseline_result:
            print("❌ 基准回测失败")
            return {}
        
        # 模拟参数
        simulated_results = []
        
        for i in range(n_simulations):
            if i % 100 == 0:
                print(f"   进度: {i}/{n_simulations}")
            
            # 随机扰动参数
            perturbed_params = self._perturb_parameters(parameters)
            
            # 随机选择时间窗口
            sim_start, sim_end = self._random_time_window(start_date, end_date)
            
            # 回测
            sim_result = await self.backtest_strategy(
                strategy, perturbed_params, sim_start, sim_end
            )
            
            if sim_result:
                simulated_results.append(sim_result)
        
        # 分析模拟结果
        analysis = self._analyze_monte_carlo_results(
            baseline_result, simulated_results, confidence_level
        )
        
        print(f"✅ 蒙特卡洛模拟完成")
        print(f"   成功模拟: {len(simulated_results)} 次")
        
        return analysis
    
    async def stress_test(self, strategy: Callable, parameters: Dict[str, Any],
                         scenarios: List[str] = None) -> Dict[str, BacktestResult]:
        """压力测试"""
        
        if scenarios is None:
            scenarios = [
                'crash_30',      # 30%暴跌
                'flash_crash',   # 闪崩
                'slow_drain',    # 缓慢下跌
                'high_volatility', # 高波动
                'low_liquidity',   # 低流动性
            ]
        
        print(f"🌪️  开始压力测试")
        print(f"   测试场景: {scenarios}")
        
        results = {}
        
        for scenario in scenarios:
            print(f"   测试场景: {scenario}")
            
            # 应用场景
            scenario_data = self._apply_stress_scenario(scenario)
            
            # 回测
            result = await self.backtest_strategy_with_scenario(
                strategy, parameters, scenario_data
            )
            
            if result:
                results[scenario] = result
                print(f"     结果: 收益 {result.total_return:.2%}, 回撤 {result.max_drawdown:.2%}")
        
        print(f"✅ 压力测试完成")
        
        return results
    
    # 私有方法
    
    async def _get_historical_data(self, symbol: str, timeframe: str,
                                 start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """获取历史数据"""
        
        # 这里应该调用数据提供者
        # 暂时返回模拟数据
        
        dates = pd.date_range(start=start_date, end=end_date, freq=timeframe)
        
        # 模拟价格数据（几何布朗运动）
        n_periods = len(dates)
        returns = np.random.normal(0.0001, 0.02, n_periods)  # 每日0.01%收益，2%波动
        
        prices = 50000 * np.exp(np.cumsum(returns))  # 起始价格5万
        
        # 创建DataFrame
        df = pd.DataFrame({
            'timestamp': dates,
            'open': prices * (1 + np.random.uniform(-0.001, 0.001, n_periods)),
            'high': prices * (1 + np.random.uniform(0, 0.005, n_periods)),
            'low': prices * (1 - np.random.uniform(0, 0.005, n_periods)),
            'close': prices,
            'volume': np.random.uniform(1000, 10000, n_periods)
        })
        
        df.set_index('timestamp', inplace=True)
        
        return df
    
    def _initialize_backtest_state(self, initial_data: pd.Series) -> Dict[str, Any]:
        """初始化回测状态"""
        
        return {
            'equity': 10000.0,  # 初始资金
            'cash': 10000.0,    # 现金
            'position': 0.0,    # 持仓数量
            'position_value': 0.0,  # 持仓价值
            'entry_price': 0.0,  # 入场价格
            'total_commission': 0.0,  # 总佣金
            'total_slippage': 0.0,  # 总滑点
            'peak_equity': 10000.0,  # 峰值资金
            'current_price': initial_data['close'],
            'timestamp': initial_data.name
        }
    
    def _update_state(self, state: Dict, current_data: pd.Series, 
                     previous_data: pd.Series) -> Dict[str, Any]:
        """更新状态"""
        
        # 更新价格
        state['current_price'] = current_data['close']
        state['timestamp'] = current_data.name
        
        # 更新持仓价值
        if state['position'] != 0:
            state['position_value'] = state['position'] * state['current_price']
            state['equity'] = state['cash'] + state['position_value']
        else:
            state['equity'] = state['cash']
        
        # 更新峰值资金
        if state['equity'] > state['peak_equity']:
            state['peak_equity'] = state['equity']
        
        return state
    
    def _execute_trade(self, signal: Dict, state: Dict, current_data: pd.Series) -> Optional[Dict]:
        """执行交易"""
        
        trade_type = signal.get('type', 'buy')  # buy, sell, close
        quantity = signal.get('quantity', 0)
        price = signal.get('price', current_data['close'])
        
        if quantity <= 0:
            return None
        
        # 计算滑点
        slippage = price * self.slippage
        if trade_type == 'buy':
            execution_price = price + slippage
        else:
            execution_price = price - slippage
        
        # 计算佣金
        trade_value = quantity * execution_price
        commission = trade_value * self.commission_rate
        
        trade = {
            'timestamp': current_data.name,
            'type': trade_type,
            'quantity': quantity,
            'price': execution_price,
            'slippage': slippage,
            'commission': commission,
            'value': trade_value
        }
        
        # 更新状态
        if trade_type == 'buy':
            if state['cash'] >= trade_value + commission:
                state['cash'] -= (trade_value + commission)
                state['position'] += quantity
                state['entry_price'] = execution_price
                state['total_commission'] += commission
                state['total_slippage'] += slippage
            else:
                return None  # 资金不足
        
        elif trade_type == 'sell':
            if state['position'] >= quantity:
                state['cash'] += (trade_value - commission)
                state['position'] -= quantity
                state['total_commission'] += commission
                state['total_slippage'] += slippage
                
                # 计算盈亏
                if state['entry_price'] > 0:
                    trade['pnl'] = (execution_price - state['entry_price']) * quantity
                    trade['pnl_percent'] = (execution_price - state['entry_price']) / state['entry_price']
            else:
                return None  # 持仓不足
        
        elif trade_type == 'close':
            if state['position'] > 0:
                # 平多
                state['cash'] += (trade_value - commission)
                trade['pnl'] = (execution_price - state['entry_price']) * state['position']
                trade['pnl_percent'] = (execution_price - state['entry_price']) / state['entry_price']
            elif state['position'] < 0:
                # 平空（如果有空头）
                state['cash'] += (trade_value - commission)
                # 这里简化处理
        
        return trade
    
    def _update_state_after_trade(self, state: Dict, trade: Dict) -> Dict[str, Any]:
        """交易后更新状态"""
        
        # 已经在上面的_execute_trade中更新了
        return state
    
    def _calculate_drawdown(self, state: Dict) -> float:
        """计算回撤"""
        
        if state['peak_equity'] == 0:
            return 0.0
        
        drawdown = (state['peak_equity'] - state['equity']) / state['peak_equity']
        return max(0.0, drawdown)
    
    def _calculate_performance_metrics(self, strategy_name: str, parameters: Dict[str, Any],
                                     start_date: datetime, end_date: datetime,
                                     trades: List[Dict], equity_curve: List[float],
                                     drawdown_curve: List[float], 
                                     historical_data: pd.DataFrame) -> BacktestResult:
        """计算性能指标"""
        
        if not trades or not equity_curve:
            return BacktestResult(
                strategy_name=strategy_name,
                parameters=parameters,
                start_date=start_date,
                end_date=end_date
            )
        
        # 基础计算
        initial_equity = equity_curve[0]
        final_equity = equity_curve[-1]
        total_return = (final_equity - initial_equity) / initial_equity
        
        # 计算年化收益
        days = (end_date - start_date).days
        if days > 0:
            annual_return = (1 + total_return) ** (365 / days) - 1
        else:
            annual_return = total_return
        
        # 计算收益序列
        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i-1] > 0:
                ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
                returns.append(ret)
        
        if returns:
            # 夏普比率（假设无风险利率为0）
            avg_return = np.mean(returns)
            std_return = np.std(returns)
            if std_return > 0:
                sharpe_ratio = avg_return / std_return * np.sqrt(252)  # 年化
            else:
                sharpe_ratio = 0.0
            
            # Sortino比率（只考虑下行风险）
            downside_returns = [r for r in returns if r < 0]
            if downside_returns:
                downside_std = np.std(downside_returns)
                if downside_std > 0:
                    sortino_ratio = avg_return / downside_std * np.sqrt(252)
                else:
                    sortino_ratio = sharpe_ratio
            else:
                sortino_ratio = sharpe_ratio
            
            # 波动率
            volatility = std_return * np.sqrt(252)
            
            # 下行风险
            downside_risk = np.std(downside_returns) * np.sqrt(252) if downside_returns else 0.0
            
            # VaR和CVaR
            if returns:
                var_95 = np.percentile(returns, 5)  # 95% VaR
                cvar_95 = np.mean([r for r in returns if r <= var_95])
            else:
                var_95 = 0.0
                cvar_95 = 0.0
        
        else:
            sharpe_ratio = 0.0
            sortino_ratio = 0.0
            volatility = 0.0
            downside_risk = 0.0
            var_95 = 0.0
            cvar_95 = 0.0
        
        # 最大回撤
        max_drawdown = max(drawdown_curve) if drawdown_curve else 0.0
        
        # Calmar比率
        if max_drawdown > 0:
            calmar_ratio = annual_return / max_drawdown
        else:
            calmar_ratio = 0.0
        
        # 交易统计
        total_trades = len(trades)
        winning_trades = 0
        losing_trades = 0
        long_trades = 0
        short_trades = 0
        
        pnls = []
        winning_pnls = []
        losing_pnls = []
        
        for trade in trades:
            if trade.get('type') == 'buy':
                long_trades += 1
            elif trade.get('type') == 'sell':
                short_trades += 1
            
            pnl = trade.get('pnl', 0)
            pnls.append(pnl)
            
            if pnl > 0:
                winning_trades += 1
                winning_pnls.append(pnl)
            elif pnl < 0:
                losing_trades += 1
                losing_pnls.append(pnl)
        
        # 胜率
        if total_trades > 0:
            win_rate = winning_trades / total_trades
        else:
            win_rate = 0.0
        
        # 平均交易收益
        if total_trades > 0:
            avg_trade_return = sum(pnls) / total_trades
        else:
            avg_trade_return = 0.0
        
        # 盈利因子
        total_profit = sum([p for p in pnls if p > 0])
        total_loss = abs(sum([p for p in pnls if p < 0]))
        
        if total_loss > 0:
            profit_factor = total_profit / total_loss
        else:
            profit_factor = float('inf') if total_profit > 0 else 0.0
        
        # 平均盈利/亏损
        avg_winning_trade = np.mean(winning_pnls) if winning_pnls else 0.0
        avg_losing_trade = np.mean(losing_pnls) if losing_pnls else 0.0
        
        result = BacktestResult(
            strategy_name=strategy_name,
            parameters=parameters,
            start_date=start_date,
            end_date=end_date,
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            calmar_ratio=calmar_ratio,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            avg_trade_return=avg_trade_return,
            volatility=volatility,
            downside_risk=downside_risk,
            var_95=var_95,
            cvar_95=cvar_95,
            long_trades=long_trades,
            short_trades=short_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_winning_trade=avg_winning_trade,
            avg_losing_trade=avg_losing_trade,
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            trades=trades
        )
        
        return result
    
    async def _grid_search_optimization(self, strategy: Callable, param_grids: List[ParameterGrid],
                                      start_date: datetime, end_date: datetime,
                                      n_iterations: int, metric: str) -> Dict[str, Any]:
        """网格搜索优化"""
        
        # 生成所有参数组合
        param_names = [pg.parameter_name for pg in param_grids]
        param_values = [pg.values for pg in param_grids]
        
        # 限制组合数量
        total_combinations = np.prod([len(vals) for vals in param_values])
        if total_combinations > n_iterations:
            # 随机采样
            combinations = []
            for _ in range(min(n_iterations, total_combinations)):
                combo = {}
                for pg in param_grids:
                    combo[pg.parameter_name] = np.random.choice(pg.values)
                combinations.append(combo)
        else:
            # 全组合
            combinations = [
                dict(zip(param_names, combo))
                for combo in itertools.product(*param_values)
            ]
        
        # 并行回测
        results = []
        for i, params in enumerate(combinations):
            print(f"   进度: {i+1}/{len(combinations)}")
            
            result = await self.backtest_strategy(
                strategy, params, start_date, end_date
            )
            
            if result:
                results.append((params, result))
        
        # 找出最优参数
        if not results:
            return {}
        
        # 根据指标排序
        metric_values = []
        for params, result in results:
            if metric == 'sharpe_ratio':
                metric_values.append(result.sharpe_ratio)
            elif metric == 'total_return':
                metric_values.append(result.total_return)
            elif metric == 'sortino_ratio':
                metric_values.append(result.sortino_ratio)
            elif metric == 'calmar_ratio':
                metric_values.append(result.calmar_ratio)
            else:
                metric_values.append(result.sharpe_ratio)  # 默认
        
        best_index = np.argmax(metric_values)
        best_params, best_result = results[best_index]
        
        print(f"   最佳 {metric}: {metric_values[best_index]:.4f}")
        
        return best_params
    
    async def _random_search_optimization(self, strategy: Callable, param_grids: List[ParameterGrid],
                                        start_date: datetime, end_date: datetime,
                                        n_iterations: int, metric: str) -> Dict[str, Any]:
        """随机搜索优化"""
        
        # 与网格搜索类似，但更随机
        return await self._grid_search_optimization(
            strategy, param_grids, start_date, end_date, n_iterations, metric
        )
    
    async def _bayesian_optimization(self, strategy: Callable, param_grids: List[ParameterGrid],
                                   start_date: datetime, end_date: datetime,
                                   n_iterations: int, metric: str) -> Dict[str, Any]:
        """贝叶斯优化"""
        
        # 简化的贝叶斯优化
        print("   ⚠️ 贝叶斯优化简化实现，使用随机搜索替代")
        return await self._random_search_optimization(
            strategy, param_grids, start_date, end_date, n_iterations, metric
        )
    
    async def _genetic_optimization(self, strategy: Callable, param_grids: List[ParameterGrid],
                                  start_date: datetime, end_date: datetime,
                                  n_iterations: int, metric: str) -> Dict[str, Any]:
        """遗传算法优化"""
        
        # 简化的遗传算法
        print("   ⚠️ 遗传算法优化简化实现，使用随机搜索替代")
        return await self._random_search_optimization(
            strategy, param_grids, start_date, end_date, n_iterations, metric
        )
    
    def _calculate_parameter_drift(self, in_sample: BacktestResult, 
                                 out_of_sample: BacktestResult) -> float:
        """计算参数漂移"""
        
        # 简化：比较关键指标的变化
        metrics = ['sharpe_ratio', 'total_return', 'max_drawdown']
        drifts = []
        
        for metric in metrics:
            in_value = getattr(in_sample, metric, 0)
            out_value = getattr(out_of_sample, metric, 0)
            
            if in_value != 0:
                drift = abs(out_value - in_value) / abs(in_value)
                drifts.append(drift)
        
        return np.mean(drifts) if drifts else 0.0
    
    def _calculate_performance_decay(self, in_sample: BacktestResult,
                                   out_of_sample: BacktestResult) -> float:
        """计算性能衰减"""
        
        # 使用夏普比率衰减
        in_sharpe = in_sample.sharpe_ratio
        out_sharpe = out_of_sample.sharpe_ratio
        
        if in_sharpe > 0:
            decay = max(0, (in_sharpe - out_sharpe) / in_sharpe)
        else:
            decay = 0.0
        
        return decay
    
    def _perturb_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """扰动参数"""
        
        perturbed = parameters.copy()
        
        for key, value in parameters.items():
            if isinstance(value, (int, float)):
                # 添加随机扰动
                if isinstance(value, int):
                    perturbation = np.random.randint(-10, 10)
                    perturbed[key] = max(1, value + perturbation)
                else:
                    perturbation = np.random.uniform(-0.1, 0.1) * value
                    perturbed[key] = max(0.01, value + perturbation)
        
        return perturbed
    
    def _random_time_window(self, start_date: datetime, end_date: datetime) -> Tuple[datetime, datetime]:
        """随机选择时间窗口"""
        
        total_days = (end_date - start_date).days
        if total_days <= 30:
            return start_date, end_date
        
        # 随机选择开始日期
        random_start_days = np.random.randint(0, total_days - 30)
        random_start = start_date + timedelta(days=random_start_days)
        
        # 随机选择窗口长度（30-180天）
        window_days = np.random.randint(30, min(180, total_days - random_start_days))
        random_end = random_start + timedelta(days=window_days)
        
        return random_start, random_end
    
    def _analyze_monte_carlo_results(self, baseline: BacktestResult,
                                   simulations: List[BacktestResult],
                                   confidence_level: float) -> Dict[str, Any]:
        """分析蒙特卡洛模拟结果"""
        
        if not simulations:
            return {}
        
        # 收集关键指标
        metrics = {
            'total_return': [],
            'sharpe_ratio': [],
            'max_drawdown': [],
            'win_rate': []
        }
        
        for sim in simulations:
            metrics['total_return'].append(sim.total_return)
            metrics['sharpe_ratio'].append(sim.sharpe_ratio)
            metrics['max_drawdown'].append(sim.max_drawdown)
            metrics['win_rate'].append(sim.win_rate)
        
        # 计算置信区间
        analysis = {
            'baseline': asdict(baseline),
            'simulation_count': len(simulations),
            'confidence_level': confidence_level,
            'confidence_intervals': {}
        }
        
        for metric_name, values in metrics.items():
            if values:
                mean_value = np.mean(values)
                std_value = np.std(values)
                
                # 计算置信区间
                z_score = 1.96  # 95%置信区间
                ci_lower = mean_value - z_score * std_value / np.sqrt(len(values))
                ci_upper = mean_value + z_score * std_value / np.sqrt(len(values))
                
                analysis['confidence_intervals'][metric_name] = {
                    'mean': mean_value,
                    'std': std_value,
                    'ci_lower': ci_lower,
                    'ci_upper': ci_upper,
                    'baseline_value': getattr(baseline, metric_name, 0),
                    'is_baseline_in_ci': ci_lower <= getattr(baseline, metric_name, 0) <= ci_upper
                }
        
        return analysis
    
    def _apply_stress_scenario(self, scenario: str) -> Dict[str, Any]:
        """应用压力测试场景"""
        
        scenarios = {
            'crash_30': {
                'description': '30%市场暴跌',
                'price_shock': -0.30,
                'volatility_multiplier': 3.0,
                'liquidity_reduction': 0.5
            },
            'flash_crash': {
                'description': '闪崩（快速下跌30%）',
                'price_shock': -0.30,
                'volatility_multiplier': 10.0,
                'liquidity_reduction': 0.9
            },
            'slow_drain': {
                'description': '缓慢下跌（每天下跌1%）',
                'price_shock': -0.01,
                'volatility_multiplier': 1.5,
                'liquidity_reduction': 0.7
            },
            'high_volatility': {
                'description': '高波动市场',
                'price_shock': 0.0,
                'volatility_multiplier': 5.0,
                'liquidity_reduction': 0.3
            },
            'low_liquidity': {
                'description': '低流动性市场',
                'price_shock': 0.0,
                'volatility_multiplier': 2.0,
                'liquidity_reduction': 0.9
            }
        }
        
        return scenarios.get(scenario, {})
    
    async def backtest_strategy_with_scenario(self, strategy: Callable, parameters: Dict[str, Any],
                                            scenario_data: Dict) -> Optional[BacktestResult]:
        """带场景的回测"""
        
        # 这里应该应用场景到数据
        # 简化实现：直接回测
        return await self.backtest_strategy(
            strategy, parameters, 
            datetime.now() - timedelta(days=90),
            datetime.now()
        )
    
    # 公共接口
    
    def save_results(self, filename: str):
        """保存回测结果"""
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                data = {
                    'results': {
                        strategy_name: [asdict(result) for result in results]
                        for strategy_name, results in self.results.items()
                    }
                }
                json.dump(data, f, indent=2, default=str)
            
            print(f"✅ 回测结果已保存到: {filename}")
            
        except Exception as e:
            print(f"❌ 保存回测结果失败: {e}")
    
    def load_results(self, filename: str):
        """加载回测结果"""
        
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for strategy_name, results_data in data.get('results', {}).items():
                results = []
                for result_data in results_data:
                    # 转换回BacktestResult对象
                    result = BacktestResult(**result_data)
                    results.append(result)
                
                self.results[strategy_name] = results
            
            print(f"✅ 回测结果已从 {filename} 加载")
            
        except Exception as e:
            print(f"❌ 加载回测结果失败: {e}")
    
    def compare_strategies(self, strategy_names: List[str]) -> pd.DataFrame:
        """比较多个策略"""
        
        comparison_data = []
        
        for strategy_name in strategy_names:
            if strategy_name in self.results:
                # 取最近的回测结果
                results = self.results[strategy_name]
                if results:
                    latest_result = results[-1]
                    
                    comparison_data.append({
                        'strategy': strategy_name,
                        'total_return': latest_result.total_return,
                        'annual_return': latest_result.annual_return,
                        'sharpe_ratio': latest_result.sharpe_ratio,
                        'sortino_ratio': latest_result.sortino_ratio,
                        'max_drawdown': latest_result.max_drawdown,
                        'calmar_ratio': latest_result.calmar_ratio,
                        'win_rate': latest_result.win_rate,
                        'profit_factor': latest_result.profit_factor,
                        'total_trades': latest_result.total_trades
                    })
        
        df = pd.DataFrame(comparison_data)
        
        if not df.empty:
            df.set_index('strategy', inplace=True)
        
        return df

# 单例实例
_backtester = None

def get_backtester(data_provider=None, commission_rate: float = 0.001, slippage: float = 0.001) -> AdvancedBacktester:
    """获取回测器单例"""
    global _backtester
    if _backtester is None:
        _backtester = AdvancedBacktester(data_provider, commission_rate, slippage)
    return _backtester

async def test_backtester():
    """测试回测器"""
    
    # 简单的策略示例
    async def simple_strategy(data, state, parameters):
        """简单移动平均策略"""
        
        # 这里应该实现具体的策略逻辑
        # 简化实现：随机信号
        if np.random.random() < 0.1:  # 10%概率交易
            return {
                'type': 'buy' if np.random.random() > 0.5 else 'sell',
                'quantity': 0.1,
                'price': data['close']
            }
        return None
    
    # 创建回测器
    backtester = get_backtester()
    
    # 定义参数网格
    param_grids = [
        ParameterGrid('threshold', [0.05, 0.1, 0.15, 0.2], 'discrete'),
        ParameterGrid('window', [10, 20, 30, 50], 'discrete')
    ]
    
    # 单次回测
    result = await backtester.backtest_strategy(
        simple_strategy,
        {'threshold': 0.1, 'window': 20},
        datetime.now() - timedelta(days=90),
        datetime.now()
    )
    
    if result:
        print(f"回测结果: 收益 {result.total_return:.2%}, 夏普 {result.sharpe_ratio:.2f}")
    
    # 参数优化
    optimal_params = await backtester.optimize_parameters(
        simple_strategy,
        param_grids,
        datetime.now() - timedelta(days=180),
        datetime.now() - timedelta(days=90),
        optimization_method='grid_search',
        n_iterations=16,
        metric='sharpe_ratio'
    )
    
    print(f"最优参数: {optimal_params}")
    
    # 滚动窗口分析
    wfa_results = await backtester.walk_forward_analysis(
        simple_strategy,
        optimal_params,
        datetime.now() - timedelta(days=365),
        datetime.now(),
        window_size_days=90,
        step_size_days=30
    )
    
    print(f"滚动窗口分析完成: {len(wfa_results)} 个窗口")

if __name__ == "__main__":
    asyncio.run(test_backtester())