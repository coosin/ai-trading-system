import asyncio
import pytest
from unittest.mock import Mock, MagicMock
from src.modules.intelligence.sentiment_analyzer.analyzer import (
    SentimentAnalyzer, SentimentType, SentimentResult
)


class TestSentimentAnalyzer:
    """情感分析器测试类"""

    @pytest.fixture
    def db_manager(self):
        """数据库管理器fixture"""
        return Mock()

    @pytest.fixture
    def config(self):
        """配置fixture"""
        return {
            "sources": ["twitter", "reddit", "news"],
            "model_config": {
                "threshold": 0.3,
                "window_size": 60,
                "min_confidence": 0.5
            }
        }

    @pytest.fixture
    def sentiment_analyzer(self, db_manager, config):
        """情感分析器fixture"""
        analyzer = SentimentAnalyzer(db_manager, config)
        return analyzer

    @pytest.mark.asyncio
    async def test_initialization(self, sentiment_analyzer):
        """测试初始化"""
        result = await sentiment_analyzer.initialize()
        assert result is True
        assert sentiment_analyzer.enabled is True
        assert "twitter" in sentiment_analyzer.sentiment_history
        assert "reddit" in sentiment_analyzer.sentiment_history
        assert "news" in sentiment_analyzer.sentiment_history

    @pytest.mark.asyncio
    async def test_shutdown(self, sentiment_analyzer):
        """测试关闭"""
        await sentiment_analyzer.initialize()
        result = await sentiment_analyzer.shutdown()
        assert result is True
        assert sentiment_analyzer.enabled is False
        assert len(sentiment_analyzer.sentiment_history) == 0

    @pytest.mark.asyncio
    async def test_analyze_text_disabled(self, sentiment_analyzer):
        """测试禁用状态下的文本分析"""
        result = await sentiment_analyzer.analyze_text("This is a test")
        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_text_positive(self, sentiment_analyzer):
        """测试积极情感分析"""
        await sentiment_analyzer.initialize()
        result = await sentiment_analyzer.analyze_text("This is great!", "twitter")
        assert result is not None
        assert isinstance(result, SentimentResult)
        assert result.sentiment == SentimentType.POSITIVE
        assert result.score > 0
        assert result.confidence > 0
        assert result.source == "twitter"

    @pytest.mark.asyncio
    async def test_analyze_text_negative(self, sentiment_analyzer):
        """测试消极情感分析"""
        await sentiment_analyzer.initialize()
        result = await sentiment_analyzer.analyze_text("This is bad!", "reddit")
        assert result is not None
        assert isinstance(result, SentimentResult)
        assert result.sentiment == SentimentType.NEGATIVE
        assert result.score < 0
        assert result.confidence > 0
        assert result.source == "reddit"

    @pytest.mark.asyncio
    async def test_analyze_text_neutral(self, sentiment_analyzer):
        """测试中性情感分析"""
        await sentiment_analyzer.initialize()
        result = await sentiment_analyzer.analyze_text("This is a test", "news")
        assert result is not None
        assert isinstance(result, SentimentResult)
        assert result.sentiment == SentimentType.NEUTRAL
        assert result.score == 0
        assert result.confidence == 0
        assert result.source == "news"

    @pytest.mark.asyncio
    async def test_analyze_batch(self, sentiment_analyzer):
        """测试批量分析"""
        await sentiment_analyzer.initialize()
        texts = [
            ("This is great!", "twitter"),
            ("This is bad!", "reddit"),
            ("This is a test", "news")
        ]
        results = await sentiment_analyzer.analyze_batch(texts)
        assert len(results) == 3
        assert all(isinstance(r, SentimentResult) for r in results)

    @pytest.mark.asyncio
    async def test_get_sentiment_trend(self, sentiment_analyzer):
        """测试获取情感趋势"""
        await sentiment_analyzer.initialize()
        
        # 分析一些文本
        await sentiment_analyzer.analyze_text("This is great!", "twitter")
        await sentiment_analyzer.analyze_text("This is good!", "twitter")
        await sentiment_analyzer.analyze_text("This is bad!", "twitter")
        
        trend = await sentiment_analyzer.get_sentiment_trend(source="twitter")
        assert isinstance(trend, dict)
        assert "average_score" in trend
        assert "dominant_sentiment" in trend
        assert "total_analyzed" in trend
        assert "trend" in trend
        assert "sentiment_distribution" in trend

    @pytest.mark.asyncio
    async def test_get_sentiment_trend_all_sources(self, sentiment_analyzer):
        """测试获取所有来源的情感趋势"""
        await sentiment_analyzer.initialize()
        
        # 分析一些文本
        await sentiment_analyzer.analyze_text("This is great!", "twitter")
        await sentiment_analyzer.analyze_text("This is bad!", "reddit")
        
        trend = await sentiment_analyzer.get_sentiment_trend()
        assert isinstance(trend, dict)
        assert "average_score" in trend
        assert "total_analyzed" in trend
        assert trend["total_analyzed"] == 2

    @pytest.mark.asyncio
    async def test_get_market_sentiment(self, sentiment_analyzer):
        """测试获取市场情感"""
        await sentiment_analyzer.initialize()
        
        # 分析一些文本
        await sentiment_analyzer.analyze_text("This is great!", "twitter")
        await sentiment_analyzer.analyze_text("This is good!", "reddit")
        await sentiment_analyzer.analyze_text("This is positive!", "news")
        
        market_sentiment = await sentiment_analyzer.get_market_sentiment()
        assert isinstance(market_sentiment, dict)
        assert "overall" in market_sentiment
        assert "dominant" in market_sentiment
        assert "confidence" in market_sentiment
        assert "trend" in market_sentiment
        assert "sources" in market_sentiment

    def test_score_to_sentiment(self, sentiment_analyzer):
        """测试得分转换为情感类型"""
        assert sentiment_analyzer._score_to_sentiment(0.5) == SentimentType.POSITIVE
        assert sentiment_analyzer._score_to_sentiment(-0.5) == SentimentType.NEGATIVE
        assert sentiment_analyzer._score_to_sentiment(0.1) == SentimentType.NEUTRAL
        assert sentiment_analyzer._score_to_sentiment(-0.1) == SentimentType.NEUTRAL

    def test_calculate_confidence(self, sentiment_analyzer):
        """测试计算置信度"""
        assert sentiment_analyzer._calculate_confidence(0.5) == 1.0
        assert sentiment_analyzer._calculate_confidence(-0.5) == 1.0
        assert sentiment_analyzer._calculate_confidence(0.3) == 0.6
        assert sentiment_analyzer._calculate_confidence(0) == 0

    def test_calculate_market_confidence(self, sentiment_analyzer):
        """测试计算市场置信度"""
        trend_data = {
            "total_analyzed": 100,
            "sentiment_distribution": {
                "positive": 70,
                "neutral": 20,
                "negative": 10
            }
        }
        confidence = sentiment_analyzer._calculate_market_confidence(trend_data)
        assert confidence > 0.6
        assert confidence <= 1.0

    def test_is_healthy(self, sentiment_analyzer):
        """测试健康状态"""
        assert sentiment_analyzer.is_healthy() is False
        
        # 初始化后应该健康
        asyncio.run(sentiment_analyzer.initialize())
        assert sentiment_analyzer.is_healthy() is True
