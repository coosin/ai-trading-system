import numpy as np
import pandas as pd
from scipy import stats
import math

class StrategyEvaluator:
    def __init__(self, strategy_name):
        self.strategy_name = strategy_name
        self.returns = []
        self.trades = []
    
    def add_trade(self, trade):
        """添加交易记录"""
        self.trades.append(trade)
        if 'pnl' in trade:
            self.returns.append(trade['pnl'])
    
    def add_returns(self, returns):
        """添加收益数据"""
        self.returns.extend(returns)
    
    def calculate_total_return(self):
        """计算总收益"""
        return sum(self.returns)
    
    def calculate_annual_return(self, trading_days=252):
        """计算年化收益"""
        if not self.returns:
            return 0
        total_return = self.calculate_total_return()
        period = len(self.returns)
        if period == 0:
            return 0
        return (1 + total_return) ** (trading_days / period) - 1
    
    def calculate_sharpe_ratio(self, risk_free_rate=0.0, trading_days=252):
        """计算夏普比率"""
        if not self.returns:
            return 0
        returns = np.array(self.returns)
        excess_returns = returns - risk_free_rate / trading_days
        return np.sqrt(trading_days) * excess_returns.mean() / excess_returns.std() if excess_returns.std() > 0 else 0
    
    def calculate_sortino_ratio(self, risk_free_rate=0.0, trading_days=252):
        """计算索提诺比率"""
        if not self.returns:
            return 0
        returns = np.array(self.returns)
        excess_returns = returns - risk_free_rate / trading_days
        downside_returns = excess_returns[excess_returns < 0]
        downside_std = downside_returns.std() if len(downside_returns) > 0 else 1
        return np.sqrt(trading_days) * excess_returns.mean() / downside_std
    
    def calculate_max_drawdown(self, returns=None):
        """计算最大回撤"""
        if returns is None:
            returns = self.returns
        if not returns:
            return 0
        cumulative_returns = np.cumsum(returns)
        peak = cumulative_returns[0]
        max_drawdown = 0
        for r in cumulative_returns:
            if r > peak:
                peak = r
            drawdown = (peak - r) / peak if peak > 0 else 0
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        return max_drawdown
    
    def calculate_calmar_ratio(self, trading_days=252):
        """计算卡玛比率"""
        max_drawdown = self.calculate_max_drawdown()
        if max_drawdown == 0:
            return float('inf')
        annual_return = self.calculate_annual_return(trading_days)
        return annual_return / max_drawdown
    
    def calculate_win_rate(self, returns=None):
        """计算胜率"""
        if returns is None:
            returns = self.returns
        if not returns:
            return 0
        winning_trades = [r for r in returns if r > 0]
        return len(winning_trades) / len(returns)
    
    def calculate_profit_factor(self, returns=None):
        """计算盈利因子"""
        if returns is None:
            returns = self.returns
        if not returns:
            return 0
        total_profit = sum(r for r in returns if r > 0)
        total_loss = abs(sum(r for r in returns if r < 0))
        return total_profit / total_loss if total_loss > 0 else float('inf')
    
    def calculate_avg_win_loss_ratio(self):
        """计算平均盈亏比"""
        if not self.returns:
            return 0
        winning_trades = [r for r in self.returns if r > 0]
        losing_trades = [abs(r) for r in self.returns if r < 0]
        avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(losing_trades) / len(losing_trades) if losing_trades else 1
        return avg_win / avg_loss
    
    def calculate_omega_ratio(self, threshold=0):
        """计算欧米茄比率"""
        if not self.returns:
            return 0
        returns = np.array(self.returns)
        excess_returns = returns - threshold
        positive_excess = excess_returns[excess_returns > 0].sum()
        negative_excess = abs(excess_returns[excess_returns < 0].sum())
        return positive_excess / negative_excess if negative_excess > 0 else float('inf')
    
    def calculate_alpha_beta(self, market_returns):
        """计算Alpha和Beta"""
        if not self.returns or not market_returns:
            return 0, 0
        returns = np.array(self.returns)
        market_returns = np.array(market_returns)
        if len(returns) != len(market_returns):
            min_len = min(len(returns), len(market_returns))
            returns = returns[:min_len]
            market_returns = market_returns[:min_len]
        beta, alpha, r_value, p_value, std_err = stats.linregress(market_returns, returns)
        return alpha, beta
    
    def calculate_information_ratio(self, benchmark_returns):
        """计算信息比率"""
        if not self.returns or not benchmark_returns:
            return 0
        returns = np.array(self.returns)
        benchmark_returns = np.array(benchmark_returns)
        if len(returns) != len(benchmark_returns):
            min_len = min(len(returns), len(benchmark_returns))
            returns = returns[:min_len]
            benchmark_returns = benchmark_returns[:min_len]
        active_returns = returns - benchmark_returns
        return active_returns.mean() / active_returns.std() if active_returns.std() > 0 else 0
    
    def calculate_kurtosis(self):
        """计算峰度"""
        if not self.returns:
            return 0
        return stats.kurtosis(self.returns)
    
    def calculate_skewness(self):
        """计算偏度"""
        if not self.returns:
            return 0
        return stats.skew(self.returns)
    
    def get_evaluation_report(self, market_returns=None, benchmark_returns=None):
        """获取完整评估报告"""
        report = {
            'strategy_name': self.strategy_name,
            'total_trades': len(self.trades),
            'total_return': self.calculate_total_return(),
            'annual_return': self.calculate_annual_return(),
            'sharpe_ratio': self.calculate_sharpe_ratio(),
            'sortino_ratio': self.calculate_sortino_ratio(),
            'max_drawdown': self.calculate_max_drawdown(),
            'calmar_ratio': self.calculate_calmar_ratio(),
            'win_rate': self.calculate_win_rate(),
            'profit_factor': self.calculate_profit_factor(),
            'avg_win_loss_ratio': self.calculate_avg_win_loss_ratio(),
            'omega_ratio': self.calculate_omega_ratio(),
            'kurtosis': self.calculate_kurtosis(),
            'skewness': self.calculate_skewness()
        }
        if market_returns:
            alpha, beta = self.calculate_alpha_beta(market_returns)
            report['alpha'] = alpha
            report['beta'] = beta
        if benchmark_returns:
            report['information_ratio'] = self.calculate_information_ratio(benchmark_returns)
        return report
    
    def calculate_var(self, confidence_level=0.05, returns=None):
        """计算风险价值 (VaR)
        
        Args:
            confidence_level: 置信水平，默认 0.05 (95% VaR)
            returns: 收益序列，默认使用 self.returns
        
        Returns:
            VaR 值
        """
        if returns is None:
            returns = self.returns
        if not returns:
            return 0
        returns_array = np.array(returns)
        return np.percentile(returns_array, confidence_level * 100)
    
    def calculate_cvar(self, confidence_level=0.05, returns=None):
        """计算条件风险价值 (CVaR/Expected Shortfall)
        
        Args:
            confidence_level: 置信水平，默认 0.05 (95% CVaR)
            returns: 收益序列，默认使用 self.returns
        
        Returns:
            CVaR 值
        """
        if returns is None:
            returns = self.returns
        if not returns:
            return 0
        returns_array = np.array(returns)
        var = np.percentile(returns_array, confidence_level * 100)
        return returns_array[returns_array <= var].mean()
    
    def get_risk_metrics(self):
        """获取风险指标"""
        returns = np.array(self.returns)
        return {
            'volatility': returns.std() * math.sqrt(252),
            'value_at_risk': self.calculate_var(),
            'conditional_value_at_risk': self.calculate_cvar(),
            'max_drawdown': self.calculate_max_drawdown()
        }
    
    def get_performance_metrics(self):
        """获取性能指标"""
        return {
            'total_return': self.calculate_total_return(),
            'annual_return': self.calculate_annual_return(),
            'sharpe_ratio': self.calculate_sharpe_ratio(),
            'sortino_ratio': self.calculate_sortino_ratio(),
            'calmar_ratio': self.calculate_calmar_ratio(),
            'information_ratio': self.calculate_information_ratio(self.returns),
            'omega_ratio': self.calculate_omega_ratio()
        }
    
    def get_trade_metrics(self):
        """获取交易指标"""
        return {
            'total_trades': len(self.trades),
            'win_rate': self.calculate_win_rate(),
            'profit_factor': self.calculate_profit_factor(),
            'avg_win_loss_ratio': self.calculate_avg_win_loss_ratio(),
            'avg_trade_size': sum(abs(r) for r in self.returns) / len(self.returns) if self.returns else 0
        }