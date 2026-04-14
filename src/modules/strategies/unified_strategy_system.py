"""
统一策略系统

整合所有策略管理功能：
1. 策略生命周期管理
2. 策略评估
3. 策略优化
4. 策略回测
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

from src.modules.core.module_config_utils import resolve_module_config

logger = logging.getLogger(__name__)


class UnifiedStrategySystem:
    """
    统一策略系统
    
    整合所有策略管理功能，提供统一接口
    """
    
    def __init__(self, config: Dict[str, Any] = None, config_manager=None):
        """
        初始化统一策略系统
        
        Args:
            config: 配置字典
        """
        self.config = resolve_module_config(
            config=config,
            config_manager=config_manager,
            section="unified_strategy_system",
            defaults={},
        )
        
        # 子模块（保留现有模块的引用）
        self.manager = None
        self.evaluator = None
        self.optimizer = None
        self.backtester = None
        
        # 策略注册表
        self.strategies: Dict[str, Any] = {}
        
        # 策略性能缓存
        self._performance_cache: Dict[str, Dict] = {}
        
        # 统计信息
        self.stats = {
            "total_strategies": 0,
            "active_strategies": 0,
            "total_backtests": 0,
            "total_optimizations": 0
        }
        
        logger.info("统一策略系统初始化")
    
    async def initialize(self) -> bool:
        """
        初始化所有子模块
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            logger.info("🔧 初始化统一策略系统...")
            
            # 初始化策略管理器
            await self._init_manager()
            
            # 初始化策略评估器
            await self._init_evaluator()
            
            # 初始化策略优化器
            await self._init_optimizer()
            
            # 初始化策略回测器
            await self._init_backtester()
            
            logger.info("✅ 统一策略系统初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 统一策略系统初始化失败: {e}")
            return False
    
    async def _init_manager(self):
        """初始化策略管理器"""
        try:
            from src.modules.core.strategy_manager import StrategyManager
            self.manager = StrategyManager(None)  # config_manager will be set later
            logger.info("✅ 策略管理器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 策略管理器初始化失败: {e}")
            self.manager = None
    
    async def _init_evaluator(self):
        """初始化策略评估器"""
        try:
            from src.modules.strategies.strategy_evaluator import StrategyEvaluator
            self.evaluator = StrategyEvaluator("unified_system")
            logger.info("✅ 策略评估器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 策略评估器初始化失败: {e}")
            self.evaluator = None
    
    async def _init_optimizer(self):
        """初始化策略优化器"""
        try:
            from src.modules.strategies.parameter_optimizer import ParameterOptimizer
            from src.modules.strategies.portfolio_optimizer import PortfolioOptimizer
            
            self.optimizer = {
                "parameter": ParameterOptimizer(),
                "portfolio": PortfolioOptimizer()
            }
            logger.info("✅ 策略优化器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 策略优化器初始化失败: {e}")
            self.optimizer = None
    
    async def _init_backtester(self):
        """初始化策略回测器"""
        try:
            from src.modules.backtesting.backtest_engine import BacktestEngine
            self.backtester = BacktestEngine()
            logger.info("✅ 策略回测器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 策略回测器初始化失败: {e}")
            self.backtester = None
    
    # ==================== 策略生命周期管理 ====================
    
    async def create_strategy(self, strategy_config: Dict[str, Any]) -> Optional[str]:
        """
        创建策略
        
        Args:
            strategy_config: 策略配置
        
        Returns:
            Optional[str]: 策略ID
        """
        try:
            strategy_id = strategy_config.get("id", f"strategy_{datetime.now().timestamp()}")
            
            # 注册策略
            self.strategies[strategy_id] = {
                "config": strategy_config,
                "status": "created",
                "created_at": datetime.now(),
                "performance": {}
            }
            
            # 使用管理器创建
            if self.manager:
                try:
                    await self.manager.create_strategy_instance(strategy_config)
                except Exception as e:
                    logger.debug(f"策略管理器创建实例失败 {strategy_id}: {e}")
            
            self.stats["total_strategies"] += 1
            
            logger.info(f"✅ 策略已创建: {strategy_id}")
            return strategy_id
            
        except Exception as e:
            logger.error(f"创建策略失败: {e}")
            return None
    
    async def start_strategy(self, strategy_id: str) -> bool:
        """
        启动策略
        
        Args:
            strategy_id: 策略ID
        
        Returns:
            bool: 是否成功
        """
        try:
            if strategy_id not in self.strategies:
                logger.warning(f"策略不存在: {strategy_id}")
                return False
            
            # 使用管理器启动
            if self.manager:
                try:
                    await self.manager.start_strategy(strategy_id)
                except Exception as e:
                    logger.debug(f"策略管理器启动失败 {strategy_id}: {e}")
            
            # 更新状态
            self.strategies[strategy_id]["status"] = "running"
            self.stats["active_strategies"] = sum(
                1 for s in self.strategies.values() if s["status"] == "running"
            )
            
            logger.info(f"✅ 策略已启动: {strategy_id}")
            return True
            
        except Exception as e:
            logger.error(f"启动策略失败 {strategy_id}: {e}")
            return False
    
    async def stop_strategy(self, strategy_id: str) -> bool:
        """
        停止策略
        
        Args:
            strategy_id: 策略ID
        
        Returns:
            bool: 是否成功
        """
        try:
            if strategy_id not in self.strategies:
                return False
            
            # 使用管理器停止
            if self.manager:
                try:
                    await self.manager.stop_strategy(strategy_id)
                except Exception as e:
                    logger.debug(f"策略管理器停止失败 {strategy_id}: {e}")
            
            # 更新状态
            self.strategies[strategy_id]["status"] = "stopped"
            self.stats["active_strategies"] = sum(
                1 for s in self.strategies.values() if s["status"] == "running"
            )
            
            logger.info(f"✅ 策略已停止: {strategy_id}")
            return True
            
        except Exception as e:
            logger.error(f"停止策略失败 {strategy_id}: {e}")
            return False
    
    async def get_strategy_status(self, strategy_id: str) -> Dict[str, Any]:
        """
        获取策略状态
        
        Args:
            strategy_id: 策略ID
        
        Returns:
            Dict: 策略状态
        """
        try:
            if strategy_id not in self.strategies:
                return {"status": "not_found"}
            
            strategy = self.strategies[strategy_id]
            
            return {
                "id": strategy_id,
                "status": strategy["status"],
                "created_at": strategy["created_at"].isoformat(),
                "performance": strategy["performance"]
            }
            
        except Exception as e:
            logger.error(f"获取策略状态失败 {strategy_id}: {e}")
            return {"status": "error", "error": str(e)}
    
    # ==================== 策略评估 ====================
    
    async def evaluate_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """
        评估策略
        
        Args:
            strategy_id: 策略ID
        
        Returns:
            Dict: 评估结果
        """
        try:
            if strategy_id not in self.strategies:
                return {"error": "strategy_not_found"}
            
            # 使用评估器
            if self.evaluator:
                try:
                    performance = await self.evaluator.get_performance_metrics(strategy_id)
                    
                    # 更新策略性能
                    self.strategies[strategy_id]["performance"] = performance
                    self._performance_cache[strategy_id] = {
                        "performance": performance,
                        "timestamp": datetime.now()
                    }
                    
                    return performance
                except Exception as e:
                    logger.debug(f"策略评估器获取性能失败 {strategy_id}: {e}")
            
            return self.strategies[strategy_id]["performance"]
            
        except Exception as e:
            logger.error(f"评估策略失败 {strategy_id}: {e}")
            return {"error": str(e)}
    
    async def get_performance(self, strategy_id: str) -> Dict[str, Any]:
        """
        获取策略性能
        
        Args:
            strategy_id: 策略ID
        
        Returns:
            Dict: 性能数据
        """
        try:
            # 检查缓存
            if strategy_id in self._performance_cache:
                cached = self._performance_cache[strategy_id]
                if datetime.now() - cached["timestamp"] < timedelta(minutes=5):
                    return cached["performance"]
            
            # 重新评估
            return await self.evaluate_strategy(strategy_id)
            
        except Exception as e:
            logger.error(f"获取策略性能失败 {strategy_id}: {e}")
            return {}
    
    # ==================== 策略优化 ====================
    
    async def optimize_parameters(self, strategy_id: str, 
                                  optimization_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        优化策略参数
        
        Args:
            strategy_id: 策略ID
            optimization_config: 优化配置
        
        Returns:
            Dict: 优化结果
        """
        try:
            if not self.optimizer or "parameter" not in self.optimizer:
                return {"error": "optimizer_not_available"}
            
            parameter_optimizer = self.optimizer["parameter"]
            
            # 执行优化
            try:
                result = await parameter_optimizer.grid_search(
                    strategy_id,
                    optimization_config or {}
                )
                
                self.stats["total_optimizations"] += 1
                
                logger.info(f"✅ 策略参数优化完成: {strategy_id}")
                return result
            except:
                return {"error": "optimization_failed"}
            
        except Exception as e:
            logger.error(f"优化策略参数失败 {strategy_id}: {e}")
            return {"error": str(e)}
    
    async def optimize_portfolio(self, strategies: List[str]) -> Dict[str, Any]:
        """
        优化投资组合
        
        Args:
            strategies: 策略列表
        
        Returns:
            Dict: 优化结果
        """
        try:
            if not self.optimizer or "portfolio" not in self.optimizer:
                return {"error": "optimizer_not_available"}
            
            portfolio_optimizer = self.optimizer["portfolio"]
            
            # 执行优化
            try:
                result = await portfolio_optimizer.minimum_variance_portfolio(strategies)
                
                self.stats["total_optimizations"] += 1
                
                logger.info("✅ 投资组合优化完成")
                return result
            except:
                return {"error": "optimization_failed"}
            
        except Exception as e:
            logger.error(f"优化投资组合失败: {e}")
            return {"error": str(e)}
    
    # ==================== 策略回测 ====================
    
    async def backtest_strategy(self, strategy_id: str, 
                                backtest_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        回测策略
        
        Args:
            strategy_id: 策略ID
            backtest_config: 回测配置
        
        Returns:
            Dict: 回测结果
        """
        try:
            if not self.backtester:
                return {"error": "backtester_not_available"}
            
            # 执行回测
            try:
                result = await self.backtester.run_backtest(
                    strategy_id,
                    backtest_config or {}
                )
                
                self.stats["total_backtests"] += 1
                
                logger.info(f"✅ 策略回测完成: {strategy_id}")
                return result
            except:
                return {"error": "backtest_failed"}
            
        except Exception as e:
            logger.error(f"回测策略失败 {strategy_id}: {e}")
            return {"error": str(e)}
    
    # ==================== 统计和监控 ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict: 统计信息
        """
        return {
            **self.stats,
            "manager_available": self.manager is not None,
            "evaluator_available": self.evaluator is not None,
            "optimizer_available": self.optimizer is not None,
            "backtester_available": self.backtester is not None
        }
    
    # ==================== 清理 ====================
    
    async def cleanup(self):
        """清理资源"""
        try:
            logger.info("清理统一策略系统...")
            
            # 停止所有运行中的策略
            for strategy_id, strategy in self.strategies.items():
                if strategy["status"] == "running":
                    await self.stop_strategy(strategy_id)
            
            # 清理缓存
            self._performance_cache.clear()
            
            logger.info("✅ 统一策略系统清理完成")
        except Exception as e:
            logger.error(f"清理失败: {e}")
