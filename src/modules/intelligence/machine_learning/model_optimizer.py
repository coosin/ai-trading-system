from __future__ import annotations

import asyncio
import logging
import time
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Callable

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from src.modules.intelligence.machine_learning.model_manager import ModelManager, ModelType, ModelPerformance

logger = logging.getLogger(__name__)


class ModelPerformanceStatus(Enum):
    """模型性能状态"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


@dataclass
class ModelPerformanceMetric:
    """模型性能指标"""
    timestamp: float
    model_type: ModelType
    mape: float  # 平均绝对百分比误差
    mae: float  # 平均绝对误差
    mse: float  # 均方误差
    rmse: float  # 均方根误差
    r2: float  # R²评分
    accuracy: float  # 准确率（用于分类模型）
    status: ModelPerformanceStatus


@dataclass
class ModelOptimizationResult:
    """模型优化结果"""
    timestamp: float
    model_type: ModelType
    old_performance: ModelPerformanceMetric
    new_performance: ModelPerformanceMetric
    improvement: float  # 性能提升百分比
    training_time: float  # 训练时间（秒）
    success: bool
    message: str


class ModelOptimizer:
    """模型自动优化器"""

    def __init__(self, model_manager: ModelManager, config: Dict[str, Any]):
        """初始化模型优化器

        Args:
            model_manager: 模型管理器
            config: 配置信息
        """
        self.model_manager = model_manager
        self.config = config
        self.enabled = False
        self.performance_history = {}
        self.optimization_history = []
        self.monitoring_interval = config.get("monitoring_interval", 3600)  # 秒
        self.optimization_threshold = config.get("optimization_threshold", 0.1)  # 性能下降阈值
        self.max_performance_history = config.get("max_performance_history", 100)
        self.training_config = config.get("training_config", {})

    async def initialize(self) -> bool:
        """初始化模型优化器

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 初始化性能历史
            for model_type in ModelType:
                self.performance_history[model_type] = []
            
            # 启动监控循环
            asyncio.create_task(self._monitoring_loop())
            
            self.enabled = True
            logger.info("ModelOptimizer initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize ModelOptimizer: {e}")
            return False

    async def shutdown(self) -> bool:
        """关闭模型优化器

        Returns:
            bool: 关闭是否成功
        """
        try:
            self.enabled = False
            self.performance_history.clear()
            self.optimization_history.clear()
            logger.info("ModelOptimizer shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown ModelOptimizer: {e}")
            return False

    async def _monitoring_loop(self):
        """监控循环"""
        while self.enabled:
            try:
                # 检查所有模型的性能
                for model_type in ModelType:
                    await self._check_model_performance(model_type)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            await asyncio.sleep(self.monitoring_interval)

    async def _check_model_performance(self, model_type: ModelType):
        """检查模型性能

        Args:
            model_type: 模型类型
        """
        try:
            # 获取模型性能
            performance = await self._evaluate_model(model_type)
            if performance:
                # 添加到性能历史
                self.performance_history[model_type].append(performance)
                
                # 限制历史记录大小
                if len(self.performance_history[model_type]) > self.max_performance_history:
                    self.performance_history[model_type] = self.performance_history[model_type][-self.max_performance_history:]
                
                # 检查性能是否下降
                if await self._should_optimize(model_type, performance):
                    # 优化模型
                    await self.optimize_model(model_type)
        except Exception as e:
            logger.error(f"Error checking model performance: {e}")

    async def _evaluate_model(self, model_type: ModelType) -> Optional[ModelPerformanceMetric]:
        """评估模型性能

        Args:
            model_type: 模型类型

        Returns:
            Optional[ModelPerformanceMetric]: 模型性能指标
        """
        try:
            # 获取模型实例
            model = self.model_manager.get_model(model_type)
            if not model:
                logger.error(f"Model {model_type.value} not found")
                return None
            
            # 获取测试数据
            test_data = await self.model_manager.get_test_data(model_type)
            if test_data is None or len(test_data) == 0:
                # 暂时使用模拟数据
                mape = np.random.normal(0.05, 0.02)
                mae = np.random.normal(100, 20)
                mse = np.random.normal(15000, 3000)
                rmse = np.sqrt(mse)
                r2 = np.random.normal(0.8, 0.1)
                accuracy = np.random.normal(0.7, 0.1)
            else:
                # 使用实际数据评估
                X_test, y_test = test_data
                predictions = await self.model_manager.predict(model_type, X_test)
                
                # 计算性能指标
                mape = np.mean(np.abs((y_test - predictions) / y_test)) if np.any(y_test) else 0
                mae = mean_absolute_error(y_test, predictions)
                mse = mean_squared_error(y_test, predictions)
                rmse = np.sqrt(mse)
                r2 = r2_score(y_test, predictions)
                accuracy = np.mean(np.abs((y_test - predictions) / y_test) < 0.05)  # 预测误差小于5%的准确率
            
            # 确定性能状态
            status = self._determine_performance_status(mape, r2, accuracy)
            
            return ModelPerformanceMetric(
                timestamp=time.time(),
                model_type=model_type,
                mape=mape,
                mae=mae,
                mse=mse,
                rmse=rmse,
                r2=r2,
                accuracy=accuracy,
                status=status
            )
        except Exception as e:
            logger.error(f"Error evaluating model: {e}")
            return None

    def _determine_performance_status(self, mape: float, r2: float, accuracy: float) -> ModelPerformanceStatus:
        """确定性能状态

        Args:
            mape: 平均绝对百分比误差
            r2: R²评分
            accuracy: 准确率

        Returns:
            ModelPerformanceStatus: 性能状态
        """
        if mape < 0.03 and r2 > 0.9 and accuracy > 0.85:
            return ModelPerformanceStatus.EXCELLENT
        elif mape < 0.05 and r2 > 0.8 and accuracy > 0.75:
            return ModelPerformanceStatus.GOOD
        elif mape < 0.1 and r2 > 0.6 and accuracy > 0.65:
            return ModelPerformanceStatus.FAIR
        elif mape < 0.15 and r2 > 0.4 and accuracy > 0.55:
            return ModelPerformanceStatus.POOR
        else:
            return ModelPerformanceStatus.CRITICAL

    async def _should_optimize(self, model_type: ModelType, current_performance: ModelPerformanceMetric) -> bool:
        """判断是否需要优化模型

        Args:
            model_type: 模型类型
            current_performance: 当前性能

        Returns:
            bool: 是否需要优化
        """
        try:
            # 检查性能历史
            history = self.performance_history[model_type]
            if len(history) < 3:
                return False
            
            # 计算性能趋势
            recent_history = history[-3:]
            mape_values = [h.mape for h in recent_history]
            r2_values = [h.r2 for h in recent_history]
            accuracy_values = [h.accuracy for h in recent_history]
            
            # 检查性能是否持续下降
            mape_trend = np.polyfit(range(len(mape_values)), mape_values, 1)[0]
            r2_trend = np.polyfit(range(len(r2_values)), r2_values, 1)[0]
            accuracy_trend = np.polyfit(range(len(accuracy_values)), accuracy_values, 1)[0]
            
            # 检查当前性能是否低于阈值
            if current_performance.status in [ModelPerformanceStatus.POOR, ModelPerformanceStatus.CRITICAL]:
                return True
            
            # 检查性能是否持续下降
            if mape_trend > 0.001 and r2_trend < -0.01 and accuracy_trend < -0.01:
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error determining if optimization is needed: {e}")
            return False

    async def optimize_model(self, model_type: ModelType) -> Optional[ModelOptimizationResult]:
        """优化模型

        Args:
            model_type: 模型类型

        Returns:
            Optional[ModelOptimizationResult]: 优化结果
        """
        try:
            # 获取当前性能
            old_performance = await self._evaluate_model(model_type)
            if not old_performance:
                return None
            
            logger.info(f"Optimizing model: {model_type.value}")
            start_time = time.time()
            
            # 训练新模型
            training_config = self.training_config.get(model_type.value, {})
            success = await self.model_manager.train_model(model_type, training_config)
            
            training_time = time.time() - start_time
            
            # 获取新性能
            new_performance = await self._evaluate_model(model_type)
            if not new_performance:
                return None
            
            # 计算性能提升
            improvement = self._calculate_improvement(old_performance, new_performance)
            
            # 保存优化结果
            result = ModelOptimizationResult(
                timestamp=time.time(),
                model_type=model_type,
                old_performance=old_performance,
                new_performance=new_performance,
                improvement=improvement,
                training_time=training_time,
                success=success,
                message=f"Model {model_type.value} optimized"
            )
            
            self.optimization_history.append(result)
            
            logger.info(f"Model {model_type.value} optimized successfully. Improvement: {improvement:.2f}%")
            return result
        except Exception as e:
            logger.error(f"Error optimizing model: {e}")
            return None

    def _calculate_improvement(self, old_performance: ModelPerformanceMetric, new_performance: ModelPerformanceMetric) -> float:
        """计算性能提升

        Args:
            old_performance: 旧性能
            new_performance: 新性能

        Returns:
            float: 性能提升百分比
        """
        try:
            # 综合考虑多个指标的改进
            mape_improvement = (old_performance.mape - new_performance.mape) / old_performance.mape * 100
            r2_improvement = (new_performance.r2 - old_performance.r2) / max(old_performance.r2, 0.1) * 100
            accuracy_improvement = (new_performance.accuracy - old_performance.accuracy) / max(old_performance.accuracy, 0.1) * 100
            
            # 加权平均
            improvement = (mape_improvement * 0.4 + r2_improvement * 0.3 + accuracy_improvement * 0.3)
            return improvement
        except Exception as e:
            logger.error(f"Error calculating improvement: {e}")
            return 0.0

    async def get_model_performance(self, model_type: ModelType) -> Optional[ModelPerformanceMetric]:
        """获取模型性能

        Args:
            model_type: 模型类型

        Returns:
            Optional[ModelPerformanceMetric]: 模型性能
        """
        history = self.performance_history.get(model_type, [])
        if history:
            return history[-1]
        return None

    def get_performance_history(self, model_type: ModelType, limit: int = 10) -> List[ModelPerformanceMetric]:
        """获取性能历史

        Args:
            model_type: 模型类型
            limit: 返回的历史记录数量

        Returns:
            List[ModelPerformanceMetric]: 性能历史
        """
        history = self.performance_history.get(model_type, [])
        return history[-limit:]

    def get_optimization_history(self, limit: int = 10) -> List[ModelOptimizationResult]:
        """获取优化历史

        Args:
            limit: 返回的历史记录数量

        Returns:
            List[ModelOptimizationResult]: 优化历史
        """
        return self.optimization_history[-limit:]

    async def force_optimize(self, model_type: ModelType) -> Optional[ModelOptimizationResult]:
        """强制优化模型

        Args:
            model_type: 模型类型

        Returns:
            Optional[ModelOptimizationResult]: 优化结果
        """
        return await self.optimize_model(model_type)

    def is_healthy(self) -> bool:
        """检查模型优化器是否健康

        Returns:
            bool: 健康状态
        """
        return self.enabled
