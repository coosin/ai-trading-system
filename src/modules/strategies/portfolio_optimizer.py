import numpy as np
import pandas as pd
from scipy.optimize import minimize
from typing import Any, List, Dict

class PortfolioOptimizer:
    def __init__(self):
        self.strategies = {}

    def seed_from_strategy_manager(self, strategy_manager: Any) -> int:
        """从 StrategyManager 策略池预置优化条目（无历史时用占位收益/波动率，便于组合 API 可用）。"""
        if strategy_manager is None:
            return 0
        configs = getattr(strategy_manager, "strategy_configs", None) or {}
        metrics = getattr(strategy_manager, "performance_metrics", None) or {}
        added = 0
        for sid, cfg in configs.items():
            name = getattr(cfg, "name", None) or sid
            if name in self.strategies:
                continue
            vol = 0.25
            ann = 0.08
            perf = metrics.get(sid)
            if perf is not None:
                try:
                    dd = float(getattr(perf, "max_drawdown", 0.0) or 0.0)
                    vol = max(min(abs(dd) * 1.2, 0.8), 0.05)
                    sh = float(getattr(perf, "sharpe_ratio", 0.0) or 0.0)
                    ann = max(min(0.04 + sh * 0.03, 0.5), -0.2)
                except Exception:
                    pass
            self.add_strategy(str(name), ann, vol, {})
            added += 1
        return added
    
    def add_strategy(self, strategy_name: str, returns: pd.Series or float, volatility: float, correlation: Dict[str, float] = None):
        """添加策略到组合中
        
        Args:
            strategy_name: 策略名称
            returns: 策略收益率序列或年化收益率
            volatility: 策略波动率
            correlation: 与其他策略的相关性字典 {strategy_name: correlation}
        """
        if correlation is None:
            correlation = {}
        
        # 如果 returns 是数值，直接使用；如果是 Series，计算年化收益
        if isinstance(returns, (int, float)):
            annual_return = returns
        else:
            annual_return = returns.mean() * 252 if hasattr(returns, 'mean') else returns
            
        self.strategies[strategy_name] = {
            'returns': returns,
            'annual_return': annual_return,
            'volatility': volatility,
            'correlation': correlation
        }
    
    def calculate_returns(self, weights: Dict[str, float]) -> float:
        """计算组合的预期收益率"""
        total_return = 0.0
        for strategy_name, weight in weights.items():
            strategy = self.strategies[strategy_name]
            total_return += weight * strategy['annual_return']
        return total_return
    
    def calculate_volatility(self, weights: Dict[str, float]) -> float:
        """计算组合的波动率"""
        if len(self.strategies) == 1:
            strategy_name = list(weights.keys())[0]
            return weights[strategy_name] * self.strategies[strategy_name]['volatility']
        
        # 构建协方差矩阵
        strategy_names = list(weights.keys())
        n = len(strategy_names)
        cov_matrix = np.zeros((n, n))
        
        for i, name_i in enumerate(strategy_names):
            for j, name_j in enumerate(strategy_names):
                if i == j:
                    cov_matrix[i, j] = self.strategies[name_i]['volatility'] ** 2
                else:
                    corr = self.strategies[name_i]['correlation'].get(name_j, 0.0)
                    cov_matrix[i, j] = corr * self.strategies[name_i]['volatility'] * self.strategies[name_j]['volatility']
        
        # 计算组合波动率
        weights_array = np.array([weights[name] for name in strategy_names])
        portfolio_variance = np.dot(weights_array.T, np.dot(cov_matrix, weights_array))
        return np.sqrt(portfolio_variance)
    
    def calculate_sharpe_ratio(self, weights: Dict[str, float], risk_free_rate: float = 0.0) -> float:
        """计算组合的夏普比率"""
        portfolio_return = self.calculate_returns(weights)
        portfolio_volatility = self.calculate_volatility(weights)
        if portfolio_volatility == 0:
            return 0.0
        return (portfolio_return - risk_free_rate) / portfolio_volatility
    
    def mean_variance_optimization(self, target_return: float = None, risk_free_rate: float = 0.0) -> Dict[str, float]:
        """均值方差优化"""
        strategy_names = list(self.strategies.keys())
        n = len(strategy_names)
        
        # 目标函数：最小化波动率
        def objective(weights):
            weights_dict = dict(zip(strategy_names, weights))
            return self.calculate_volatility(weights_dict)
        
        # 约束条件
        constraints = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1.0}  # 权重和为1
        ]
        
        if target_return is not None:
            def return_constraint(weights):
                weights_dict = dict(zip(strategy_names, weights))
                return self.calculate_returns(weights_dict) - target_return
            constraints.append({'type': 'eq', 'fun': return_constraint})
        
        # 边界条件：权重在0-1之间
        bounds = [(0, 1) for _ in range(n)]
        
        # 初始权重：等权重
        initial_weights = np.ones(n) / n
        
        # 优化
        result = minimize(objective, initial_weights, method='SLSQP', bounds=bounds, constraints=constraints)
        
        if result.success:
            return dict(zip(strategy_names, result.x))
        else:
            raise Exception(f"优化失败: {result.message}")
    
    def risk_parity_optimization(self) -> Dict[str, float]:
        """风险平价优化"""
        strategy_names = list(self.strategies.keys())
        n = len(strategy_names)
        
        # 目标函数：最小化风险贡献的差异
        def objective(weights):
            weights_dict = dict(zip(strategy_names, weights))
            portfolio_vol = self.calculate_volatility(weights_dict)
            
            if portfolio_vol == 0:
                return 0.0
            
            # 计算每个策略的风险贡献
            risk_contributions = []
            for i, name_i in enumerate(strategy_names):
                # 计算边际风险贡献
                weights_array = np.array([weights_dict[name] for name in strategy_names])
                strategy = self.strategies[name_i]
                
                # 构建协方差矩阵
                cov_matrix = np.zeros((n, n))
                for j, name_j in enumerate(strategy_names):
                    if i == j:
                        cov_matrix[i, j] = strategy['volatility'] ** 2
                    else:
                        corr = strategy['correlation'].get(name_j, 0.0)
                        cov_matrix[i, j] = corr * strategy['volatility'] * self.strategies[name_j]['volatility']
                
                mrc = np.dot(cov_matrix, weights_array)[i] / portfolio_vol
                risk_contribution = weights[i] * mrc
                risk_contributions.append(risk_contribution)
            
            # 计算风险贡献的标准差
            return np.std(risk_contributions)
        
        # 约束条件
        constraints = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1.0}  # 权重和为1
        ]
        
        # 边界条件：权重在0-1之间
        bounds = [(0, 1) for _ in range(n)]
        
        # 初始权重：等权重
        initial_weights = np.ones(n) / n
        
        # 优化
        result = minimize(objective, initial_weights, method='SLSQP', bounds=bounds, constraints=constraints)
        
        if result.success:
            return dict(zip(strategy_names, result.x))
        else:
            raise Exception(f"优化失败: {result.message}")
    
    def minimum_variance_portfolio(self) -> Dict[str, float]:
        """最小方差组合"""
        return self.mean_variance_optimization()
    
    def maximum_sharpe_ratio_portfolio(self, risk_free_rate: float = 0.0) -> Dict[str, float]:
        """最大夏普比率组合"""
        strategy_names = list(self.strategies.keys())
        n = len(strategy_names)
        
        # 目标函数：最大化夏普比率（最小化负的夏普比率）
        def objective(weights):
            weights_dict = dict(zip(strategy_names, weights))
            return -self.calculate_sharpe_ratio(weights_dict, risk_free_rate)
        
        # 约束条件
        constraints = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1.0}  # 权重和为1
        ]
        
        # 边界条件：权重在0-1之间
        bounds = [(0, 1) for _ in range(n)]
        
        # 初始权重：等权重
        initial_weights = np.ones(n) / n
        
        # 优化
        result = minimize(objective, initial_weights, method='SLSQP', bounds=bounds, constraints=constraints)
        
        if result.success:
            return dict(zip(strategy_names, result.x))
        else:
            raise Exception(f"优化失败: {result.message}")
    
    def efficient_frontier(self, num_points: int = 100) -> pd.DataFrame:
        """生成有效前沿"""
        returns = []
        volatilities = []
        weights_list = []
        
        # 计算最小方差组合
        min_var_weights = self.minimum_variance_portfolio()
        min_var_return = self.calculate_returns(min_var_weights)
        min_var_vol = self.calculate_volatility(min_var_weights)
        
        # 计算最大夏普比率组合
        max_sharpe_weights = self.maximum_sharpe_ratio_portfolio()
        max_sharpe_return = self.calculate_returns(max_sharpe_weights)
        max_sharpe_vol = self.calculate_volatility(max_sharpe_weights)
        
        # 生成有效前沿上的点
        return_range = np.linspace(min_var_return, max_sharpe_return * 1.5, num_points)
        
        for target_return in return_range:
            try:
                weights = self.mean_variance_optimization(target_return=target_return)
                portfolio_return = self.calculate_returns(weights)
                portfolio_vol = self.calculate_volatility(weights)
                returns.append(portfolio_return)
                volatilities.append(portfolio_vol)
                weights_list.append(weights)
            except:
                continue
        
        # 创建有效前沿数据框
        frontier = pd.DataFrame({
            'return': returns,
            'volatility': volatilities
        })
        
        # 添加权重信息
        for strategy_name in self.strategies.keys():
            frontier[strategy_name] = [w.get(strategy_name, 0.0) for w in weights_list]
        
        return frontier
