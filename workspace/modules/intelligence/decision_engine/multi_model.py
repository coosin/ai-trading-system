#!/usr/bin/env python3
"""
多模型决策引擎
融合多个AI模型进行交易决策
"""

import asyncio
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import json
from datetime import datetime

class Decision(Enum):
    """决策类型"""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"

class SignalConfidence(Enum):
    """信号置信度"""
    VERY_HIGH = 0.9
    HIGH = 0.7
    MEDIUM = 0.5
    LOW = 0.3
    VERY_LOW = 0.1

@dataclass
class ModelOutput:
    """模型输出"""
    decision: Decision
    confidence: float
    reasoning: str
    model_name: str
    timestamp: datetime
    
@dataclass  
class TradingSignal:
    """交易信号"""
    symbol: str
    decision: Decision
    confidence: float
    reasoning: str
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    suggested_position_size: Optional[float] = None
    time_horizon: str = "short_term"  # short_term, medium_term, long_term

class BaseTradingModel:
    """交易模型基类"""
    
    def __init__(self, name: str, weight: float = 1.0):
        self.name = name
        self.weight = weight
        self.history = []
        
    async def analyze(self, market_data: Dict, portfolio: Dict = None) -> ModelOutput:
        """分析市场并生成决策"""
        raise NotImplementedError
    
    def update_weight(self, performance_score: float):
        """根据表现更新模型权重"""
        # 表现越好权重越高，但避免极端值
        adjustment = (performance_score - 0.5) * 0.1
        self.weight = max(0.1, min(2.0, self.weight + adjustment))
        
class TechnicalAnalysisModel(BaseTradingModel):
    """技术分析模型"""
    
    def __init__(self):
        super().__init__("TechnicalAnalysis", weight=1.0)
        self.indicators = {}
        
    async def analyze(self, market_data: Dict, portfolio: Dict = None) -> ModelOutput:
        """技术分析"""
        
        indicators = market_data.get('indicators', {})
        
        # 计算技术信号
        signals = []
        reasoning_parts = []
        
        # 趋势分析
        if indicators.get('sma_20') and indicators.get('sma_50'):
            if indicators['sma_20'] > indicators['sma_50']:
                signals.append(1.0)  # 看涨
                reasoning_parts.append("短期均线上穿长期均线，趋势向上")
            else:
                signals.append(-1.0)  # 看跌
                reasoning_parts.append("短期均线下穿长期均线，趋势向下")
        
        # RSI分析
        rsi = indicators.get('rsi')
        if rsi:
            if rsi < 30:
                signals.append(1.0)  # 超卖，看涨
                reasoning_parts.append(f"RSI={rsi:.1f}，处于超卖区间")
            elif rsi > 70:
                signals.append(-1.0)  # 超买，看跌
                reasoning_parts.append(f"RSI={rsi:.1f}，处于超买区间")
            else:
                signals.append(0.0)
        
        # MACD分析
        macd = indicators.get('macd')
        if macd:
            if macd > 0:
                signals.append(0.5)  # 看涨
                reasoning_parts.append("MACD为正，多头信号")
            else:
                signals.append(-0.5)  # 看跌
                reasoning_parts.append("MACD为负，空头信号")
        
        # 布林带分析
        close = market_data.get('close')
        bb_upper = indicators.get('bb_upper')
        bb_lower = indicators.get('bb_lower')
        
        if close and bb_upper and bb_lower:
            if close <= bb_lower:
                signals.append(0.8)  # 强烈看涨
                reasoning_parts.append("价格触及布林带下轨，反弹概率大")
            elif close >= bb_upper:
                signals.append(-0.8)  # 强烈看跌
                reasoning_parts.append("价格触及布林带上轨，回调概率大")
        
        if not signals:
            decision = Decision.HOLD
            confidence = 0.3
            reasoning = "技术指标信号不明确"
        else:
            avg_signal = np.mean(signals)
            
            if avg_signal > 0.4:
                decision = Decision.STRONG_BUY
                confidence = min(0.9, 0.5 + abs(avg_signal))
            elif avg_signal > 0.1:
                decision = Decision.BUY
                confidence = 0.5 + abs(avg_signal) * 0.4
            elif avg_signal < -0.4:
                decision = Decision.STRONG_SELL
                confidence = min(0.9, 0.5 + abs(avg_signal))
            elif avg_signal < -0.1:
                decision = Decision.SELL
                confidence = 0.5 + abs(avg_signal) * 0.4
            else:
                decision = Decision.HOLD
                confidence = 0.5
            
            reasoning = " | ".join(reasoning_parts) if reasoning_parts else "技术分析信号"
        
        return ModelOutput(
            decision=decision,
            confidence=confidence,
            reasoning=reasoning,
            model_name=self.name,
            timestamp=datetime.now()
        )

class SentimentAnalysisModel(BaseTradingModel):
    """市场情绪分析模型"""
    
    def __init__(self):
        super().__init__("SentimentAnalysis", weight=0.8)
        
    async def analyze(self, market_data: Dict, portfolio: Dict = None) -> ModelOutput:
        """情绪分析"""
        
        # 模拟情绪数据（实际应该从API获取）
        sentiment_data = {
            'social_media': self._get_social_media_sentiment(),
            'news_sentiment': self._get_news_sentiment(),
            'fear_greed_index': self._get_fear_greed_index()
        }
        
        # 计算情绪得分
        sentiment_score = np.mean([
            sentiment_data['social_media'],
            sentiment_data['news_sentiment'],
            (100 - sentiment_data['fear_greed_index']) / 100  # 反转处理
        ])
        
        # 映射到决策
        if sentiment_score > 0.7:
            decision = Decision.BUY
            confidence = min(0.8, sentiment_score)
            reasoning = "市场情绪积极，多头氛围浓厚"
        elif sentiment_score > 0.6:
            decision = Decision.BUY
            confidence = 0.6
            reasoning = "市场情绪偏积极"
        elif sentiment_score < 0.3:
            decision = Decision.SELL
            confidence = min(0.8, 1 - sentiment_score)
            reasoning = "市场情绪悲观，空头氛围浓厚"
        elif sentiment_score < 0.4:
            decision = Decision.SELL
            confidence = 0.6
            reasoning = "市场情绪偏悲观"
        else:
            decision = Decision.HOLD
            confidence = 0.5
            reasoning = "市场情绪中性"
        
        reasoning += f" (情绪得分: {sentiment_score:.2f})"
        
        return ModelOutput(
            decision=decision,
            confidence=confidence,
            reasoning=reasoning,
            model_name=self.name,
            timestamp=datetime.now()
        )
    
    def _get_social_media_sentiment(self) -> float:
        """获取社交媒体情绪"""
        # 模拟数据
        return np.random.uniform(0.3, 0.8)
    
    def _get_news_sentiment(self) -> float:
        """获取新闻情绪"""
        # 模拟数据
        return np.random.uniform(0.4, 0.9)
    
    def _get_fear_greed_index(self) -> float:
        """获取恐惧贪婪指数"""
        # 模拟数据
        return np.random.uniform(20, 80)

class RiskAwareModel(BaseTradingModel):
    """风险感知模型"""
    
    def __init__(self):
        super().__init__("RiskAware", weight=1.2)
        
    async def analyze(self, market_data: Dict, portfolio: Dict = None) -> ModelOutput:
        """风险感知分析"""
        
        volatility = market_data.get('volatility', 0.02)
        position_size = portfolio.get('position_size', 0) if portfolio else 0
        max_position = portfolio.get('max_position', 0.3) if portfolio else 0.3
        
        # 风险计算
        risk_score = self._calculate_risk_score(volatility, position_size, max_position)
        
        # 风险调整决策
        if risk_score > 0.7:
            decision = Decision.STRONG_SELL if position_size > 0 else Decision.STRONG_BUY
            confidence = 0.8
            reasoning = f"风险水平低(得分:{risk_score:.2f})，建议"
            reasoning += "减仓" if position_size > 0 else "增仓"
        elif risk_score > 0.5:
            decision = Decision.SELL if position_size > 0 else Decision.BUY
            confidence = 0.7
            reasoning = f"风险水平适中(得分:{risk_score:.2f})"
        elif risk_score > 0.3:
            decision = Decision.HOLD
            confidence = 0.6
            reasoning = f"风险水平较高(得分:{risk_score:.2f})，建议观望"
        else:
            decision = Decision.STRONG_SELL if position_size > 0 else Decision.HOLD
            confidence = 0.8
            reasoning = f"风险水平极高(得分:{risk_score:.2f})，建议清仓"
        
        reasoning += f"，波动率:{volatility:.2%}，仓位:{position_size:.1%}"
        
        return ModelOutput(
            decision=decision,
            confidence=confidence,
            reasoning=reasoning,
            model_name=self.name,
            timestamp=datetime.now()
        )
    
    def _calculate_risk_score(self, volatility: float, position_size: float, max_position: float) -> float:
        """计算风险得分"""
        
        # 波动率风险 (越高风险越大)
        vol_risk = 1.0 - min(volatility * 10, 1.0)
        
        # 仓位风险 (仓位越重风险越大)
        position_risk = 1.0 - (position_size / max_position)
        
        # 组合风险得分
        risk_score = 0.6 * vol_risk + 0.4 * position_risk
        
        return max(0.0, min(1.0, risk_score))

class MultiModelDecisionEngine:
    """多模型决策引擎"""
    
    def __init__(self):
        self.models = {
            'technical': TechnicalAnalysisModel(),
            'sentiment': SentimentAnalysisModel(),
            'risk': RiskAwareModel()
        }
        
        # 模型权重（可动态调整）
        self.model_weights = {
            'technical': 1.0,
            'sentiment': 0.8,
            'risk': 1.2
        }
        
        # 决策历史
        self.decision_history = []
        
    async def analyze_market(self, symbol: str, market_data: Dict, 
                           portfolio: Dict = None) -> Dict[str, ModelOutput]:
        """多模型市场分析"""
        
        model_outputs = {}
        
        # 并行运行所有模型
        tasks = []
        for model_name, model in self.models.items():
            task = model.analyze(market_data, portfolio)
            tasks.append((model_name, task))
        
        # 等待所有模型完成
        for model_name, task in tasks:
            try:
                output = await task
                model_outputs[model_name] = output
            except Exception as e:
                print(f"模型 {model_name} 分析失败: {e}")
                # 使用默认输出
                model_outputs[model_name] = ModelOutput(
                    decision=Decision.HOLD,
                    confidence=0.3,
                    reasoning=f"模型分析失败: {str(e)}",
                    model_name=model_name,
                    timestamp=datetime.now()
                )
        
        return model_outputs
    
    def fuse_decisions(self, model_outputs: Dict[str, ModelOutput]) -> TradingSignal:
        """融合多个模型决策"""
        
        if not model_outputs:
            return self._create_default_signal()
        
        # 决策映射到数值
        decision_values = {
            Decision.STRONG_BUY: 2.0,
            Decision.BUY: 1.0,
            Decision.HOLD: 0.0,
            Decision.SELL: -1.0,
            Decision.STRONG_SELL: -2.0
        }
        
        weighted_decisions = []
        confidence_sum = 0
        reasoning_parts = []
        total_weight = 0
        
        for model_name, output in model_outputs.items():
            weight = self.model_weights.get(model_name, 1.0)
            decision_value = decision_values[output.decision]
            
            # 加权决策值
            weighted_value = decision_value * weight * output.confidence
            weighted_decisions.append(weighted_value)
            
            # 累计置信度
            confidence_sum += output.confidence * weight
            
            # 收集推理
            reasoning_parts.append(f"{model_name}: {output.reasoning}")
            
            total_weight += weight
        
        if not weighted_decisions:
            return self._create_default_signal()
        
        # 计算加权平均决策
        avg_decision = np.mean(weighted_decisions)
        avg_confidence = confidence_sum / total_weight if total_weight > 0 else 0.5
        
        # 映射回决策类型
        if avg_decision > 1.5:
            final_decision = Decision.STRONG_BUY
        elif avg_decision > 0.5:
            final_decision = Decision.BUY
        elif avg_decision < -1.5:
            final_decision = Decision.STRONG_SELL
        elif avg_decision < -0.5:
            final_decision = Decision.SELL
        else:
            final_decision = Decision.HOLD
        
        # 生成交易信号
        signal = TradingSignal(
            symbol=next(iter(model_outputs.values())).model_name.split('_')[0],  # 简化处理
            decision=final_decision,
            confidence=avg_confidence,
            reasoning=" | ".join(reasoning_parts)
        )
        
        # 记录决策历史
        self.decision_history.append({
            'timestamp': datetime.now(),
            'signal': signal,
            'model_outputs': {k: {
                'decision': v.decision.value,
                'confidence': v.confidence,
                'reasoning': v.reasoning
            } for k, v in model_outputs.items()}
        })
        
        # 保持历史记录长度
        if len(self.decision_history) > 1000:
            self.decision_history = self.decision_history[-1000:]
        
        return signal
    
    def _create_default_signal(self) -> TradingSignal:
        """创建默认信号"""
        return TradingSignal(
            symbol="BTCUSDT",
            decision=Decision.HOLD,
            confidence=0.3,
            reasoning="无模型输出，使用默认信号"
        )
    
    def update_model_weights(self, performance_data: Dict[str, float]):
        """根据表现更新模型权重"""
        
        for model_name, performance in performance_data.items():
            if model_name in self.models and model_name in self.model_weights:
                # 表现越好权重越高
                weight_adjustment = (performance - 0.5) * 0.2
                new_weight = self.model_weights[model_name] + weight_adjustment
                
                # 限制权重范围
                self.model_weights[model_name] = max(0.1, min(3.0, new_weight))
                
                # 更新模型内部权重
                self.models[model_name].weight = self.model_weights[model_name]
    
    def get_performance_stats(self) -> Dict:
        """获取模型表现统计"""
        
        if not self.decision_history:
            return {}
        
        stats = {}
        recent_history = self.decision_history[-100:]  # 最近100次
        
        for model_name in self.models.keys():
            model_decisions = []
            
            for record in recent_history:
                if model_name in record['model_outputs']:
                    output = record['model_outputs'][model_name]
                    model_decisions.append(output)
            
            if model_decisions:
                avg_confidence = np.mean([d['confidence'] for d in model_decisions])
                decision_distribution = {}
                
                for decision in Decision:
                    count = sum(1 for d in model_decisions if d['decision'] == decision.value)
                    decision_distribution[decision.value] = count / len(model_decisions)
                
                stats[model_name] = {
                    'avg_confidence': avg_confidence,
                    'decision_distribution': decision_distribution,
                    'sample_count': len(model_decisions)
                }
        
        return stats

# 单例实例
_decision_engine = None

def get_decision_engine() -> MultiModelDecisionEngine:
    """获取决策引擎单例"""
    global _decision_engine
    if _decision_engine is None:
        _decision_engine = MultiModelDecisionEngine()
    return _decision_engine