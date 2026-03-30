"""
多策略组合管理

功能：
1. 管理多个策略
2. 策略性能评估
3. 自动策略切换
4. 策略组合优化
"""

import logging
import time
from typing import Dict, List, Any, Optional

from .strategy_base import Strategy

logger = logging.getLogger(__name__)


class MultiStrategyManager:
    """多策略组合管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化多策略管理器
        
        Args:
            config: 配置信息
        """
        self.config = config
        self.strategies: Dict[str, Strategy] = {}
        self.strategy_performance: Dict[str, Dict[str, Any]] = {}
        self.switch_threshold = config.get("switch_threshold", 0.05)  # 切换阈值
        self.evaluation_period = config.get("evaluation_period", 3600)  # 评估周期（秒）
        self.last_evaluation_time = time.time()
        self.best_strategy = None
    
    def add_strategy(self, strategy: Strategy):
        """添加策略
        
        Args:
            strategy: 策略实例
        """
        self.strategies[strategy.name] = strategy
        self.strategy_performance[strategy.name] = {
            "total_pnl": 0,
            "win_rate": 0,
            "sharpe_ratio": 0,
            "max_drawdown": 0,
            "last_updated": time.time()
        }
        logger.info(f"添加策略: {strategy.name}")
    
    def remove_strategy(self, strategy_name: str):
        """移除策略
        
        Args:
            strategy_name: 策略名称
        """
        if strategy_name in self.strategies:
            del self.strategies[strategy_name]
            del self.strategy_performance[strategy_name]
            logger.info(f"移除策略: {strategy_name}")
    
    def generate_signals(self, market_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成交易信号
        
        Args:
            market_data: 市场数据
            
        Returns:
            交易信号列表
        """
        signals = []
        
        # 定期评估策略性能并切换
        if time.time() - self.last_evaluation_time >= self.evaluation_period:
            self.evaluate_strategies()
            self.last_evaluation_time = time.time()
        
        # 只使用最佳策略生成信号
        if self.best_strategy and self.strategies[self.best_strategy].is_active():
            signal = self.strategies[self.best_strategy].generate_signal(market_data)
            if signal:
                signal["strategy"] = self.best_strategy
                signals.append(signal)
        else:
            # 如果没有最佳策略，使用所有激活的策略
            for name, strategy in self.strategies.items():
                if strategy.is_active():
                    signal = strategy.generate_signal(market_data)
                    if signal:
                        signal["strategy"] = name
                        signals.append(signal)
        
        return signals
    
    def evaluate_strategies(self):
        """评估策略性能并更新最佳策略"""
        logger.info("开始评估策略性能")
        
        # 更新每个策略的性能
        for name, strategy in self.strategies.items():
            performance = strategy.get_performance()
            if performance:
                self.strategy_performance[name].update(performance)
                self.strategy_performance[name]["last_updated"] = time.time()
        
        # 选择最佳策略
        if self.strategy_performance:
            # 根据夏普比率和总盈亏综合评估
            best_score = -float('inf')
            best_strategy = None
            
            for name, perf in self.strategy_performance.items():
                # 计算综合得分
                sharpe = perf.get("sharpe_ratio", 0)
                total_pnl = perf.get("total_pnl", 0)
                win_rate = perf.get("win_rate", 0)
                
                # 综合得分公式
                score = sharpe * 0.5 + (total_pnl / 1000) * 0.3 + win_rate * 0.2
                
                if score > best_score:
                    best_score = score
                    best_strategy = name
            
            # 检查是否需要切换策略
            if best_strategy and best_strategy != self.best_strategy:
                # 计算性能差异
                if self.best_strategy:
                    current_perf = self.strategy_performance.get(self.best_strategy, {})
                    new_perf = self.strategy_performance.get(best_strategy, {})
                    current_score = current_perf.get("sharpe_ratio", 0) * 0.5 + (current_perf.get("total_pnl", 0) / 1000) * 0.3 + current_perf.get("win_rate", 0) * 0.2
                    new_score = best_score
                    
                    # 只有当性能提升超过阈值时才切换
                    if (new_score - current_score) / abs(current_score) > self.switch_threshold:
                        self._switch_strategy(best_strategy)
                else:
                    # 首次选择策略
                    self._switch_strategy(best_strategy)
    
    def _switch_strategy(self, new_strategy_name: str):
        """切换策略
        
        Args:
            new_strategy_name: 新策略名称
        """
        # 停用当前最佳策略
        if self.best_strategy and self.best_strategy in self.strategies:
            self.strategies[self.best_strategy].deactivate()
            logger.info(f"停用策略: {self.best_strategy}")
        
        # 激活新策略
        if new_strategy_name in self.strategies:
            self.strategies[new_strategy_name].activate()
            self.best_strategy = new_strategy_name
            logger.info(f"切换到最佳策略: {new_strategy_name}")
    
    def get_strategy_performance(self) -> Dict[str, Dict[str, Any]]:
        """获取所有策略的性能
        
        Returns:
            策略性能字典
        """
        return self.strategy_performance
    
    def get_best_strategy(self) -> Optional[str]:
        """获取当前最佳策略
        
        Returns:
            最佳策略名称
        """
        return self.best_strategy
    
    def update_strategy_parameters(self, strategy_name: str, params: Dict[str, Any]):
        """更新策略参数
        
        Args:
            strategy_name: 策略名称
            params: 新的参数
        """
        if strategy_name in self.strategies:
            self.strategies[strategy_name].update_parameters(params)
            logger.info(f"更新策略参数: {strategy_name}")
    
    def activate_strategy(self, strategy_name: str):
        """激活策略
        
        Args:
            strategy_name: 策略名称
        """
        if strategy_name in self.strategies:
            self.strategies[strategy_name].activate()
            logger.info(f"激活策略: {strategy_name}")
    
    def deactivate_strategy(self, strategy_name: str):
        """停用策略
        
        Args:
            strategy_name: 策略名称
        """
        if strategy_name in self.strategies:
            self.strategies[strategy_name].deactivate()
            logger.info(f"停用策略: {strategy_name}")
    
    def get_active_strategies(self) -> List[str]:
        """获取所有激活的策略
        
        Returns:
            激活策略名称列表
        """
        return [name for name, strategy in self.strategies.items() if strategy.is_active()]
    
    def get_all_strategies(self) -> List[str]:
        """获取所有策略
        
        Returns:
            策略名称列表
        """
        return list(self.strategies.keys())