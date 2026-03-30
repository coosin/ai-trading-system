import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class BacktestResult:
    """回测结果"""
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    profit_factor: float
    calmar_ratio: float
    sortino_ratio: float
    beta: float = 0.0
    alpha: float = 0.0
    drawdown_duration: int = 0
    trades: List[Dict[str, Any]] = field(default_factory=list)
    equity_curve: pd.Series = None
    positions: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

@dataclass
class MarketData:
    """市场数据"""
    symbol: str
    data: pd.DataFrame
    timezone: str = "UTC"

class EnhancedBacktester:
    def __init__(self):
        self.strategies = {}
        self.market_data = {}
        self.initial_balance = 100000.0
        self.current_balance = self.initial_balance
        self.portfolio = {}
        self.trades = []
        self.equity_curve = []
        self.positions = {}
    
    def add_strategy(self, strategy_name: str, strategy):
        """添加策略"""
        self.strategies[strategy_name] = strategy
    
    def add_market_data(self, symbol: str, data: pd.DataFrame):
        """添加市场数据"""
        self.market_data[symbol] = MarketData(symbol=symbol, data=data)
    
    def set_initial_balance(self, balance: float):
        """设置初始资金"""
        self.initial_balance = balance
        self.current_balance = balance
    
    def run_multi_strategy_backtest(self, start_date: Optional[datetime] = None, 
                                   end_date: Optional[datetime] = None) -> BacktestResult:
        """运行多策略协同回测"""
        # 重置状态
        self._reset_state()
        
        # 获取时间范围
        all_data = []
        for market in self.market_data.values():
            all_data.append(market.data)
        
        if not all_data:
            return BacktestResult(
                total_return=0.0, sharpe_ratio=0.0, max_drawdown=0.0,
                win_rate=0.0, total_trades=0, profit_factor=0.0,
                calmar_ratio=0.0, sortino_ratio=0.0
            )
        
        combined_data = pd.concat(all_data)
        combined_data = combined_data.sort_index()
        
        if start_date:
            combined_data = combined_data[combined_data.index >= start_date]
        if end_date:
            combined_data = combined_data[combined_data.index <= end_date]
        
        # 按时间顺序处理数据
        for timestamp in combined_data.index.unique():
            # 获取当前时间点的所有市场数据
            current_data = {}
            for symbol, market in self.market_data.items():
                if timestamp in market.data.index:
                    current_data[symbol] = market.data.loc[timestamp]
            
            if not current_data:
                continue
            
            # 让每个策略生成信号
            signals = {}
            for strategy_name, strategy in self.strategies.items():
                try:
                    signal = strategy.generate_signal(current_data)
                    if signal:
                        signals[strategy_name] = signal
                except Exception as e:
                    print(f"策略 {strategy_name} 生成信号时出错: {e}")
            
            # 处理信号
            self._process_signals(signals, current_data, timestamp)
            
            # 更新资产曲线
            self._update_equity_curve(timestamp, current_data)
        
        # 计算回测结果
        return self._calculate_results()
    
    def run_cross_market_arbitrage_backtest(self, symbol1: str, symbol2: str, 
                                          spread_threshold: float = 0.01, 
                                          start_date: Optional[datetime] = None, 
                                          end_date: Optional[datetime] = None) -> BacktestResult:
        """运行跨市场套利回测"""
        # 重置状态
        self._reset_state()
        
        # 获取两个市场的数据
        if symbol1 not in self.market_data or symbol2 not in self.market_data:
            return BacktestResult(
                total_return=0.0, sharpe_ratio=0.0, max_drawdown=0.0,
                win_rate=0.0, total_trades=0, profit_factor=0.0,
                calmar_ratio=0.0, sortino_ratio=0.0
            )
        
        data1 = self.market_data[symbol1].data
        data2 = self.market_data[symbol2].data
        
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
                    self._execute_trade(
                        strategy_name="arbitrage",
                        symbol=symbol1,
                        side="sell",
                        price=price1,
                        quantity=self.current_balance * 0.5 / price1,
                        timestamp=timestamp
                    )
                    self._execute_trade(
                        strategy_name="arbitrage",
                        symbol=symbol2,
                        side="buy",
                        price=price2,
                        quantity=self.current_balance * 0.5 / price2,
                        timestamp=timestamp
                    )
                elif current_spread < spread_mean - spread_threshold * spread_std:
                    # 做多symbol1，做空symbol2
                    position = 1
                    entry_price = current_spread
                    self._execute_trade(
                        strategy_name="arbitrage",
                        symbol=symbol1,
                        side="buy",
                        price=price1,
                        quantity=self.current_balance * 0.5 / price1,
                        timestamp=timestamp
                    )
                    self._execute_trade(
                        strategy_name="arbitrage",
                        symbol=symbol2,
                        side="sell",
                        price=price2,
                        quantity=self.current_balance * 0.5 / price2,
                        timestamp=timestamp
                    )
            else:
                # 价差回归，平仓
                if (position == 1 and current_spread >= spread_mean) or \
                   (position == -1 and current_spread <= spread_mean):
                    # 平仓
                    self._execute_trade(
                        strategy_name="arbitrage",
                        symbol=symbol1,
                        side="sell" if position == 1 else "buy",
                        price=price1,
                        quantity=self.portfolio.get(symbol1, 0),
                        timestamp=timestamp
                    )
                    self._execute_trade(
                        strategy_name="arbitrage",
                        symbol=symbol2,
                        side="buy" if position == 1 else "sell",
                        price=price2,
                        quantity=self.portfolio.get(symbol2, 0),
                        timestamp=timestamp
                    )
                    position = 0
            
            # 更新资产曲线
            current_data = {
                symbol1: data1.loc[timestamp],
                symbol2: data2.loc[timestamp]
            }
            self._update_equity_curve(timestamp, current_data)
        
        # 计算回测结果
        return self._calculate_results()
    
    def _reset_state(self):
        """重置回测状态"""
        self.current_balance = self.initial_balance
        self.portfolio = {}
        self.trades = []
        self.equity_curve = []
        self.positions = {}
    
    def _process_signals(self, signals: Dict[str, Dict[str, Any]], 
                        current_data: Dict[str, pd.Series], 
                        timestamp: datetime):
        """处理信号"""
        for strategy_name, signal in signals.items():
            symbol = signal.get('symbol')
            side = signal.get('side')
            quantity = signal.get('quantity')
            price = signal.get('price') or current_data.get(symbol, {}).get('close')
            
            if not symbol or not side or not quantity or not price:
                continue
            
            # 执行交易
            self._execute_trade(
                strategy_name=strategy_name,
                symbol=symbol,
                side=side,
                price=price,
                quantity=quantity,
                timestamp=timestamp
            )
    
    def _execute_trade(self, strategy_name: str, symbol: str, side: str, 
                      price: float, quantity: float, timestamp: datetime):
        """执行交易"""
        # 计算交易成本
        trade_cost = price * quantity * 0.001  # 假设0.1%的交易成本
        
        if side == "buy":
            # 买入
            cost = price * quantity + trade_cost
            if cost > self.current_balance:
                # 资金不足，调整交易量
                quantity = (self.current_balance - trade_cost) / price
                if quantity <= 0:
                    return
                cost = price * quantity + trade_cost
            
            self.current_balance -= cost
            self.portfolio[symbol] = self.portfolio.get(symbol, 0) + quantity
        elif side == "sell":
            # 卖出
            if self.portfolio.get(symbol, 0) < quantity:
                # 持仓不足，调整交易量
                quantity = self.portfolio.get(symbol, 0)
                if quantity <= 0:
                    return
            
            revenue = price * quantity - trade_cost
            self.current_balance += revenue
            self.portfolio[symbol] = self.portfolio.get(symbol, 0) - quantity
        
        # 记录交易
        trade = {
            'timestamp': timestamp,
            'strategy': strategy_name,
            'symbol': symbol,
            'side': side,
            'price': price,
            'quantity': quantity,
            'cost': trade_cost,
            'balance': self.current_balance
        }
        self.trades.append(trade)
        
        # 记录持仓
        if symbol not in self.positions:
            self.positions[symbol] = []
        self.positions[symbol].append({
            'timestamp': timestamp,
            'quantity': self.portfolio.get(symbol, 0),
            'price': price
        })
    
    def _update_equity_curve(self, timestamp: datetime, 
                            current_data: Dict[str, pd.Series]):
        """更新资产曲线"""
        # 计算当前总资产
        total_equity = self.current_balance
        for symbol, quantity in self.portfolio.items():
            if symbol in current_data:
                price = current_data[symbol].get('close')
                if price:
                    total_equity += quantity * price
        
        self.equity_curve.append({
            'timestamp': timestamp,
            'equity': total_equity
        })
    
    def _calculate_results(self) -> BacktestResult:
        """计算回测结果"""
        if not self.equity_curve:
            return BacktestResult(
                total_return=0.0, sharpe_ratio=0.0, max_drawdown=0.0,
                win_rate=0.0, total_trades=0, profit_factor=0.0,
                calmar_ratio=0.0, sortino_ratio=0.0
            )
        
        # 计算资产曲线
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df.set_index('timestamp', inplace=True)
        equity_series = equity_df['equity']
        
        # 计算总收益率
        total_return = (equity_series.iloc[-1] - self.initial_balance) / self.initial_balance
        
        # 计算日收益率
        daily_returns = equity_series.pct_change().dropna()
        
        # 计算夏普比率（假设无风险利率为0）
        if daily_returns.std() > 0:
            sharpe_ratio = daily_returns.mean() / daily_returns.std() * np.sqrt(252)
        else:
            sharpe_ratio = 0.0
        
        # 计算最大回撤
        cumulative_returns = (1 + daily_returns).cumprod()
        running_max = cumulative_returns.cummax()
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # 计算胜率
        win_trades = len([t for t in self.trades if 
                        (t['side'] == 'buy' and t['balance'] > self.trades[max(0, self.trades.index(t)-1)]['balance']) or 
                        (t['side'] == 'sell' and t['balance'] > self.trades[max(0, self.trades.index(t)-1)]['balance'])])
        total_trades = len(self.trades)
        win_rate = win_trades / total_trades if total_trades > 0 else 0.0
        
        # 计算盈利因子
        profitable_trades = [t for t in self.trades if 
                           (t['side'] == 'buy' and t['balance'] > self.trades[max(0, self.trades.index(t)-1)]['balance']) or 
                           (t['side'] == 'sell' and t['balance'] > self.trades[max(0, self.trades.index(t)-1)]['balance'])]
        losing_trades = [t for t in self.trades if t not in profitable_trades]
        total_profit = sum(t['balance'] - self.trades[max(0, self.trades.index(t)-1)]['balance'] for t in profitable_trades)
        total_loss = sum(self.trades[max(0, self.trades.index(t)-1)]['balance'] - t['balance'] for t in losing_trades)
        profit_factor = total_profit / total_loss if total_loss > 0 else 0.0
        
        # 计算卡马比率
        calmar_ratio = total_return / abs(max_drawdown) if max_drawdown < 0 else 0.0
        
        # 计算索提诺比率
        negative_returns = daily_returns[daily_returns < 0]
        if negative_returns.std() > 0:
            sortino_ratio = daily_returns.mean() / negative_returns.std() * np.sqrt(252)
        else:
            sortino_ratio = 0.0
        
        return BacktestResult(
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            total_trades=total_trades,
            profit_factor=profit_factor,
            calmar_ratio=calmar_ratio,
            sortino_ratio=sortino_ratio,
            trades=self.trades,
            equity_curve=equity_series,
            positions=self.positions
        )
    
    def get_equity_curve(self) -> pd.Series:
        """获取资产曲线"""
        if not self.equity_curve:
            return pd.Series()
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df.set_index('timestamp', inplace=True)
        return equity_df['equity']
    
    def get_trades(self) -> List[Dict[str, Any]]:
        """获取交易记录"""
        return self.trades
    
    def get_positions(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取持仓记录"""
        return self.positions
