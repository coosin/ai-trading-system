from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

from src.modules.core.database_manager import DatabaseManager

logger = logging.getLogger(__name__)


class SentimentType(Enum):
    """情感类型"""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


@dataclass
class SentimentResult:
    """情感分析结果"""
    sentiment: SentimentType
    score: float  # -1.0 到 1.0
    confidence: float  # 0.0 到 1.0
    source: str
    timestamp: float
    text: str
    metadata: Dict[str, Any]


class SentimentAnalyzer:
    """情感分析模块"""

    def __init__(self, db_manager: DatabaseManager, config: Dict[str, Any]):
        """初始化情感分析器

        Args:
            db_manager: 数据库管理器
            config: 配置信息
        """
        self.db_manager = db_manager
        self.config = config
        self.sources = config.get("sources", [
            "twitter",
            "reddit",
            "news",
            "telegram"
        ])
        self.model_config = config.get("model_config", {
            "threshold": 0.3,
            "window_size": 60,
            "min_confidence": 0.5
        })
        self.sentiment_history = {}
        self.enabled = False

    async def initialize(self) -> bool:
        """初始化情感分析器

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 初始化情感历史
            for source in self.sources:
                self.sentiment_history[source] = []
            
            self.enabled = True
            logger.info("SentimentAnalyzer initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize SentimentAnalyzer: {e}")
            return False

    async def shutdown(self) -> bool:
        """关闭情感分析器

        Returns:
            bool: 关闭是否成功
        """
        try:
            self.enabled = False
            self.sentiment_history.clear()
            logger.info("SentimentAnalyzer shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown SentimentAnalyzer: {e}")
            return False

    async def analyze_text(self, text: str, source: str = "unknown") -> Optional[SentimentResult]:
        """分析文本情感

        Args:
            text: 要分析的文本
            source: 文本来源

        Returns:
            Optional[SentimentResult]: 情感分析结果
        """
        if not self.enabled:
            logger.warning("SentimentAnalyzer is not enabled")
            return None

        try:
            # 这里应该使用实际的情感分析模型
            # 暂时使用模拟结果
            score = self._mock_sentiment_score(text)
            sentiment = self._score_to_sentiment(score)
            confidence = self._calculate_confidence(score)
            
            result = SentimentResult(
                sentiment=sentiment,
                score=score,
                confidence=confidence,
                source=source,
                timestamp=asyncio.get_event_loop().time(),
                text=text,
                metadata={}
            )
            
            # 记录情感历史
            await self._record_sentiment(result)
            
            return result
        except Exception as e:
            logger.error(f"Error analyzing text sentiment: {e}")
            return None

    async def analyze_batch(self, texts: List[Tuple[str, str]]) -> List[SentimentResult]:
        """批量分析文本情感

        Args:
            texts: 文本和来源的列表

        Returns:
            List[SentimentResult]: 情感分析结果列表
        """
        results = []
        for text, source in texts:
            result = await self.analyze_text(text, source)
            if result:
                results.append(result)
        return results

    async def get_sentiment_trend(self, source: Optional[str] = None, window: int = 60) -> Dict[str, Any]:
        """获取情感趋势

        Args:
            source: 来源，如果为None则分析所有来源
            window: 时间窗口（分钟）

        Returns:
            Dict[str, Any]: 情感趋势数据
        """
        try:
            current_time = asyncio.get_event_loop().time()
            window_seconds = window * 60
            
            if source:
                if source not in self.sentiment_history:
                    return {}
                sentiments = self.sentiment_history[source]
            else:
                # 合并所有来源的情感
                sentiments = []
                for src_sentiments in self.sentiment_history.values():
                    sentiments.extend(src_sentiments)
            
            # 过滤时间窗口内的情感
            recent_sentiments = [
                s for s in sentiments
                if current_time - s.timestamp <= window_seconds
            ]
            
            if not recent_sentiments:
                return {
                    "average_score": 0.0,
                    "dominant_sentiment": SentimentType.NEUTRAL.value,
                    "total_analyzed": 0,
                    "trend": "stable"
                }
            
            # 计算统计数据
            scores = [s.score for s in recent_sentiments]
            average_score = sum(scores) / len(scores)
            
            # 计算主导情感
            sentiment_counts = {
                SentimentType.POSITIVE: 0,
                SentimentType.NEUTRAL: 0,
                SentimentType.NEGATIVE: 0
            }
            for s in recent_sentiments:
                sentiment_counts[s.sentiment] += 1
            
            dominant_sentiment = max(sentiment_counts, key=sentiment_counts.get)
            
            # 计算趋势
            if len(scores) >= 2:
                trend = "improving" if scores[-1] > scores[0] else "worsening"
            else:
                trend = "stable"
            
            return {
                "average_score": average_score,
                "dominant_sentiment": dominant_sentiment.value,
                "total_analyzed": len(recent_sentiments),
                "trend": trend,
                "sentiment_distribution": {
                    "positive": sentiment_counts[SentimentType.POSITIVE],
                    "neutral": sentiment_counts[SentimentType.NEUTRAL],
                    "negative": sentiment_counts[SentimentType.NEGATIVE]
                }
            }
        except Exception as e:
            logger.error(f"Error getting sentiment trend: {e}")
            return {}

    async def get_market_sentiment(self) -> Dict[str, Any]:
        """获取市场整体情感

        Returns:
            Dict[str, Any]: 市场情感数据
        """
        try:
            # 分析所有来源的情感
            all_trends = await self.get_sentiment_trend(window=1440)  # 24小时
            
            # 计算市场情绪指标
            market_sentiment = {
                "overall": all_trends.get("average_score", 0.0),
                "dominant": all_trends.get("dominant_sentiment", "neutral"),
                "confidence": self._calculate_market_confidence(all_trends),
                "trend": all_trends.get("trend", "stable"),
                "sources": {}
            }
            
            # 按来源分析
            for source in self.sources:
                source_trend = await self.get_sentiment_trend(source=source, window=1440)
                market_sentiment["sources"][source] = source_trend
            
            return market_sentiment
        except Exception as e:
            logger.error(f"Error getting market sentiment: {e}")
            return {}

    def _mock_sentiment_score(self, text: str) -> float:
        """模拟情感得分

        Args:
            text: 文本

        Returns:
            float: 情感得分
        """
        # 简单的关键词匹配
        positive_words = ["good", "great", "excellent", "positive", "bullish", "rise", "up", "gain"]
        negative_words = ["bad", "terrible", "poor", "negative", "bearish", "fall", "down", "loss"]
        
        positive_count = sum(1 for word in positive_words if word in text.lower())
        negative_count = sum(1 for word in negative_words if word in text.lower())
        
        if positive_count > negative_count:
            return 0.5 + (positive_count - negative_count) * 0.1
        elif negative_count > positive_count:
            return -0.5 - (negative_count - positive_count) * 0.1
        else:
            return 0.0

    def _score_to_sentiment(self, score: float) -> SentimentType:
        """将得分转换为情感类型

        Args:
            score: 情感得分

        Returns:
            SentimentType: 情感类型
        """
        threshold = self.model_config.get("threshold", 0.3)
        if score > threshold:
            return SentimentType.POSITIVE
        elif score < -threshold:
            return SentimentType.NEGATIVE
        else:
            return SentimentType.NEUTRAL

    def _calculate_confidence(self, score: float) -> float:
        """计算置信度

        Args:
            score: 情感得分

        Returns:
            float: 置信度
        """
        # 基于得分的绝对值计算置信度
        return min(abs(score) * 2, 1.0)

    def _calculate_market_confidence(self, trend_data: Dict[str, Any]) -> float:
        """计算市场置信度

        Args:
            trend_data: 趋势数据

        Returns:
            float: 市场置信度
        """
        total_analyzed = trend_data.get("total_analyzed", 0)
        if total_analyzed == 0:
            return 0.0
        
        # 基于分析数量和情感一致性计算置信度
        max_count = max(trend_data.get("sentiment_distribution", {}).values())
        consistency = max_count / total_analyzed
        
        # 分析数量越多，置信度越高
        volume_factor = min(total_analyzed / 100, 1.0)
        
        return consistency * volume_factor

    async def _record_sentiment(self, result: SentimentResult) -> bool:
        """记录情感分析结果

        Args:
            result: 情感分析结果

        Returns:
            bool: 记录是否成功
        """
        try:
            # 记录到历史
            if result.source not in self.sentiment_history:
                self.sentiment_history[result.source] = []
            
            self.sentiment_history[result.source].append(result)
            
            # 限制历史记录数量
            window_size = self.model_config.get("window_size", 60)
            if len(self.sentiment_history[result.source]) > window_size:
                self.sentiment_history[result.source] = self.sentiment_history[result.source][-window_size:]
            
            # 这里应该将结果记录到数据库
            # 暂时使用日志记录
            logger.debug(f"Sentiment recorded: {result}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to record sentiment: {e}")
            return False

    def is_healthy(self) -> bool:
        """检查情感分析器健康状态

        Returns:
            bool: 健康状态
        """
        return self.enabled
