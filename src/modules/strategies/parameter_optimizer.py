import numpy as np
import pandas as pd
from scipy.optimize import minimize, differential_evolution
from bayes_opt import BayesianOptimization
from typing import Dict, Any, List, Callable, Tuple
import random

class ParameterOptimizer:
    def __init__(self):
        self.strategy = None
        self.optimization_history = []
    
    def set_strategy(self, strategy):
        """设置要优化的策略"""
        self.strategy = strategy
    
    def evaluate_strategy(self, params: Dict[str, float], backtest_data: pd.DataFrame) -> float:
        """评估策略性能
        
        Args:
            params: 策略参数
            backtest_data: 回测数据
            
        Returns:
            策略性能指标（越高越好）
        """
        if not self.strategy:
            return 0.0
        
        # 设置策略参数
        for param_name, value in params.items():
            if hasattr(self.strategy, param_name):
                setattr(self.strategy, param_name, value)
        
        # 运行回测
        try:
            results = self.strategy.backtest(backtest_data)
            # 返回夏普比率作为优化目标
            return results.get('sharpe_ratio', 0.0)
        except Exception as e:
            print(f"评估策略时出错: {e}")
            return 0.0
    
    def grid_search(self, param_space: Dict[str, List[float]], backtest_data: pd.DataFrame) -> Dict[str, Any]:
        """网格搜索优化
        
        Args:
            param_space: 参数空间，每个参数的候选值列表
            backtest_data: 回测数据
            
        Returns:
            最优参数和性能
        """
        best_score = -float('inf')
        best_params = None
        
        # 生成所有参数组合
        param_combinations = self._generate_param_combinations(param_space)
        
        for params in param_combinations:
            score = self.evaluate_strategy(params, backtest_data)
            self.optimization_history.append({'params': params, 'score': score})
            
            if score > best_score:
                best_score = score
                best_params = params
        
        return {
            'best_params': best_params,
            'best_score': best_score,
            'history': self.optimization_history
        }
    
    def random_search(self, param_space: Dict[str, Tuple[float, float]], backtest_data: pd.DataFrame, 
                     n_iter: int = 100) -> Dict[str, Any]:
        """随机搜索优化
        
        Args:
            param_space: 参数空间，每个参数的范围 (min, max)
            backtest_data: 回测数据
            n_iter: 迭代次数
            
        Returns:
            最优参数和性能
        """
        best_score = -float('inf')
        best_params = None
        
        for i in range(n_iter):
            # 随机生成参数
            params = {}
            for param_name, (min_val, max_val) in param_space.items():
                params[param_name] = random.uniform(min_val, max_val)
            
            score = self.evaluate_strategy(params, backtest_data)
            self.optimization_history.append({'params': params, 'score': score})
            
            if score > best_score:
                best_score = score
                best_params = params
        
        return {
            'best_params': best_params,
            'best_score': best_score,
            'history': self.optimization_history
        }
    
    def bayesian_optimization(self, param_space: Dict[str, Tuple[float, float]], backtest_data: pd.DataFrame, 
                             n_iter: int = 50, init_points: int = 10) -> Dict[str, Any]:
        """贝叶斯优化
        
        Args:
            param_space: 参数空间，每个参数的范围 (min, max)
            backtest_data: 回测数据
            n_iter: 迭代次数
            init_points: 初始点数量
            
        Returns:
            最优参数和性能
        """
        # 目标函数
        def target(**params):
            return self.evaluate_strategy(params, backtest_data)
        
        # 创建贝叶斯优化器
        optimizer = BayesianOptimization(
            f=target,
            pbounds=param_space,
            random_state=42
        )
        
        # 运行优化
        optimizer.maximize(
            init_points=init_points,
            n_iter=n_iter
        )
        
        # 记录历史
        for i, res in enumerate(optimizer.res):
            self.optimization_history.append({
                'params': res['params'],
                'score': res['target']
            })
        
        return {
            'best_params': optimizer.max['params'],
            'best_score': optimizer.max['target'],
            'history': self.optimization_history
        }
    
    def differential_evolution_optimization(self, param_space: Dict[str, Tuple[float, float]], 
                                           backtest_data: pd.DataFrame, 
                                           maxiter: int = 100, 
                                           popsize: int = 15) -> Dict[str, Any]:
        """差分进化优化
        
        Args:
            param_space: 参数空间，每个参数的范围 (min, max)
            backtest_data: 回测数据
            maxiter: 最大迭代次数
            popsize: 种群大小
            
        Returns:
            最优参数和性能
        """
        # 转换参数空间为列表
        param_names = list(param_space.keys())
        bounds = [param_space[name] for name in param_names]
        
        # 目标函数（最小化负的性能指标）
        def target(params):
            param_dict = dict(zip(param_names, params))
            return -self.evaluate_strategy(param_dict, backtest_data)
        
        # 运行优化
        result = differential_evolution(
            target,
            bounds=bounds,
            maxiter=maxiter,
            popsize=popsize,
            tol=0.01,
            mutation=(0.5, 1),
            recombination=0.7,
            seed=42
        )
        
        # 记录历史（简化版）
        best_params = dict(zip(param_names, result.x))
        best_score = -result.fun
        self.optimization_history.append({
            'params': best_params,
            'score': best_score
        })
        
        return {
            'best_params': best_params,
            'best_score': best_score,
            'history': self.optimization_history
        }
    
    def _generate_param_combinations(self, param_space: Dict[str, List[float]]) -> List[Dict[str, float]]:
        """生成所有参数组合
        
        Args:
            param_space: 参数空间
            
        Returns:
            参数组合列表
        """
        if not param_space:
            return [{}]
        
        # 获取第一个参数及其值
        first_param, values = next(iter(param_space.items()))
        remaining_params = {k: v for k, v in param_space.items() if k != first_param}
        
        # 递归生成组合
        combinations = []
        for value in values:
            for rest in self._generate_param_combinations(remaining_params):
                combination = rest.copy()
                combination[first_param] = value
                combinations.append(combination)
        
        return combinations
    
    def get_optimization_history(self) -> List[Dict[str, Any]]:
        """获取优化历史
        
        Returns:
            优化历史记录
        """
        return self.optimization_history
    
    def clear_history(self):
        """清除优化历史"""
        self.optimization_history = []
    
    def optimize(self, method: str, param_space: Dict[str, Any], backtest_data: pd.DataFrame, 
                **kwargs) -> Dict[str, Any]:
        """统一的优化接口
        
        Args:
            method: 优化方法 ('grid', 'random', 'bayesian', 'differential_evolution')
            param_space: 参数空间
            backtest_data: 回测数据
            **kwargs: 额外参数
            
        Returns:
            优化结果
        """
        self.clear_history()
        
        if method == 'grid':
            return self.grid_search(param_space, backtest_data)
        elif method == 'random':
            n_iter = kwargs.get('n_iter', 100)
            return self.random_search(param_space, backtest_data, n_iter)
        elif method == 'bayesian':
            n_iter = kwargs.get('n_iter', 50)
            init_points = kwargs.get('init_points', 10)
            return self.bayesian_optimization(param_space, backtest_data, n_iter, init_points)
        elif method == 'differential_evolution':
            maxiter = kwargs.get('maxiter', 100)
            popsize = kwargs.get('popsize', 15)
            return self.differential_evolution_optimization(param_space, backtest_data, maxiter, popsize)
        else:
            raise ValueError(f"不支持的优化方法: {method}")
