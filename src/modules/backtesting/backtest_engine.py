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
                "策略名称": self.strategy.name,
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
                "盈利因子": f"{result.profit_factor:.2f}"
            }
        }
        
        return report
    
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