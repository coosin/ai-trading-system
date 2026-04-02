"""
AI模块记忆集成接口
连接AI模块与统一记忆系统
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .unified_intelligent_memory import (
    UnifiedIntelligentMemory,
    UnifiedMemoryType,
    MemoryPriority,
    get_unified_memory
)

logger = logging.getLogger(__name__)


class AIMemoryIntegration:
    """
    AI模块记忆集成接口
    
    为各个AI模块提供统一的记忆访问接口
    """
    
    def __init__(self, memory_system: UnifiedIntelligentMemory = None):
        self.memory = memory_system or get_unified_memory()
    
    async def record_dl_prediction(
        self,
        symbol: str,
        model_type: str,
        prediction: Dict[str, Any],
        confidence: float,
        features_used: List[str] = None
    ) -> Optional[str]:
        """记录深度学习预测"""
        return await self.memory.add_ai_prediction(
            prediction_type=f"deep_learning_{model_type}",
            symbol=symbol,
            prediction=prediction,
            confidence=confidence,
            model_info={
                "model_type": model_type,
                "features_used": features_used or []
            }
        )
    
    async def record_rl_action(
        self,
        symbol: str,
        state: Dict[str, Any],
        action: str,
        reward: float,
        q_value: float = None
    ) -> Optional[str]:
        """记录强化学习动作"""
        content = f"RL动作 [{symbol}]: {action}, 奖励: {reward:.4f}"
        if q_value is not None:
            content += f", Q值: {q_value:.4f}"
        
        return await self.memory.add_memory(
            memory_type=UnifiedMemoryType.RL_OPTIMIZATION,
            content=content,
            summary=f"{symbol} RL决策: {action}",
            metadata={
                "symbol": symbol,
                "action": action,
                "reward": reward,
                "q_value": q_value
            },
            source_module="rl_agent",
            tags=[symbol, "rl_action"]
        )
    
    async def record_strategy_optimization(
        self,
        strategy_name: str,
        optimization_type: str,
        old_params: Dict[str, Any],
        new_params: Dict[str, Any],
        backtest_improvement: float,
        reason: str = ""
    ) -> Optional[str]:
        """记录策略优化"""
        return await self.memory.add_rl_optimization(
            strategy_name=strategy_name,
            old_params=old_params,
            new_params=new_params,
            improvement=backtest_improvement,
            reason=reason
        )
    
    async def record_model_training_result(
        self,
        model_id: str,
        model_type: str,
        training_metrics: Dict[str, float],
        validation_metrics: Dict[str, float],
        training_duration: float = None
    ) -> Optional[str]:
        """记录模型训练结果"""
        return await self.memory.add_model_training(
            model_id=model_id,
            model_type=model_type,
            metrics={
                "training": training_metrics,
                "validation": validation_metrics,
                "duration_seconds": training_duration
            }
        )
    
    async def record_model_deployment(
        self,
        model_id: str,
        old_version: str,
        new_version: str,
        deployment_type: str,
        performance_comparison: Dict[str, float]
    ) -> Optional[str]:
        """记录模型部署"""
        return await self.memory.add_model_update(
            model_id=model_id,
            update_type=deployment_type,
            old_version=old_version,
            new_version=new_version,
            performance_change=performance_comparison
        )
    
    async def record_onchain_analysis(
        self,
        symbol: str,
        metrics: Dict[str, Any],
        sentiment: str,
        key_insights: List[str]
    ) -> Optional[str]:
        """记录链上数据分析"""
        insights_text = "; ".join(key_insights[:3]) if key_insights else ""
        return await self.memory.add_onchain_data(
            symbol=symbol,
            onchain_metrics=metrics,
            insights=f"{sentiment}: {insights_text}"
        )
    
    async def record_social_sentiment(
        self,
        symbol: str,
        sentiment_score: float,
        sources: Dict[str, float],
        trending_topics: List[str] = None
    ) -> Optional[str]:
        """记录社交媒体情绪"""
        return await self.memory.add_market_sentiment(
            symbol=symbol,
            sentiment_data={
                "overall": sentiment_score,
                "sources": sources,
                "trending": trending_topics or []
            },
            sources=list(sources.keys())
        )
    
    async def record_news_impact(
        self,
        symbol: str,
        news_title: str,
        sentiment: float,
        impact_score: float,
        source: str
    ) -> Optional[str]:
        """记录新闻影响"""
        content = f"新闻 [{source}]: {news_title}"
        return await self.memory.add_memory(
            memory_type=UnifiedMemoryType.NEWS_ANALYSIS,
            content=content,
            summary=f"{symbol} 新闻: {news_title[:100]}",
            metadata={
                "symbol": symbol,
                "sentiment": sentiment,
                "impact_score": impact_score,
                "source": source
            },
            source_module="news_analyzer",
            tags=[symbol, "news", source]
        )
    
    async def record_generated_strategy(
        self,
        strategy_name: str,
        strategy_type: str,
        rules: Dict[str, Any],
        backtest_results: Dict[str, float],
        generation_reason: str
    ) -> Optional[str]:
        """记录AI生成的策略"""
        content = f"AI生成策略 [{strategy_name}]: {strategy_type}"
        return await self.memory.add_memory(
            memory_type=UnifiedMemoryType.STRATEGY_GENERATED,
            content=content,
            summary=f"生成策略: {strategy_name} ({strategy_type})",
            metadata={
                "strategy_name": strategy_name,
                "strategy_type": strategy_type,
                "rules": rules,
                "backtest_results": backtest_results,
                "generation_reason": generation_reason
            },
            source_module="ai_strategy_generator",
            tags=[strategy_name, strategy_type, "ai_generated"]
        )
    
    async def get_relevant_predictions(
        self,
        symbol: str,
        prediction_type: str = None,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """获取相关预测记录"""
        mem_type = None
        if prediction_type:
            if "deep_learning" in prediction_type or "dl" in prediction_type:
                mem_type = UnifiedMemoryType.DL_PREDICTION
            elif "rl" in prediction_type:
                mem_type = UnifiedMemoryType.RL_OPTIMIZATION
            else:
                mem_type = UnifiedMemoryType.AI_PREDICTION
        
        memories = await self.memory.retrieve_memories(
            query=symbol,
            memory_types=[mem_type] if mem_type else [UnifiedMemoryType.AI_PREDICTION, UnifiedMemoryType.DL_PREDICTION],
            limit=10
        )
        
        results = []
        cutoff = datetime.now().timestamp() - hours * 3600
        
        for mem in memories:
            if mem.created_at.timestamp() >= cutoff:
                results.append({
                    "id": mem.id,
                    "summary": mem.summary,
                    "metadata": mem.metadata,
                    "created_at": mem.created_at.isoformat(),
                    "importance": mem.importance_score
                })
        
        return results
    
    async def get_strategy_history(
        self,
        strategy_name: str = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """获取策略优化历史"""
        memories = await self.memory.retrieve_memories(
            query=strategy_name or "",
            memory_types=[UnifiedMemoryType.RL_OPTIMIZATION, UnifiedMemoryType.STRATEGY_GENERATED],
            limit=limit
        )
        
        return [
            {
                "id": mem.id,
                "summary": mem.summary,
                "metadata": mem.metadata,
                "created_at": mem.created_at.isoformat()
            }
            for mem in memories
        ]
    
    async def get_model_history(
        self,
        model_id: str = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """获取模型历史"""
        memories = await self.memory.retrieve_memories(
            query=model_id or "",
            memory_types=[UnifiedMemoryType.MODEL_TRAINING, UnifiedMemoryType.MODEL_UPDATE],
            limit=limit
        )
        
        return [
            {
                "id": mem.id,
                "summary": mem.summary,
                "metadata": mem.metadata,
                "created_at": mem.created_at.isoformat()
            }
            for mem in memories
        ]
    
    async def get_market_context(
        self,
        symbol: str
    ) -> Dict[str, Any]:
        """获取市场上下文（用于AI决策）"""
        predictions = await self.get_relevant_predictions(symbol, hours=48)
        
        sentiment_mems = await self.memory.retrieve_memories(
            query=symbol,
            memory_types=[UnifiedMemoryType.SOCIAL_SENTIMENT],
            limit=3
        )
        
        onchain_mems = await self.memory.retrieve_memories(
            query=symbol,
            memory_types=[UnifiedMemoryType.ONCHAIN_DATA],
            limit=3
        )
        
        news_mems = await self.memory.retrieve_memories(
            query=symbol,
            memory_types=[UnifiedMemoryType.NEWS_ANALYSIS],
            limit=5
        )
        
        return {
            "symbol": symbol,
            "predictions": predictions,
            "social_sentiment": [
                {"summary": m.summary, "metadata": m.metadata}
                for m in sentiment_mems
            ],
            "onchain_data": [
                {"summary": m.summary, "metadata": m.metadata}
                for m in onchain_mems
            ],
            "recent_news": [
                {"summary": m.summary, "metadata": m.metadata}
                for m in news_mems
            ]
        }
    
    async def build_ai_context(
        self,
        symbol: str = None,
        task_type: str = "trading"
    ) -> str:
        """构建AI上下文（用于LLM提示）"""
        return await self.memory.get_trading_context(symbol)


ai_memory_integration = AIMemoryIntegration()
