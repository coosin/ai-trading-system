from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Union

import numpy as np
import pandas as pd

from src.modules.strategy.multi_strategy_framework import BaseStrategy, StrategySignal, StrategyType
from src.modules.core.advanced_risk_manager import AdvancedRiskManager
from src.modules.core.intelligent_fund_manager import IntelligentFundManager

logger = logging.getLogger(__name__)


class BacktestStatus(Enum):
    """回测状态"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BacktestConfig:
    """回测配置"""
    symbol: str
    start_date: str
    end_date: str
    initial_balance: float
    leverage: float
    risk_per_trade: float
    strategies: List[StrategyType]
    parameters: Dict[str, Any]


@dataclass
class BacktestResult:
    """回测结果"""
    config: BacktestConfig
    total_trades: int
    win_rate: float
    total_profit: float
    total_loss: float
    net_profit: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    profit_factor: float
    average_win: float
    average_loss: float
    max_win: float
    max_loss: float
    holding_periods: List[float]
    equity_curve: List[float]
    drawdown_curve: List[float]
    start_time: float
    end_time: float
    execution_time: float


@dataclass
class Trade:
    """交易记录"""
    timestamp: float
    symbol: str
    action: str  # buy, sell
    price: float
    size: float
    leverage: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    close_timestamp: Optional[float]
    close_price: Optional[float]
    profit: Optional[float]
    holding_period: Optional[float]


class AdvancedBacktester:
    """高级回测系统"""

    def __init__(self, config: Dict[str, Any]):
        """初始化高级回测系统

        Args:
            config: 配置信息
        """
        self.config = config
        self.status = BacktestStatus.IDLE
        self.current_backtest = None
        self.risk_manager = None
        self.fund_manager = None

    async def initialize(self) -> bool:
        """初始化高级回测系统

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 初始化风险管理系统
            self.risk_manager = AdvancedRiskManager(None, self.config.get("risk_manager", {}))
            await self.risk_manager.initialize()
            
            # 初始化资金管理系统
            self.fund_manager = IntelligentFundManager(None, self.risk_manager, self.config.get("fund_manager", {}))
            await self.fund_manager.initialize()
            
            self.status = BacktestStatus.IDLE
            logger.info("AdvancedBacktester initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize AdvancedBacktester: {e}")
            self.status = BacktestStatus.FAILED
            return False

    async def shutdown(self) -> bool:
        """关闭高级回测系统

        Returns:
            bool: 关闭是否成功
        """
        try:
            if self.risk_manager:
                await self.risk_manager.shutdown()
            if self.fund_manager:
                await self.fund_manager.shutdown()
            
            self.status = BacktestStatus.IDLE
            self.current_backtest = None
            logger.info("AdvancedBacktester shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown AdvancedBacktester: {e}")
            return False

    async def run_backtest(self, backtest_config: BacktestConfig, data: pd.DataFrame) -> Optional[BacktestResult]:
        """运行回测

        Args:
            backtest_config: 回测配置
            data: 历史数据

        Returns:
            Optional[BacktestResult]: 回测结果
        """
        try:
            if self.status == BacktestStatus.RUNNING:
                logger.warning("Backtest already running")
                return None
            
            self.status = BacktestStatus.RUNNING
            self.current_backtest = backtest_config
            
            start_time = time.time()
            
            # 准备数据
            prepared_data = await self._prepare_data(data)
            
            # 执行回测
            result = await self._execute_backtest(backtest_config, prepared_data)
            
            end_time = time.time()
            result.execution_time = end_time - start_time
            result.start_time = start_time
            result.end_time = end_time
            
            self.status = BacktestStatus.COMPLETED
            logger.info(f"Backtest completed in {result.execution_time:.2f} seconds")
            
            return result
        except Exception as e:
            logger.error(f"Error running backtest: {e}")
            self.status = BacktestStatus.FAILED
            return None

    async def _prepare_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """准备数据

        Args:
            data: 原始数据

        Returns:
            pd.DataFrame: 准备好的数据
        """
        try:
            # 确保数据包含必要的列
            required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            for col in required_columns:
                if col not in data.columns:
                    logger.error(f"Missing required column: {col}")
                    raise ValueError(f"Missing required column: {col}")
            
            # 按时间排序
            data = data.sort_values('timestamp')
            
            # 添加技术指标
            data = await self._add_technical_indicators(data)
            
            return data
        except Exception as e:
            logger.error(f"Error preparing data: {e}")
            raise

    async def _add_technical_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """添加技术指标

        Args:
            data: 原始数据

        Returns:
            pd.DataFrame: 添加了技术指标的数据
        """
        try:
            # 计算移动平均线
            data['MA10'] = data['close'].rolling(window=10).mean()
            data['MA20'] = data['close'].rolling(window=20).mean()
            data['MA50'] = data['close'].rolling(window=50).mean()
            
            # 计算RSI
            delta = data['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            data['RSI'] = 100 - (100 / (1 + rs))
            
            # 计算MACD
            exp1 = data['close'].ewm(span=12, adjust=False).mean()
            exp2 = data['close'].ewm(span=26, adjust=False).mean()
            data['MACD'] = exp1 - exp2
            data['MACD_signal'] = data['MACD'].ewm(span=9, adjust=False).mean()
            
            # 计算布林带
            data['BB_middle'] = data['close'].rolling(window=20).mean()
            data['BB_std'] = data['close'].rolling(window=20).std()
            data['BB_upper'] = data['BB_middle'] + (data['BB_std'] * 2)
            data['BB_lower'] = data['BB_middle'] - (data['BB_std'] * 2)
            
            return data
        except Exception as e:
            logger.error(f"Error adding technical indicators: {e}")
            return data

    async def _execute_backtest(self, config: BacktestConfig, data: pd.DataFrame) -> BacktestResult:
        """执行回测

        Args:
            config: 回测配置
            data: 准备好的数据

        Returns:
            BacktestResult: 回测结果
        """
        try:
            # 初始化回测变量
            balance = config.initial_balance
            equity = balance
            equity_curve = [equity]
            drawdown_curve = [0]
            trades = []
            current_position = None
            
            # 模拟交易
            for i in range(1, len(data)):
                current_data = data.iloc[i]
                previous_data = data.iloc[i-1]
                
                # 检查是否需要平仓
                if current_position:
                    if current_data['low'] <= current_position.stop_loss:
                        # 触发止损
                        close_price = current_position.stop_loss
                        await self._close_position(current_position, close_price, current_data['timestamp'])
                        trades.append(current_position)
                        equity += current_position.profit
                        equity_curve.append(equity)
                        drawdown = (max(equity_curve) - equity) / max(equity_curve)
                        drawdown_curve.append(drawdown)
                        current_position = None
                    elif current_data['high'] >= current_position.take_profit:
                        # 触发止盈
                        close_price = current_position.take_profit
                        await self._close_position(current_position, close_price, current_data['timestamp'])
                        trades.append(current_position)
                        equity += current_position.profit
                        equity_curve.append(equity)
                        drawdown = (max(equity_curve) - equity) / max(equity_curve)
                        drawdown_curve.append(drawdown)
                        current_position = None
                
                # 生成交易信号
                if not current_position:
                    signal = await self._generate_signal(config, data.iloc[:i+1])
                    if signal and signal.action == "buy":
                        # 计算仓位大小
                        position_size = await self.fund_manager.calculate_position_size(
                            config.symbol,
                            current_data['close'],
                            signal.stop_loss or current_data['close'] * 0.95,
                            signal.confidence
                        )
                        
                        if position_size:
                            # 开仓
                            current_position = Trade(
                                timestamp=current_data['timestamp'],
                                symbol=config.symbol,
                                action="buy",
                                price=current_data['close'],
                                size=position_size.size,
                                leverage=position_size.leverage,
                                stop_loss=signal.stop_loss or current_data['close'] * 0.95,
                                take_profit=signal.take_profit or current_data['close'] * 1.05,
                                close_timestamp=None,
                                close_price=None,
                                profit=None,
                                holding_period=None
                            )
                
                # 更新权益曲线
                if not current_position:
                    equity_curve.append(equity)
                    drawdown = (max(equity_curve) - equity) / max(equity_curve)
                    drawdown_curve.append(drawdown)
            
            # 计算回测结果
            result = await self._calculate_backtest_result(config, trades, equity_curve, drawdown_curve)
            
            return result
        except Exception as e:
            logger.error(f"Error executing backtest: {e}")
            raise

    async def _generate_signal(self, config: BacktestConfig, data: pd.DataFrame) -> Optional[StrategySignal]:
        """生成交易信号

        Args:
            config: 回测配置
            data: 历史数据

        Returns:
            Optional[StrategySignal]: 交易信号
        """
        try:
            # 这里应该实现具体的信号生成逻辑
            # 暂时返回一个模拟信号
            if len(data) < 20:
                return None
            
            # 简单的移动平均线策略
            if data.iloc[-1]['MA10'] > data.iloc[-1]['MA20'] and data.iloc[-2]['MA10'] <= data.iloc[-2]['MA20']:
                return StrategySignal(
                    strategy_type=StrategyType.TREND_FOLLOWING,
                    symbol=config.symbol,
                    action="buy",
                    price=data.iloc[-1]['close'],
                    timestamp=data.iloc[-1]['timestamp'],
                    confidence=0.7,
                    stop_loss=data.iloc[-1]['close'] * 0.95,
                    take_profit=data.iloc[-1]['close'] * 1.05
                )
            
            return None
        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            return None

    async def _close_position(self, position: Trade, close_price: float, close_timestamp: float):
        """平仓

        Args:
            position: 持仓
            close_price: 平仓价格
            close_timestamp: 平仓时间
        """
        try:
            position.close_timestamp = close_timestamp
            position.close_price = close_price
            position.profit = (close_price - position.price) * position.size * position.leverage
            position.holding_period = (close_timestamp - position.timestamp) / (24 * 3600)  # 转换为天
        except Exception as e:
            logger.error(f"Error closing position: {e}")

    async def _calculate_backtest_result(self, config: BacktestConfig, trades: List[Trade], equity_curve: List[float], drawdown_curve: List[float]) -> BacktestResult:
        """计算回测结果

        Args:
            config: 回测配置
            trades: 交易记录
            equity_curve: 权益曲线
            drawdown_curve: 回撤曲线

        Returns:
            BacktestResult: 回测结果
        """
        try:
            # 计算基本指标
            total_trades = len(trades)
            winning_trades = [t for t in trades if t.profit > 0]
            losing_trades = [t for t in trades if t.profit <= 0]
            win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
            
            total_profit = sum(t.profit for t in winning_trades)
            total_loss = abs(sum(t.profit for t in losing_trades))
            net_profit = total_profit - total_loss
            
            max_drawdown = max(drawdown_curve)
            
            # 计算夏普比率
            returns = np.diff(equity_curve) / equity_curve[:-1]
            sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0
            
            # 计算索提诺比率
            downside_returns = [r for r in returns if r < 0]
            sortino_ratio = np.mean(returns) / np.std(downside_returns) * np.sqrt(252) if downside_returns else 0
            
            # 计算盈利因子
            profit_factor = total_profit / total_loss if total_loss > 0 else 0
            
            # 计算平均盈利和平均亏损
            average_win = total_profit / len(winning_trades) if winning_trades else 0
            average_loss = total_loss / len(losing_trades) if losing_trades else 0
            
            # 计算最大盈利和最大亏损
            max_win = max([t.profit for t in winning_trades]) if winning_trades else 0
            max_loss = min([t.profit for t in losing_trades]) if losing_trades else 0
            
            # 计算持有期
            holding_periods = [t.holding_period for t in trades if t.holding_period]
            
            return BacktestResult(
                config=config,
                total_trades=total_trades,
                win_rate=win_rate,
                total_profit=total_profit,
                total_loss=total_loss,
                net_profit=net_profit,
                max_drawdown=max_drawdown,
                sharpe_ratio=sharpe_ratio,
                sortino_ratio=sortino_ratio,
                profit_factor=profit_factor,
                average_win=average_win,
                average_loss=average_loss,
                max_win=max_win,
                max_loss=max_loss,
                holding_periods=holding_periods,
                equity_curve=equity_curve,
                drawdown_curve=drawdown_curve,
                start_time=0,
                end_time=0,
                execution_time=0
            )
        except Exception as e:
            logger.error(f"Error calculating backtest result: {e}")
            raise

    async def optimize_strategy(self, config: BacktestConfig, data: pd.DataFrame, parameter_ranges: Dict[str, List[float]]) -> Optional[Dict[str, Any]]:
        """优化策略参数

        Args:
            config: 回测配置
            data: 历史数据
            parameter_ranges: 参数范围

        Returns:
            Optional[Dict[str, Any]]: 最优参数
        """
        try:
            if self.status == BacktestStatus.RUNNING:
                logger.warning("Backtest already running")
                return None
            
            # 生成参数组合
            parameter_combinations = self._generate_parameter_combinations(parameter_ranges)
            
            # 测试每个参数组合
            best_result = None
            best_parameters = None
            
            for params in parameter_combinations:
                # 更新配置参数
                config.parameters.update(params)
                
                # 运行回测
                result = await self.run_backtest(config, data)
                
                # 比较结果
                if not best_result or result.sharpe_ratio > best_result.sharpe_ratio:
                    best_result = result
                    best_parameters = params
            
            logger.info(f"Optimization completed. Best parameters: {best_parameters}")
            return best_parameters
        except Exception as e:
            logger.error(f"Error optimizing strategy: {e}")
            return None

    def _generate_parameter_combinations(self, parameter_ranges: Dict[str, List[float]]) -> List[Dict[str, float]]:
        """生成参数组合

        Args:
            parameter_ranges: 参数范围

        Returns:
            List[Dict[str, float]]: 参数组合列表
        """
        try:
            import itertools
            
            # 获取参数名称和范围
            param_names = list(parameter_ranges.keys())
            param_values = [parameter_ranges[name] for name in param_names]
            
            # 生成所有组合
            combinations = list(itertools.product(*param_values))
            
            # 转换为字典列表
            result = []
            for combo in combinations:
                params = {}
                for i, name in enumerate(param_names):
                    params[name] = combo[i]
                result.append(params)
            
            return result
        except Exception as e:
            logger.error(f"Error generating parameter combinations: {e}")
            return []

    def get_status(self) -> BacktestStatus:
        """获取回测状态

        Returns:
            BacktestStatus: 回测状态
        """
        return self.status

    def is_healthy(self) -> bool:
        """检查高级回测系统健康状态

        Returns:
            bool: 健康状态
        """
        return self.status in [BacktestStatus.IDLE, BacktestStatus.COMPLETED]
