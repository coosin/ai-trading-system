"""
策略回测引擎

功能：
1. 基于历史数据的策略回测
2. 多时间周期支持
3. 性能指标计算
4. 风险评估
5. 回测结果可视化
"""

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """回测配置"""
    symbol: str
    start_time: datetime
    end_time: datetime
    initial_balance: float
    leverage: float = 1.0
    fee_rate: float = 0.001
    slippage: float = 0.0005
    time_frame: str = "1m"


@dataclass
class Trade:
    """交易记录"""
    timestamp: datetime
    symbol: str
    side: str  # buy, sell
    quantity: float
    price: float
    fee: float
    balance: float
    position: float
    pnl: float
    cumulative_pnl: float


@dataclass
class BacktestResult:
    """回测结果"""
    config: BacktestConfig
    trades: List[Trade]
    final_balance: float
    total_pnl: float
    win_rate: float
    average_win: float
    average_loss: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    profit_factor: float
    total_trades: int
    win_trades: int
    loss_trades: int
    start_balance: float
    equity_curve: List[Tuple[datetime, float]]
    drawdown_curve: List[Tuple[datetime, float]]
    # 新增字段
    calmar_ratio: float = 0.0
    beta: float = 0.0
    alpha: float = 0.0
    equity_series: Optional[pd.Series] = None
    positions: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)


class StrategyBase:
    """策略基类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = config.get("name", "BaseStrategy")
    
    def initialize(self, data: pd.DataFrame):
        """初始化策略"""
        pass
    
    def on_data(self, data: pd.DataFrame, index: int) -> Optional[Dict[str, Any]]:
        """处理数据并生成信号"""
        pass
    
    def on_finish(self):
        """回测完成时调用"""
        pass


class BacktestEngine:
    """回测引擎"""
    
    def __init__(self):
        self.strategy = None
        self.data = None
        self.config = None
        # 新增多策略支持
        self.strategies = {}
        self.market_data = {}
        self.portfolio = {}
        self.positions = {}
    
    async def run_backtest(self, strategy: StrategyBase, data: pd.DataFrame, config: BacktestConfig) -> BacktestResult:
        """运行回测"""
        self.strategy = strategy
        self.data = data
        self.config = config
        
        # 初始化策略
        self.strategy.initialize(data)
        
        # 初始化回测状态
        balance = config.initial_balance
        position = 0.0
        trades = []
        equity_curve = []
        drawdown_curve = []
        high_watermark = balance
        win_trades = 0
        loss_trades = 0
        total_win = 0.0
        total_loss = 0.0
        
        # 运行回测
        for i in range(len(data)):
            # 获取当前数据
            current_data = data.iloc[:i+1]
            
            # 生成信号
            signal = self.strategy.on_data(current_data, i)
            
            if signal:
                # 处理信号
                trade = await self._execute_trade(
                    signal, 
                    data.iloc[i], 
                    balance, 
                    position
                )
                
                if trade:
                    trades.append(trade)
                    balance = trade.balance
                    position = trade.position
                    
                    # 更新高水位线
                    if balance > high_watermark:
                        high_watermark = balance
                    
                    # 计算回撤
                    drawdown = (high_watermark - balance) / high_watermark * 100
                    
                    # 更新曲线
                    equity_curve.append((data.index[i], balance))
                    drawdown_curve.append((data.index[i], drawdown))
                    
                    # 更新交易统计
                    if trade.pnl > 0:
                        win_trades += 1
                        total_win += trade.pnl
                    else:
                        loss_trades += 1
                        total_loss += abs(trade.pnl)
            else:
                # 无信号时也更新曲线
                equity_curve.append((data.index[i], balance))
                drawdown = (high_watermark - balance) / high_watermark * 100
                drawdown_curve.append((data.index[i], drawdown))
        
        # 策略完成
        self.strategy.on_finish()
        
        # 计算性能指标
        total_pnl = balance - config.initial_balance
        win_rate = win_trades / len(trades) * 100 if trades else 0
        average_win = total_win / win_trades if win_trades else 0
        average_loss = total_loss / loss_trades if loss_trades else 0
        max_drawdown = max([d[1] for d in drawdown_curve]) if drawdown_curve else 0
        sharpe_ratio = self._calculate_sharpe_ratio(equity_curve)
        sortino_ratio = self._calculate_sortino_ratio(equity_curve)
        profit_factor = total_win / total_loss if total_loss > 0 else float('inf')
        
        # 创建回测结果
        result = BacktestResult(
            config=config,
            trades=trades,
            final_balance=balance,
            total_pnl=total_pnl,
            win_rate=win_rate,
            average_win=average_win,
            average_loss=average_loss,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            profit_factor=profit_factor,
            total_trades=len(trades),
            win_trades=win_trades,
            loss_trades=loss_trades,
            start_balance=config.initial_balance,
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve
        )
        
        return result
    
    async def _execute_trade(self, signal: Dict[str, Any], data: pd.Series, 
                           balance: float, position: float) -> Optional[Trade]:
        """执行交易"""
        side = signal.get("side")
        quantity = signal.get("quantity")
        
        if not side or not quantity:
            return None
        
        # 计算价格（包含滑点）
        price = data["close"]
        if side == "buy":
            price = price * (1 + self.config.slippage)
        else:
            price = price * (1 - self.config.slippage)
        
        # 计算手续费
        fee = price * quantity * self.config.fee_rate
        
        # 计算交易后余额和仓位
        if side == "buy":
            # 开多仓
            cost = price * quantity
            new_balance = balance - cost - fee
            new_position = position + quantity
        else:
            # 平仓或开空仓
            if position > 0:
                # 平仓
                proceeds = price * quantity
                new_balance = balance + proceeds - fee
                new_position = position - quantity
            else:
                # 开空仓
                proceeds = price * quantity
                new_balance = balance + proceeds - fee
                new_position = position - quantity
        
        # 计算PnL
        if position != 0:
            if side == "sell" and position > 0:
                # 平仓多仓
                pnl = (price - data["close"]) * quantity
            elif side == "buy" and position < 0:
                # 平仓空仓
                pnl = (data["close"] - price) * abs(position)
            else:
                pnl = 0.0
        else:
            pnl = 0.0
        
        # 计算累计PnL
        cumulative_pnl = new_balance - self.config.initial_balance
        
        # 创建交易记录
        trade = Trade(
            timestamp=data.name,
            symbol=self.config.symbol,
            side=side,
            quantity=quantity,
            price=price,
            fee=fee,
            balance=new_balance,
            position=new_position,
            pnl=pnl,
            cumulative_pnl=cumulative_pnl
        )
        
        return trade
    
    def _calculate_sharpe_ratio(self, equity_curve: List[Tuple[datetime, float]]) -> float:
        """计算夏普比率"""
        if len(equity_curve) < 2:
            return 0.0
        
        # 计算日收益率
        returns = []
        for i in range(1, len(equity_curve)):
            prev_balance = equity_curve[i-1][1]
            current_balance = equity_curve[i][1]
            returns.append((current_balance - prev_balance) / prev_balance)
        
        if not returns:
            return 0.0
        
        # 计算年化收益率和标准差
        avg_return = np.mean(returns) * 365
        std_return = np.std(returns) * math.sqrt(365)
        
        if std_return == 0:
            return 0.0
        
        # 夏普比率 = (年化收益率 - 无风险利率) / 年化标准差
        risk_free_rate = 0.02  # 假设无风险利率为2%
        sharpe = (avg_return - risk_free_rate) / std_return
        
        return sharpe
    
    def _calculate_sortino_ratio(self, equity_curve: List[Tuple[datetime, float]]) -> float:
        """计算索提诺比率"""
        if len(equity_curve) < 2:
            return 0.0
        
        # 计算日收益率
        returns = []
        for i in range(1, len(equity_curve)):
            prev_balance = equity_curve[i-1][1]
            current_balance = equity_curve[i][1]
            returns.append((current_balance - prev_balance) / prev_balance)
        
        if not returns:
            return 0.0
        
        # 计算年化收益率和下行标准差
        avg_return = np.mean(returns) * 365
        negative_returns = [r for r in returns if r < 0]
        
        if not negative_returns:
            return 0.0
        
        downside_std = np.std(negative_returns) * math.sqrt(365)
        
        if downside_std == 0:
            return 0.0
        
        # 索提诺比率 = (年化收益率 - 无风险利率) / 年化下行标准差
        risk_free_rate = 0.02
        sortino = (avg_return - risk_free_rate) / downside_std
        
        return sortino
    
    def generate_report(self, result: BacktestResult) -> Dict[str, Any]:
        """生成回测报告"""
        report = {
            "基本信息": {
                "策略名称": self.strategy.name if self.strategy else "多策略组合",
                "交易对": result.config.symbol,
                "回测周期": f"{result.config.start_time} 至 {result.config.end_time}",
                "初始资金": result.start_balance,
                "最终资金": result.final_balance,
                "总盈亏": result.total_pnl,
                "总收益率": f"{result.total_pnl / result.start_balance * 100:.2f}%"
            },
            "交易统计": {
                "总交易次数": result.total_trades,
                "盈利交易": result.win_trades,
                "亏损交易": result.loss_trades,
                "胜率": f"{result.win_rate:.2f}%",
                "平均盈利": result.average_win,
                "平均亏损": result.average_loss,
                "盈亏比": f"{result.average_win / result.average_loss:.2f}:1" if result.average_loss > 0 else "N/A"
            },
            "风险指标": {
                "最大回撤": f"{result.max_drawdown:.2f}%",
                "夏普比率": f"{result.sharpe_ratio:.2f}",
                "索提诺比率": f"{result.sortino_ratio:.2f}",
                "卡马比率": f"{result.calmar_ratio:.2f}",
                "盈利因子": f"{result.profit_factor:.2f}"
            }
        }
        
        return report
    
    # 多策略回测方法
    
    def add_strategy(self, strategy_name: str, strategy):
        """添加策略"""
        self.strategies[strategy_name] = strategy
    
    def add_market_data(self, symbol: str, data: pd.DataFrame):
        """添加市场数据"""
        self.market_data[symbol] = data
    
    def set_initial_balance(self, balance: float):
        """设置初始资金"""
        if self.config:
            self.config.initial_balance = balance
    
    async def run_multi_strategy_backtest(self, start_date: Optional[datetime] = None, 
                                         end_date: Optional[datetime] = None) -> BacktestResult:
        """运行多策略协同回测"""
        # 重置状态
        self._reset_state()
        
        # 获取时间范围
        all_data = []
        for data in self.market_data.values():
            all_data.append(data)
        
        if not all_data:
            return BacktestResult(
                config=BacktestConfig(symbol="MULTI", start_time=start_date or datetime.now(), 
                                     end_time=end_date or datetime.now(), initial_balance=100000),
                trades=[],
                final_balance=100000,
                total_pnl=0,
                win_rate=0,
                average_win=0,
                average_loss=0,
                max_drawdown=0,
                sharpe_ratio=0,
                sortino_ratio=0,
                profit_factor=0,
                total_trades=0,
                win_trades=0,
                loss_trades=0,
                start_balance=100000,
                equity_curve=[],
                drawdown_curve=[]
            )
        
        combined_data = pd.concat(all_data)
        combined_data = combined_data.sort_index()
        
        if start_date:
            combined_data = combined_data[combined_data.index >= start_date]
        if end_date:
            combined_data = combined_data[combined_data.index <= end_date]
        
        # 初始化回测状态
        balance = self.config.initial_balance if self.config else 100000
        portfolio = {}
        trades = []
        equity_curve = []
        drawdown_curve = []
        high_watermark = balance
        win_trades = 0
        loss_trades = 0
        total_win = 0.0
        total_loss = 0.0
        positions = {}
        
        # 运行回测
        for timestamp in combined_data.index.unique():
            # 获取当前时间点的所有市场数据
            current_data = {}
            for symbol, data in self.market_data.items():
                if timestamp in data.index:
                    current_data[symbol] = data.loc[timestamp]
            
            if not current_data:
                continue
            
            # 让每个策略生成信号
            signals = {}
            for strategy_name, strategy in self.strategies.items():
                try:
                    signal = strategy.on_data(pd.DataFrame([current_data]), 0)
                    if signal:
                        signals[strategy_name] = signal
                except Exception as e:
                    logger.error(f"策略 {strategy_name} 生成信号时出错: {e}")
            
            # 处理信号
            for strategy_name, signal in signals.items():
                symbol = signal.get("symbol")
                side = signal.get("side")
                quantity = signal.get("quantity")
                price = signal.get("price") or current_data.get(symbol, {}).get("close")
                
                if not symbol or not side or not quantity or not price:
                    continue
                
                # 执行交易
                trade = await self._execute_trade(
                    {"side": side, "quantity": quantity},
                    current_data.get(symbol),
                    balance,
                    portfolio.get(symbol, 0)
                )
                
                if trade:
                    trades.append(trade)
                    balance = trade.balance
                    portfolio[symbol] = trade.position
                    
                    # 更新高水位线
                    if balance > high_watermark:
                        high_watermark = balance
                    
                    # 计算回撤
                    drawdown = (high_watermark - balance) / high_watermark * 100
                    
                    # 更新曲线
                    equity_curve.append((timestamp, balance))
                    drawdown_curve.append((timestamp, drawdown))
                    
                    # 更新交易统计
                    if trade.pnl > 0:
                        win_trades += 1
                        total_win += trade.pnl
                    else:
                        loss_trades += 1
                        total_loss += abs(trade.pnl)
            
            # 无信号时也更新曲线
            equity_curve.append((timestamp, balance))
            drawdown = (high_watermark - balance) / high_watermark * 100
            drawdown_curve.append((timestamp, drawdown))
        
        # 计算性能指标
        total_pnl = balance - (self.config.initial_balance if self.config else 100000)
        win_rate = win_trades / len(trades) * 100 if trades else 0
        average_win = total_win / win_trades if win_trades else 0
        average_loss = total_loss / loss_trades if loss_trades else 0
        max_drawdown = max([d[1] for d in drawdown_curve]) if drawdown_curve else 0
        sharpe_ratio = self._calculate_sharpe_ratio(equity_curve)
        sortino_ratio = self._calculate_sortino_ratio(equity_curve)
        profit_factor = total_win / total_loss if total_loss > 0 else float('inf')
        calmar_ratio = total_pnl / max_drawdown if max_drawdown > 0 else 0
        
        # 创建回测结果
        result = BacktestResult(
            config=BacktestConfig(symbol="MULTI", start_time=start_date or datetime.now(), 
                                 end_time=end_date or datetime.now(), initial_balance=self.config.initial_balance if self.config else 100000),
            trades=trades,
            final_balance=balance,
            total_pnl=total_pnl,
            win_rate=win_rate,
            average_win=average_win,
            average_loss=average_loss,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            profit_factor=profit_factor,
            total_trades=len(trades),
            win_trades=win_trades,
            loss_trades=loss_trades,
            start_balance=self.config.initial_balance if self.config else 100000,
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            calmar_ratio=calmar_ratio,
            positions=positions
        )
        
        return result
    
    async def run_cross_market_arbitrage_backtest(self, symbol1: str, symbol2: str, 
                                              spread_threshold: float = 0.01, 
                                              start_date: Optional[datetime] = None, 
                                              end_date: Optional[datetime] = None) -> BacktestResult:
        """运行跨市场套利回测"""
        # 重置状态
        self._reset_state()
        
        # 获取两个市场的数据
        if symbol1 not in self.market_data or symbol2 not in self.market_data:
            return BacktestResult(
                config=BacktestConfig(symbol=f"{symbol1}/{symbol2}", start_time=start_date or datetime.now(), 
                                     end_time=end_date or datetime.now(), initial_balance=100000),
                trades=[],
                final_balance=100000,
                total_pnl=0,
                win_rate=0,
                average_win=0,
                average_loss=0,
                max_drawdown=0,
                sharpe_ratio=0,
                sortino_ratio=0,
                profit_factor=0,
                total_trades=0,
                win_trades=0,
                loss_trades=0,
                start_balance=100000,
                equity_curve=[],
                drawdown_curve=[]
            )
        
        data1 = self.market_data[symbol1]
        data2 = self.market_data[symbol2]
        
        # 对齐时间索引
        combined_index = data1.index.intersection(data2.index)
        data1 = data1.loc[combined_index]
        data2 = data2.loc[combined_index]
        
        if start_date:
            data1 = data1[data1.index >= start_date]
            data2 = data2[data2.index >= start_date]
        if end_date:
            data1 = data1[data1.index <= end_date]
            data2 = data2[data2.index <= end_date]
        
        # 计算价差
        spread = data1['close'] - data2['close']
        spread_mean = spread.mean()
        spread_std = spread.std()
        
        # 初始化回测状态
        balance = self.config.initial_balance if self.config else 100000
        portfolio = {}
        trades = []
        equity_curve = []
        drawdown_curve = []
        high_watermark = balance
        win_trades = 0
        loss_trades = 0
        total_win = 0.0
        total_loss = 0.0
        
        # 运行套利策略
        position = 0  # 0: 无仓位, 1: 做多symbol1做空symbol2, -1: 做空symbol1做多功能2
        entry_price = 0.0
        
        for i, timestamp in enumerate(data1.index):
            current_spread = spread.iloc[i]
            price1 = data1.loc[timestamp, 'close']
            price2 = data2.loc[timestamp, 'close']
            
            # 套利信号
            if position == 0:
                # 价差偏离过大，开仓
                if current_spread > spread_mean + spread_threshold * spread_std:
                    # 做空symbol1，做多功能2
                    position = -1
                    entry_price = current_spread
                    
                    # 执行交易
                    trade1 = await self._execute_trade(
                        {"side": "sell", "quantity": balance * 0.5 / price1},
                        data1.loc[timestamp],
                        balance,
                        portfolio.get(symbol1, 0)
                    )
                    if trade1:
                        trades.append(trade1)
                        balance = trade1.balance
                        portfolio[symbol1] = trade1.position
                    
                    trade2 = await self._execute_trade(
                        {"side": "buy", "quantity": balance * 0.5 / price2},
                        data2.loc[timestamp],
                        balance,
                        portfolio.get(symbol2, 0)
                    )
                    if trade2:
                        trades.append(trade2)
                        balance = trade2.balance
                        portfolio[symbol2] = trade2.position
                        
                elif current_spread < spread_mean - spread_threshold * spread_std:
                    # 做多symbol1，做空symbol2
                    position = 1
                    entry_price = current_spread
                    
                    # 执行交易
                    trade1 = await self._execute_trade(
                        {"side": "buy", "quantity": balance * 0.5 / price1},
                        data1.loc[timestamp],
                        balance,
                        portfolio.get(symbol1, 0)
                    )
                    if trade1:
                        trades.append(trade1)
                        balance = trade1.balance
                        portfolio[symbol1] = trade1.position
                    
                    trade2 = await self._execute_trade(
                        {"side": "sell", "quantity": balance * 0.5 / price2},
                        data2.loc[timestamp],
                        balance,
                        portfolio.get(symbol2, 0)
                    )
                    if trade2:
                        trades.append(trade2)
                        balance = trade2.balance
                        portfolio[symbol2] = trade2.position
            else:
                # 价差回归，平仓
                if (position == 1 and current_spread >= spread_mean) or \
                   (position == -1 and current_spread <= spread_mean):
                    # 平仓
                    trade1 = await self._execute_trade(
                        {"side": "sell" if position == 1 else "buy", "quantity": portfolio.get(symbol1, 0)},
                        data1.loc[timestamp],
                        balance,
                        portfolio.get(symbol1, 0)
                    )
                    if trade1:
                        trades.append(trade1)
                        balance = trade1.balance
                        portfolio[symbol1] = trade1.position
                    
                    trade2 = await self._execute_trade(
                        {"side": "buy" if position == 1 else "sell", "quantity": portfolio.get(symbol2, 0)},
                        data2.loc[timestamp],
                        balance,
                        portfolio.get(symbol2, 0)
                    )
                    if trade2:
                        trades.append(trade2)
                        balance = trade2.balance
                        portfolio[symbol2] = trade2.position
                    
                    position = 0
            
            # 更新高水位线
            if balance > high_watermark:
                high_watermark = balance
            
            # 计算回撤
            drawdown = (high_watermark - balance) / high_watermark * 100
            
            # 更新曲线
            equity_curve.append((timestamp, balance))
            drawdown_curve.append((timestamp, drawdown))
            
            # 更新交易统计
            if trades:
                last_trade = trades[-1]
                if last_trade.pnl > 0:
                    win_trades += 1
                    total_win += last_trade.pnl
                else:
                    loss_trades += 1
                    total_loss += abs(last_trade.pnl)
        
        # 计算性能指标
        total_pnl = balance - (self.config.initial_balance if self.config else 100000)
        win_rate = win_trades / len(trades) * 100 if trades else 0
        average_win = total_win / win_trades if win_trades else 0
        average_loss = total_loss / loss_trades if loss_trades else 0
        max_drawdown = max([d[1] for d in drawdown_curve]) if drawdown_curve else 0
        sharpe_ratio = self._calculate_sharpe_ratio(equity_curve)
        sortino_ratio = self._calculate_sortino_ratio(equity_curve)
        profit_factor = total_win / total_loss if total_loss > 0 else float('inf')
        calmar_ratio = total_pnl / max_drawdown if max_drawdown > 0 else 0
        
        # 创建回测结果
        result = BacktestResult(
            config=BacktestConfig(symbol=f"{symbol1}/{symbol2}", start_time=start_date or datetime.now(), 
                                 end_time=end_date or datetime.now(), initial_balance=self.config.initial_balance if self.config else 100000),
            trades=trades,
            final_balance=balance,
            total_pnl=total_pnl,
            win_rate=win_rate,
            average_win=average_win,
            average_loss=average_loss,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            profit_factor=profit_factor,
            total_trades=len(trades),
            win_trades=win_trades,
            loss_trades=loss_trades,
            start_balance=self.config.initial_balance if self.config else 100000,
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            calmar_ratio=calmar_ratio
        )
        
        return result
    
    def _reset_state(self):
        """重置回测状态"""
        self.portfolio = {}
        self.positions = {}
    
    def get_equity_curve(self) -> pd.Series:
        """获取资产曲线"""
        if not self.strategy or not hasattr(self, 'equity_curve') or not self.equity_curve:
            return pd.Series()
        equity_df = pd.DataFrame(self.equity_curve, columns=['timestamp', 'equity'])
        equity_df.set_index('timestamp', inplace=True)
        return equity_df['equity']
    
    def get_trades(self) -> List[Trade]:
        """获取交易记录"""
        if not self.strategy or not hasattr(self, 'trades'):
            return []
        return self.trades
    
    async def load_historical_data(self, symbol: str, start_time: datetime, 
                                 end_time: datetime, time_frame: str) -> pd.DataFrame:
        """加载历史数据"""
        # 这里应该从数据源加载数据，现在返回模拟数据
        # 实际实现应该从交易所API或数据库加载
        
        # 生成模拟数据
        timestamps = pd.date_range(start=start_time, end=end_time, freq=time_frame)
        data = {
            "open": np.random.normal(50000, 1000, len(timestamps)),
            "high": np.random.normal(50500, 1000, len(timestamps)),
            "low": np.random.normal(49500, 1000, len(timestamps)),
            "close": np.random.normal(50000, 1000, len(timestamps)),
            "volume": np.random.normal(10000, 1000, len(timestamps))
        }
        
        df = pd.DataFrame(data, index=timestamps)
        return df