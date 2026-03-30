from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

import pandas as pd

from src.modules.core.data_pipeline import DataPoint
from src.modules.core.database_manager import DatabaseManager
from src.modules.core.data_fusion import DataFusionSystem
from src.modules.intelligence.machine_learning import ModelManager, ModelType

logger = logging.getLogger(__name__)


class DecisionType(Enum):
    """决策类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    EXIT = "exit"


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class Decision:
    """决策结果"""
    decision_type: DecisionType
    asset: str
    amount: float
    price: float
    confidence: float
    risk_level: RiskLevel
    timestamp: float
    reason: str
    metadata: Dict[str, Any]


class DecisionEngine:
    """决策引擎模块"""

    def __init__(self, db_manager: DatabaseManager, config: Dict[str, Any]):
        """初始化决策引擎

        Args:
            db_manager: 数据库管理器
            config: 配置信息
        """
        self.db_manager = db_manager
        self.config = config
        self.models = {}
        self.risk_thresholds = config.get("risk_thresholds", {
            "low": 0.2,
            "medium": 0.4,
            "high": 0.7,
            "extreme": 1.0
        })
        self.confidence_threshold = config.get("confidence_threshold", 0.6)
        self.enabled = False
        # 自适应学习相关
        self.decision_history = []  # 历史决策记录
        self.learning_rate = config.get("learning_rate", 0.1)  # 学习率
        self.reward_factor = config.get("reward_factor", 1.0)  # 奖励因子
        self.penalty_factor = config.get("penalty_factor", 1.0)  # 惩罚因子
        # 机器学习模型管理器
        self.model_manager = ModelManager(db_manager, config.get("machine_learning", {}))
        # 数据融合系统
        self.data_fusion_system = DataFusionSystem(db_manager, config.get("data_fusion", {}))

    async def initialize(self) -> bool:
        """初始化决策引擎

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 加载模型配置
            model_configs = self.config.get("models", [])
            for model_config in model_configs:
                model_name = model_config.get("name")
                if model_name:
                    self.models[model_name] = model_config

            # 初始化模型管理器
            await self.model_manager.initialize()

            # 初始化数据融合系统
            await self.data_fusion_system.initialize()

            self.enabled = True
            logger.info("DecisionEngine initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize DecisionEngine: {e}")
            return False

    async def shutdown(self) -> bool:
        """关闭决策引擎

        Returns:
            bool: 关闭是否成功
        """
        try:
            self.enabled = False
            self.models.clear()
            # 关闭模型管理器
            await self.model_manager.shutdown()
            # 关闭数据融合系统
            await self.data_fusion_system.shutdown()
            logger.info("DecisionEngine shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown DecisionEngine: {e}")
            return False

    async def make_decision(self, data_points: List[DataPoint]) -> Optional[Decision]:
        """制定决策

        Args:
            data_points: 数据点列表

        Returns:
            Optional[Decision]: 决策结果
        """
        if not self.enabled:
            logger.warning("DecisionEngine is not enabled")
            return None

        try:
            # 分析数据
            analysis_result = await self._analyze_data(data_points)
            
            # 评估风险
            risk_level = self._assess_risk(analysis_result)
            
            # 制定决策
            decision = await self._generate_decision(analysis_result, risk_level)
            
            if decision:
                # 记录决策
                await self._record_decision(decision)
                
            return decision
        except Exception as e:
            logger.error(f"Error making decision: {e}")
            return None

    async def _analyze_data(self, data_points: List[DataPoint]) -> Dict[str, Any]:
        """分析数据

        Args:
            data_points: 数据点列表

        Returns:
            Dict[str, Any]: 分析结果
        """
        analysis_result = {
            "market_trend": None,
            "volatility": 0.0,
            "liquidity": 0.0,
            "sentiment": 0.0,
            "technical_indicators": {},
            "fundamental_indicators": {},
            "model_predictions": {},
            "ml_prediction": None,
            "ml_confidence": 0.0,
            "fused_data": None,
            "fused_confidence": 0.0
        }

        # 分析市场趋势
        if data_points:
            # 简单的趋势分析
            prices = [dp.data.get("price", 0) for dp in data_points]
            if len(prices) > 1:
                if prices[-1] > prices[0]:
                    analysis_result["market_trend"] = "up"
                elif prices[-1] < prices[0]:
                    analysis_result["market_trend"] = "down"
                else:
                    analysis_result["market_trend"] = "sideways"

                # 计算波动率
                if len(prices) > 2:
                    returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
                    analysis_result["volatility"] = sum(abs(r) for r in returns) / len(returns)

            # 使用数据融合系统
            symbol = data_points[0].symbol if data_points[0].symbol else "BTCUSDT"
            fused_data = await self.data_fusion_system.fuse_data(symbol)
            if fused_data:
                analysis_result["fused_data"] = fused_data.data
                analysis_result["fused_confidence"] = fused_data.confidence
                
                # 从融合数据中提取情绪指标
                if "social_sentiment" in fused_data.data:
                    analysis_result["sentiment"] = fused_data.data["social_sentiment"]
                if "news_sentiment" in fused_data.data:
                    analysis_result["sentiment"] = (analysis_result["sentiment"] + fused_data.data["news_sentiment"]) / 2

            # 准备机器学习模型输入数据
            df = pd.DataFrame([{
                "timestamp": dp.timestamp,
                "open": dp.data.get("open", dp.data.get("price", 0)),
                "high": dp.data.get("high", dp.data.get("price", 0)),
                "low": dp.data.get("low", dp.data.get("price", 0)),
                "close": dp.data.get("price", 0),
                "volume": dp.data.get("volume", 0)
            } for dp in data_points])

            # 使用机器学习模型预测
            if len(df) >= 60:  # 确保有足够的历史数据
                prediction = await self.model_manager.predict(symbol, df)
                if prediction:
                    analysis_result["ml_prediction"] = "up" if prediction > df["close"].iloc[-1] else "down"
                    analysis_result["ml_confidence"] = 0.8  # 暂时使用固定置信度
                    
                    # 训练或更新模型（如果需要）
                    if len(df) >= 100:  # 当有足够数据时更新模型
                        await self.model_manager.train_model(
                            symbol,
                            ModelType.LSTM,
                            df,
                            {
                                "lookback": 60,
                                "hidden_size": 64,
                                "num_layers": 2,
                                "learning_rate": 0.001,
                                "epochs": 50,
                                "batch_size": 32
                            }
                        )

        # 集成多模型预测
        for model_name, model_config in self.models.items():
            try:
                # 这里应该调用实际的模型进行预测
                # 暂时使用模拟结果
                analysis_result["model_predictions"][model_name] = {
                    "prediction": "up" if analysis_result["market_trend"] == "up" else "down",
                    "confidence": 0.7 + (0.1 * len(model_name)),
                    "reason": f"Model {model_name} analysis"
                }
            except Exception as e:
                logger.error(f"Error using model {model_name}: {e}")

        return analysis_result

    def _assess_risk(self, analysis_result: Dict[str, Any]) -> RiskLevel:
        """评估风险

        Args:
            analysis_result: 分析结果

        Returns:
            RiskLevel: 风险等级
        """
        volatility = analysis_result.get("volatility", 0.0)
        
        if volatility >= self.risk_thresholds["extreme"]:
            return RiskLevel.EXTREME
        elif volatility >= self.risk_thresholds["high"]:
            return RiskLevel.HIGH
        elif volatility >= self.risk_thresholds["medium"]:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    async def _generate_decision(self, analysis_result: Dict[str, Any], risk_level: RiskLevel) -> Optional[Decision]:
        """生成决策

        Args:
            analysis_result: 分析结果
            risk_level: 风险等级

        Returns:
            Optional[Decision]: 决策结果
        """
        # 计算综合信心度
        model_predictions = analysis_result.get("model_predictions", {})
        if model_predictions:
            avg_confidence = sum(p["confidence"] for p in model_predictions.values()) / len(model_predictions)
        else:
            avg_confidence = 0.5

        # 集成机器学习模型的信心度
        ml_confidence = analysis_result.get("ml_confidence", 0.0)
        if ml_confidence > 0:
            # 权重机器学习模型的预测
            avg_confidence = (avg_confidence * 0.5) + (ml_confidence * 0.3)

        # 集成数据融合系统的信心度
        fused_confidence = analysis_result.get("fused_confidence", 0.0)
        if fused_confidence > 0:
            # 权重数据融合系统的结果
            avg_confidence = (avg_confidence * 0.8) + (fused_confidence * 0.2)

        # 如果信心度低于阈值，返回持有决策
        if avg_confidence < self.confidence_threshold:
            return Decision(
                decision_type=DecisionType.HOLD,
                asset="BTC",  # 默认资产，实际应该根据数据点确定
                amount=0.0,
                price=0.0,
                confidence=avg_confidence,
                risk_level=risk_level,
                timestamp=asyncio.get_event_loop().time(),
                reason="Confidence below threshold",
                metadata=analysis_result
            )

        # 基于市场趋势、机器学习预测、数据融合结果和风险等级生成决策
        market_trend = analysis_result.get("market_trend")
        ml_prediction = analysis_result.get("ml_prediction")
        fused_data = analysis_result.get("fused_data")
        sentiment = analysis_result.get("sentiment", 0.0)
        
        # 综合考虑所有因素
        buy_signals = 0
        sell_signals = 0
        
        # 市场趋势信号
        if market_trend == "up":
            buy_signals += 1
        elif market_trend == "down":
            sell_signals += 1
        
        # 机器学习预测信号
        if ml_prediction == "up":
            buy_signals += 1
        elif ml_prediction == "down":
            sell_signals += 1
        
        # 情绪信号
        if sentiment > 0.1:
            buy_signals += 1
        elif sentiment < -0.1:
            sell_signals += 1
        
        # 数据融合信号
        if fused_data:
            if "social_sentiment" in fused_data and fused_data["social_sentiment"] > 0.2:
                buy_signals += 1
            if "news_sentiment" in fused_data and fused_data["news_sentiment"] > 0.2:
                buy_signals += 1
            if "onchain_activity" in fused_data and fused_data["onchain_activity"] > 0.6:
                buy_signals += 1

        # 基于信号数量和风险等级生成决策
        if buy_signals > sell_signals and risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]:
            decision_type = DecisionType.BUY
            reason = f"Positive signals ({buy_signals}-{sell_signals}) with acceptable risk"
        elif sell_signals > buy_signals or risk_level in [RiskLevel.HIGH, RiskLevel.EXTREME]:
            decision_type = DecisionType.SELL
            reason = f"Negative signals ({sell_signals}-{buy_signals}) or high risk"
        else:
            decision_type = DecisionType.HOLD
            reason = "Neutral market conditions"

        return Decision(
            decision_type=decision_type,
            asset="BTC",  # 默认资产，实际应该根据数据点确定
            amount=1.0,  # 默认数量，实际应该根据资金管理策略确定
            price=0.0,  # 默认价格，实际应该使用当前市场价格
            confidence=avg_confidence,
            risk_level=risk_level,
            timestamp=asyncio.get_event_loop().time(),
            reason=reason,
            metadata=analysis_result
        )

    async def _record_decision(self, decision: Decision) -> bool:
        """记录决策

        Args:
            decision: 决策结果

        Returns:
            bool: 记录是否成功
        """
        try:
            # 记录到历史
            decision_record = {
                'id': f"decision_{int(asyncio.get_event_loop().time() * 1000)}",
                'decision_type': decision.decision_type.value,
                'asset': decision.asset,
                'amount': decision.amount,
                'price': decision.price,
                'confidence': decision.confidence,
                'risk_level': decision.risk_level.value,
                'timestamp': decision.timestamp,
                'reason': decision.reason,
                'metadata': decision.metadata
            }
            self.decision_history.append(decision_record)
            
            # 限制历史记录数量
            if len(self.decision_history) > 1000:
                self.decision_history = self.decision_history[-1000:]
            
            # 这里应该将决策记录到数据库
            # 暂时使用日志记录
            logger.info(f"Decision recorded: {decision}")
            return True
        except Exception as e:
            logger.error(f"Failed to record decision: {e}")
            return False

    async def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标

        Returns:
            Dict[str, Any]: 性能指标
        """
        try:
            # 这里应该从数据库获取历史决策和结果
            # 暂时返回模拟数据
            return {
                "total_decisions": 100,
                "correct_decisions": 65,
                "accuracy": 0.65,
                "profit_factor": 1.2,
                "max_drawdown": 0.15,
                "sharpe_ratio": 0.8
            }
        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return {}

    def is_healthy(self) -> bool:
        """检查决策引擎健康状态

        Returns:
            bool: 健康状态
        """
        return self.enabled and bool(self.models)

    async def record_decision_result(self, decision_id: str, success: bool, profit: float, market_change: float) -> bool:
        """记录决策结果

        Args:
            decision_id: 决策ID
            success: 是否成功
            profit: 利润/损失
            market_change: 市场变化

        Returns:
            bool: 记录是否成功
        """
        try:
            # 查找对应的决策
            decision = None
            for d in self.decision_history:
                if d.get('id') == decision_id:
                    decision = d
                    break
            
            if not decision:
                logger.warning(f"Decision {decision_id} not found in history")
                return False
            
            # 记录结果
            decision['success'] = success
            decision['profit'] = profit
            decision['market_change'] = market_change
            decision['result_timestamp'] = asyncio.get_event_loop().time()
            
            # 执行自适应学习
            await self._adapt_parameters(decision)
            
            logger.info(f"Decision result recorded: {decision_id}, success: {success}, profit: {profit}")
            return True
        except Exception as e:
            logger.error(f"Failed to record decision result: {e}")
            return False

    async def _adapt_parameters(self, decision: Dict[str, Any]) -> None:
        """根据决策结果调整参数

        Args:
            decision: 决策记录
        """
        try:
            success = decision.get('success', False)
            profit = decision.get('profit', 0.0)
            confidence = decision.get('confidence', 0.5)
            risk_level = decision.get('risk_level', 'medium')
            
            # 计算奖励/惩罚
            if success:
                # 成功时的奖励
                reward = profit * self.reward_factor
                # 增加对应风险等级的阈值，鼓励更多类似决策
                if risk_level in self.risk_thresholds:
                    self.risk_thresholds[risk_level] *= (1 + self.learning_rate * 0.5)
                # 降低置信度阈值，鼓励更多决策
                self.confidence_threshold *= (1 - self.learning_rate * 0.3)
            else:
                # 失败时的惩罚
                penalty = abs(profit) * self.penalty_factor
                # 降低对应风险等级的阈值，减少类似决策
                if risk_level in self.risk_thresholds:
                    self.risk_thresholds[risk_level] *= (1 - self.learning_rate * 0.5)
                # 提高置信度阈值，减少决策频率
                self.confidence_threshold *= (1 + self.learning_rate * 0.3)
            
            # 确保参数在合理范围内
            self._normalize_parameters()
            
            logger.debug(f"Adapted parameters: confidence_threshold={self.confidence_threshold}, risk_thresholds={self.risk_thresholds}")
        except Exception as e:
            logger.error(f"Error adapting parameters: {e}")

    def _normalize_parameters(self) -> None:
        """确保参数在合理范围内"""
        # 确保置信度阈值在0.3-0.9之间
        self.confidence_threshold = max(0.3, min(0.9, self.confidence_threshold))
        
        # 确保风险阈值递增且在合理范围内
        thresholds = ['low', 'medium', 'high', 'extreme']
        min_values = [0.1, 0.3, 0.6, 0.9]
        max_values = [0.3, 0.6, 0.9, 1.5]
        
        for i, level in enumerate(thresholds):
            if level in self.risk_thresholds:
                self.risk_thresholds[level] = max(min_values[i], min(max_values[i], self.risk_thresholds[level]))
            
            # 确保阈值递增
            if i > 0:
                prev_level = thresholds[i-1]
                if self.risk_thresholds[level] <= self.risk_thresholds[prev_level]:
                    self.risk_thresholds[level] = self.risk_thresholds[prev_level] + 0.1

    async def get_learning_stats(self) -> Dict[str, Any]:
        """获取学习统计信息

        Returns:
            Dict[str, Any]: 学习统计信息
        """
        try:
            total_decisions = len(self.decision_history)
            successful_decisions = sum(1 for d in self.decision_history if d.get('success', False))
            total_profit = sum(d.get('profit', 0.0) for d in self.decision_history)
            
            if total_decisions > 0:
                success_rate = successful_decisions / total_decisions
                avg_profit = total_profit / total_decisions
            else:
                success_rate = 0.0
                avg_profit = 0.0
            
            return {
                "total_decisions": total_decisions,
                "successful_decisions": successful_decisions,
                "success_rate": success_rate,
                "total_profit": total_profit,
                "average_profit": avg_profit,
                "current_parameters": {
                    "confidence_threshold": self.confidence_threshold,
                    "risk_thresholds": self.risk_thresholds
                }
            }
        except Exception as e:
            logger.error(f"Error getting learning stats: {e}")
            return {}
