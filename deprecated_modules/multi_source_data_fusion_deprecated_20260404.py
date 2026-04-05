"""
多源数据融合分析器

核心功能：
1. 整合所有第三方数据源的数据
2. 进行综合分析和情绪评估
3. 为AI交易决策提供多维度的市场洞察
4. 自动生成市场分析报告
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import statistics

logger = logging.getLogger(__name__)


class SentimentLevel(Enum):
    """情绪等级"""
    EXTREME_FEAR = "extreme_fear"
    FEAR = "fear"
    NEUTRAL = "neutral"
    GREED = "greed"
    EXTREME_GREED = "extreme_greed"


class SignalStrength(Enum):
    """信号强度"""
    VERY_WEAK = 1
    WEAK = 2
    MODERATE = 3
    STRONG = 4
    VERY_STRONG = 5


@dataclass
class DataSourceAnalysis:
    """单个数据源分析结果"""
    source_name: str
    source_type: str
    data_available: bool
    sentiment: SentimentLevel
    sentiment_score: float  # -1 to 1
    key_findings: List[str] = field(default_factory=list)
    confidence: float = 0.5
    timestamp: datetime = field(default_factory=datetime.now)
    raw_data: Dict = field(default_factory=dict)


@dataclass
class FusedMarketIntelligence:
    """融合后的市场情报"""
    overall_sentiment: SentimentLevel
    overall_sentiment_score: float
    signal_strength: SignalStrength
    
    technical_analysis: Dict
    sentiment_analysis: Dict
    on_chain_analysis: Dict
    news_analysis: Dict
    social_media_analysis: Dict
    
    key_insights: List[str]
    risk_factors: List[str]
    opportunity_signals: List[str]
    
    recommendation: str  # bullish/bearish/neutral
    confidence: float
    
    data_sources_used: List[str]
    data_sources_missing: List[str]
    
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "overall_sentiment": self.overall_sentiment.value,
            "overall_sentiment_score": self.overall_sentiment_score,
            "signal_strength": self.signal_strength.value,
            "technical_analysis": self.technical_analysis,
            "sentiment_analysis": self.sentiment_analysis,
            "on_chain_analysis": self.on_chain_analysis,
            "news_analysis": self.news_analysis,
            "social_media_analysis": self.social_media_analysis,
            "key_insights": self.key_insights,
            "risk_factors": self.risk_factors,
            "opportunity_signals": self.opportunity_signals,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
            "data_sources_used": self.data_sources_used,
            "data_sources_missing": self.data_sources_missing,
            "timestamp": self.timestamp.isoformat()
        }


class MultiSourceDataFusion:
    """
    多源数据融合分析器
    
    整合所有数据源，提供综合市场 intelligence
    """
    
    def __init__(self, data_integration=None, llm_integration=None):
        self.data_integration = data_integration
        self.llm_integration = llm_integration
        
        self.data_sources = {}
        self.analysis_cache: Dict[str, FusedMarketIntelligence] = {}
        
        self.config = {
            "cache_ttl_seconds": 300,
            "min_data_sources_for_signal": 2,
            "sentiment_weights": {
                "technical": 0.35,
                "sentiment": 0.25,
                "on_chain": 0.15,
                "news": 0.15,
                "social_media": 0.10
            }
        }
        
        logger.info("✅ 多源数据融合分析器初始化完成")
    
    async def register_data_source(self, name: str, source_instance) -> None:
        """注册数据源"""
        try:
            metadata = await source_instance.get_metadata()
            self.data_sources[name] = {
                "instance": source_instance,
                "metadata": metadata,
                "last_fetch": None,
                "last_error": None
            }
            logger.info(f"📡 注册数据源: {name} ({metadata.get('type', 'unknown')})")
        except Exception as e:
            logger.error(f"注册数据源失败 {name}: {e}")
    
    async def analyze_market(self, symbol: str = "BTC/USDT") -> FusedMarketIntelligence:
        """
        综合分析市场
        
        整合所有可用数据源，生成融合后的市场情报
        """
        cache_key = f"{symbol}_{datetime.now().strftime('%Y%m%d%H%M')}"
        
        if cache_key in self.analysis_cache:
            return self.analysis_cache[cache_key]
        
        logger.info(f"🔍 开始多源数据分析: {symbol}")
        
        analyses = {}
        
        # 1. 技术分析 (来自AI交易引擎)
        analyses["technical"] = await self._analyze_technical(symbol)
        
        # 2. 市场情绪分析 (来自CoinGecko等)
        analyses["sentiment"] = await self._analyze_market_sentiment(symbol)
        
        # 3. 链上数据分析 (来自Etherscan)
        analyses["on_chain"] = await self._analyze_on_chain(symbol)
        
        # 4. 新闻分析 (来自NewsAPI)
        analyses["news"] = await self._analyze_news(symbol)
        
        # 5. 社交媒体分析 (来自Twitter)
        analyses["social_media"] = await self._analyze_social_media(symbol)
        
        # 融合所有分析结果
        fused_intelligence = self._fuse_analyses(analyses, symbol)
        
        # 使用AI增强分析
        if self.llm_integration:
            fused_intelligence = await self._ai_enhance_analysis(fused_intelligence, symbol)
        
        self.analysis_cache[cache_key] = fused_intelligence
        
        logger.info(f"✅ 多源数据分析完成: {symbol}, 情绪={fused_intelligence.overall_sentiment.value}, "
                   f"信号强度={fused_intelligence.signal_strength.value}, 建议={fused_intelligence.recommendation}")
        
        return fused_intelligence
    
    async def _analyze_technical(self, symbol: str) -> DataSourceAnalysis:
        """技术分析"""
        try:
            if not self.data_integration:
                return DataSourceAnalysis(
                    source_name="technical",
                    source_type="technical",
                    data_available=False,
                    sentiment=SentimentLevel.NEUTRAL,
                    sentiment_score=0,
                    key_findings=["技术数据不可用"]
                )
            
            binance_source = self.data_sources.get("binance", {}).get("instance")
            
            if binance_source:
                klines = await binance_source.fetch_data(
                    symbol=symbol.replace("/", ""),
                    interval="1h",
                    limit=100
                )
                
                if not klines.empty:
                    closes = klines['close'].values.tolist()
                    
                    trend = self._calculate_trend(closes)
                    rsi = self._calculate_rsi(closes)
                    volatility = self._calculate_volatility(closes)
                    
                    sentiment_score = (trend * 0.4 + (rsi - 50) / 50 * 0.3 + (1 - volatility) * 0.3)
                    
                    findings = []
                    if trend > 0.3:
                        findings.append("上升趋势明显")
                    elif trend < -0.3:
                        findings.append("下降趋势明显")
                    
                    if rsi > 70:
                        findings.append(f"RSI超买({rsi:.1f})")
                        sentiment_score -= 0.2
                    elif rsi < 30:
                        findings.append(f"RSI超卖({rsi:.1f})")
                        sentiment_score += 0.2
                    
                    if volatility > 0.05:
                        findings.append(f"高波动率({volatility:.2%})")
                    
                    return DataSourceAnalysis(
                        source_name="technical",
                        source_type="technical",
                        data_available=True,
                        sentiment=self._score_to_sentiment(sentiment_score),
                        sentiment_score=max(-1, min(1, sentiment_score)),
                        key_findings=findings,
                        confidence=0.85,
                        raw_data={
                            "trend": trend,
                            "rsi": rsi,
                            "volatility": volatility,
                            "price": closes[-1] if closes else 0
                        }
                    )
            
            return DataSourceAnalysis(
                source_name="technical",
                source_type="technical",
                data_available=False,
                sentiment=SentimentLevel.NEUTRAL,
                sentiment_score=0,
                key_findings=["无法获取K线数据"]
            )
            
        except Exception as e:
            logger.error(f"技术分析失败: {e}")
            return DataSourceAnalysis(
                source_name="technical",
                source_type="technical",
                data_available=False,
                sentiment=SentimentLevel.NEUTRAL,
                sentiment_score=0,
                key_findings=[f"分析错误: {str(e)[:50]}"]
            )
    
    async def _analyze_market_sentiment(self, symbol: str) -> DataSourceAnalysis:
        """市场情绪分析"""
        try:
            coingecko_source = self.data_sources.get("coingecko", {}).get("instance")
            
            if coingecko_source:
                coin_id = symbol.split("/")[0].lower()
                
                df = await coingecko_source.fetch_data(
                    coin_id=coin_id if coin_id != "btc" else "bitcoin",
                    vs_currency="usd",
                    days=7
                )
                
                if not df.empty:
                    prices = df['price'].values.tolist()
                    
                    price_change = (prices[-1] - prices[0]) / prices[0] if prices[0] > 0 else 0
                    
                    daily_changes = []
                    for i in range(1, len(prices)):
                        if prices[i-1] > 0:
                            daily_changes.append((prices[i] - prices[i-1]) / prices[i-1])
                    
                    avg_daily_change = statistics.mean(daily_changes) if daily_changes else 0
                    positive_days = sum(1 for c in daily_changes if c > 0) if daily_changes else 0
                    negative_days = len(daily_changes) - positive_days
                    
                    sentiment_score = price_change * 0.5 + avg_daily_change * 0.3
                    
                    if positive_days > negative_days * 1.5:
                        sentiment_score += 0.2
                        key_finding = f"过去7天{positive_days}天上涨，情绪偏多"
                    elif negative_days > positive_days * 1.5:
                        sentiment_score -= 0.2
                        key_finding = f"过去7天{negative_days}天下跌，情绪偏空"
                    else:
                        key_finding = "涨跌互现，情绪中性"
                    
                    return DataSourceAnalysis(
                        source_name="market_sentiment",
                        source_type="market_data",
                        data_available=True,
                        sentiment=self._score_to_sentiment(sentiment_score),
                        sentiment_score=max(-1, min(1, sentiment_score)),
                        key_findings=[key_finding, f"7日涨跌幅: {price_change:+.2%}"],
                        confidence=0.75,
                        raw_data={
                            "price_change_7d": price_change,
                            "positive_days": positive_days,
                            "negative_days": negative_days
                        }
                    )
            
            return DataSourceAnalysis(
                source_name="market_sentiment",
                source_type="market_data",
                data_available=False,
                sentiment=SentimentLevel.NEUTRAL,
                sentiment_score=0,
                key_findings=["CoinGecko数据不可用"]
            )
            
        except Exception as e:
            logger.error(f"市场情绪分析失败: {e}")
            return DataSourceAnalysis(
                source_name="market_sentiment",
                source_type="market_data",
                data_available=False,
                sentiment=SentimentLevel.NEUTRAL,
                sentiment_score=0,
                key_findings=[f"分析错误: {str(e)[:50]}"]
            )
    
    async def _analyze_on_chain(self, symbol: str) -> DataSourceAnalysis:
        """链上数据分析"""
        try:
            etherscan_source = self.data_sources.get("etherscan", {}).get("instance")
            
            if not etherscan_source or "ETH" not in symbol.upper():
                return DataSourceAnalysis(
                    source_name="on_chain",
                    source_type="blockchain",
                    data_available=False,
                    sentiment=SentimentLevel.NEUTRAL,
                    sentiment_score=0,
                    key_findings=["链上数据不可用或非ETH相关"]
                )
            
            df = await etherscan_source.fetch_data(
                address="0x00000000219ab540356cbb839cbe05303d7705fa",
                startblock=0,
                endblock=99999999,
                sort="desc",
                limit=100
            )
            
            if not df.empty:
                total_value = df['value'].sum()
                tx_count = len(df)
                avg_value = df['value'].mean()
                
                large_tx_count = len(df[df['value'] > avg_value * 10])
                
                sentiment_score = 0
                
                if tx_count > 500:
                    sentiment_score += 0.15
                    finding1 = f"活跃度高: {tx_count}笔交易"
                else:
                    finding1 = f"活跃度一般: {tx_count}笔交易"
                
                if large_tx_count > 20:
                    sentiment_score += 0.1
                    finding2 = f"大额交易频繁: {large_tx_count}笔鲸鱼交易"
                else:
                    finding2 = f"大额交易正常: {large_tx_count}笔"
                
                return DataSourceAnalysis(
                    source_name="on_chain",
                    source_type="blockchain",
                    data_available=True,
                    sentiment=self._score_to_sentiment(sentiment_score),
                    sentiment_score=max(-1, min(1, sentiment_score)),
                    key_findings=[finding1, finding2],
                    confidence=0.65,
                    raw_data={
                        "tx_count": tx_count,
                        "total_value": total_value,
                        "large_tx_count": large_tx_count
                    }
                )
            
            return DataSourceAnalysis(
                source_name="on_chain",
                source_type="blockchain",
                data_available=False,
                sentiment=SentimentLevel.NEUTRAL,
                sentiment_score=0,
                key_findings=["无法获取链上数据"]
            )
            
        except Exception as e:
            logger.error(f"链上数据分析失败: {e}")
            return DataSourceAnalysis(
                source_name="on_chain",
                source_type="blockchain",
                data_available=False,
                sentiment=SentimentLevel.NEUTRAL,
                sentiment_score=0,
                key_findings=[f"分析错误: {str(e)[:50]}"]
            )
    
    async def _analyze_news(self, symbol: str) -> DataSourceAnalysis:
        """新闻分析"""
        try:
            news_source = self.data_sources.get("news", {}).get("instance")
            
            if not news_source:
                return DataSourceAnalysis(
                    source_name="news",
                    source_type="news",
                    data_available=False,
                    sentiment=SentimentLevel.NEUTRAL,
                    sentiment_score=0,
                    key_findings=["新闻API未配置"]
                )
            
            df = await news_source.fetch_data(
                query="cryptocurrency bitcoin ethereum",
                from_date=datetime.now() - timedelta(days=1),
                page_size=20
            )
            
            if not df.empty:
                positive_keywords = ['bullish', 'rise', 'gain', 'surge', 'rally', 'growth', 'adoption', '突破', '上涨', '利好']
                negative_keywords = ['bearish', 'fall', 'drop', 'crash', 'decline', 'regulation', 'ban', '下跌', '暴跌', '监管']
                
                titles = df['title'].tolist() if 'title' in df.columns else []
                
                positive_count = 0
                negative_count = 0
                
                for title in str(titles).lower():
                    for kw in positive_keywords:
                        if kw in title.lower():
                            positive_count += 1
                    for kw in negative_keywords:
                        if kw in title.lower():
                            negative_count += 1
                
                total = positive_count + negative_count
                sentiment_score = (positive_count - negative_count) / total if total > 0 else 0
                
                if sentiment_score > 0.3:
                    key_finding = f"新闻情绪偏多: {len(df)}篇报道，正面居多"
                elif sentiment_score < -0.3:
                    key_finding = f"新闻情绪偏空: {len(df)}篇报道，负面居多"
                else:
                    key_finding = f"新闻情绪中性: {len(df)}篇报道"
                
                return DataSourceAnalysis(
                    source_name="news",
                    source_type="news",
                    data_available=True,
                    sentiment=self._score_to_sentiment(sentiment_score),
                    sentiment_score=max(-1, min(1, sentiment_score)),
                    key_findings=[key_finding],
                    confidence=0.6,
                    raw_data={
                        "article_count": len(df),
                        "positive_mentions": positive_count,
                        "negative_mentions": negative_count
                    }
                )
            
            return DataSourceAnalysis(
                source_name="news",
                source_type="news",
                data_available=False,
                sentiment=SentimentLevel.NEUTRAL,
                sentiment_score=0,
                key_findings=["无最新新闻数据"]
            )
            
        except Exception as e:
            logger.error(f"新闻分析失败: {e}")
            return DataSourceAnalysis(
                source_name="news",
                source_type="news",
                data_available=False,
                sentiment=SentimentLevel.NEUTRAL,
                sentiment_score=0,
                key_findings=[f"分析错误: {str(e)[:50]}"]
            )
    
    async def _analyze_social_media(self, symbol: str) -> DataSourceAnalysis:
        """社交媒体分析"""
        try:
            twitter_source = self.data_sources.get("twitter", {}).get("instance")
            
            if not twitter_source:
                return DataSourceAnalysis(
                    source_name="social_media",
                    source_type="social_media",
                    data_available=False,
                    sentiment=SentimentLevel.NEUTRAL,
                    sentiment_score=0,
                    key_findings=["Twitter API未配置"]
                )
            
            df = await twitter_source.fetch_data(
                query="bitcoin OR BTC OR cryptocurrency",
                max_results=50
            )
            
            if not df.empty:
                positive_emojis = ['🚀', '📈', '💎', '🙌', 'bull', 'moon', 'long']
                negative_emojis = ['📉', '💔', '😰', 'crash', 'dump', 'short']
                
                texts = df['text'].tolist() if 'text' in df.columns else []
                
                positive_count = 0
                negative_count = 0
                
                for text in texts:
                    text_lower = str(text).lower()
                    for emoji in positive_emojis:
                        if emoji in text_lower:
                            positive_count += 1
                    for emoji in negative_emojis:
                        if emoji in text_lower:
                            negative_count += 1
                
                total = positive_count + negative_count
                sentiment_score = (positive_count - negative_count) / total if total > 0 else 0
                
                engagement = 0
                if 'public_metrics' in df.columns:
                    metrics = df['public_metrics'].apply(lambda x: x.get('like_count', 0) if isinstance(x, dict) else 0)
                    engagement = metrics.sum()
                
                if sentiment_score > 0.3:
                    key_finding = f"社交媒体情绪偏多: {len(df)}条推文"
                elif sentiment_score < -0.3:
                    key_finding = f"社交媒体情绪偏空: {len(df)}条推文"
                else:
                    key_finding = f"社交媒体情绪中性: {len(df)}条推文"
                
                return DataSourceAnalysis(
                    source_name="social_media",
                    source_type="social_media",
                    data_available=True,
                    sentiment=self._score_to_sentiment(sentiment_score),
                    sentiment_score=max(-1, min(1, sentiment_score)),
                    key_findings=[key_finding, f"总互动量: {engagement}"],
                    confidence=0.55,
                    raw_data={
                        "tweet_count": len(df),
                        "engagement": engagement,
                        "positive_mentions": positive_count,
                        "negative_mentions": negative_count
                    }
                )
            
            return DataSourceAnalysis(
                source_name="social_media",
                source_type="social_media",
                data_available=False,
                sentiment=SentimentLevel.NEUTRAL,
                sentiment_score=0,
                key_findings=["无Twitter数据"]
            )
            
        except Exception as e:
            logger.error(f"社交媒体分析失败: {e}")
            return DataSourceAnalysis(
                source_name="social_media",
                source_type="social_media",
                data_available=False,
                sentiment=SentimentLevel.NEUTRAL,
                sentiment_score=0,
                key_findings=[f"分析错误: {str(e)[:50]}"]
            )
    
    def _fuse_analyses(self, analyses: Dict[str, DataSourceAnalysis], symbol: str) -> FusedMarketIntelligence:
        """融合所有分析结果"""
        weights = self.config["sentiment_weights"]
        
        weighted_scores = []
        used_sources = []
        missing_sources = []
        
        all_key_insights = []
        all_risk_factors = []
        all_opportunities = []
        
        for analysis_type, analysis in analyses.items():
            weight = weights.get(analysis_type, 0.1)
            
            if analysis.data_available:
                weighted_score = analysis.sentiment_score * weight * analysis.confidence
                weighted_scores.append(weighted_score)
                used_sources.append(analysis.source_name)
                
                all_key_insights.extend(analysis.key_findings)
                
                if analysis.sentiment_score < -0.3:
                    all_risk_factors.extend(analysis.key_findings[:2])
                elif analysis.sentiment_score > 0.3:
                    all_opportunities.extend(analysis.key_findings[:2])
            else:
                missing_sources.append(analysis.source_name)
        
        overall_score = sum(weighted_scores) if weighted_scores else 0
        
        overall_sentiment = self._score_to_sentiment(overall_score)
        
        if abs(overall_score) > 0.4:
            signal_strength = SignalStrength.STRONG if abs(overall_score) > 0.6 else SignalStrength.MODERATE
        elif abs(overall_score) > 0.2:
            signal_strength = SignalStrength.MODERATE
        else:
            signal_strength = SignalStrength.WEAK
        
        if overall_score > 0.15:
            recommendation = "bullish"
        elif overall_score < -0.15:
            recommendation = "bearish"
        else:
            recommendation = "neutral"
        
        confidence = min(len(used_sources) / 5, 1.0) * 0.9 + 0.1
        
        return FusedMarketIntelligence(
            overall_sentiment=overall_sentiment,
            overall_sentiment_score=round(overall_score, 3),
            signal_strength=signal_strength,
            technical_analysis=analyses.get("technical", DataSourceAnalysis("", "", False, SentimentLevel.NEUTRAL, 0)).raw_data,
            sentiment_analysis=analyses.get("sentiment", DataSourceAnalysis("", "", False, SentimentLevel.NEUTRAL, 0)).raw_data,
            on_chain_analysis=analyses.get("on_chain", DataSourceAnalysis("", "", False, SentimentLevel.NEUTRAL, 0)).raw_data,
            news_analysis=analyses.get("news", DataSourceAnalysis("", "", False, SentimentLevel.NEUTRAL, 0)).raw_data,
            social_media_analysis=analyses.get("social_media", DataSourceAnalysis("", "", False, SentimentLevel.NEUTRAL, 0)).raw_data,
            key_insights=all_key_insights[:8],
            risk_factors=list(set(all_risk_factors))[:5],
            opportunity_signals=list(set(all_opportunities))[:5],
            recommendation=recommendation,
            confidence=round(confidence, 2),
            data_sources_used=used_sources,
            data_sources_missing=missing_sources
        )
    
    async def _ai_enhance_analysis(self, intelligence: FusedMarketIntelligence, symbol: str) -> FusedMarketIntelligence:
        """使用AI增强分析"""
        try:
            if not self.llm_integration:
                return intelligence
            
            prompt = f"""基于以下多源数据分析结果，为 {symbol} 提供更深入的洞察：

【当前分析】
- 综合情绪: {intelligence.overall_sentiment.value} ({intelligence.overall_sentiment_score:+.2f})
- 信号强度: {intelligence.signal_strength.value}
- 建议: {intelligence.recommendation}

【各维度发现】
{chr(10).join('- ' + insight for insight in intelligence.key_insights)}

【风险因素】
{chr(10).join('- ' + risk for risk in intelligence.risk_factors) if intelligence.risk_factors else '- 无显著风险'}

【机会信号】
{chr(10).join('- ' + opp for opp in intelligence.opportunity_signals) if intelligence.opportunity_signals else '- 无明显机会'}

请提供：
1. 关键洞察总结 (2-3点)
2. 可能被忽略的风险 (1-2点)
3. 潜在机会 (1-2点)
4. 最终建议调整 (如有)

以简洁的JSON格式返回。"""
            
            response = await self.llm_integration.generate(prompt, is_user_input=False)
            
            if response and response.success and response.content:
                ai_insights = self._parse_ai_response(response.content)
                
                if ai_insights.get("key_insights"):
                    intelligence.key_insights.extend(ai_insights["key_insights"])
                if ai_insights.get("additional_risks"):
                    intelligence.risk_factors.extend(ai_insights["additional_risks"])
                if ai_insights.get("opportunities"):
                    intelligence.opportunity_signals.extend(ai_insights["opportunities"])
                if ai_insights.get("adjusted_recommendation"):
                    intelligence.recommendation = ai_insights["adjusted_recommendation"]
                
                intelligence.confidence = min(intelligence.confidence + 0.05, 1.0)
                
                logger.info(f"🤖 AI增强分析完成")
            
        except Exception as e:
            logger.error(f"AI增强分析失败: {e}")
        
        return intelligence
    
    def _calculate_trend(self, prices: List[float]) -> float:
        """计算趋势 (-1 to 1)"""
        if len(prices) < 10:
            return 0
        
        short_ma = sum(prices[-10:]) / 10
        long_ma = sum(prices[-30:]) / 30 if len(prices) >= 30 else short_ma
        
        if long_ma == 0:
            return 0
        
        trend = (short_ma - long_ma) / long_ma
        return max(-1, min(1, trend))
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """计算RSI"""
        if len(prices) < period + 1:
            return 50
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_volatility(self, prices: List[float]) -> float:
        """计算波动率"""
        if len(prices) < 2:
            return 0
        
        returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices)) if prices[i-1] != 0]
        
        if not returns:
            return 0
        
        return statistics.stdev(returns) if len(returns) > 1 else 0
    
    def _score_to_sentiment(self, score: float) -> SentimentLevel:
        """将分数转换为情绪等级"""
        if score >= 0.6:
            return SentimentLevel.EXTREME_GREED
        elif score >= 0.2:
            return SentimentLevel.GREED
        elif score >= -0.2:
            return SentimentLevel.NEUTRAL
        elif score >= -0.6:
            return SentimentLevel.FEAR
        else:
            return SentimentLevel.EXTREME_FEAR
    
    def _parse_ai_response(self, content: str) -> Dict:
        """解析AI响应"""
        try:
            import re
            
            insights_match = re.search(r'(?:关键洞察|insights)[：:]\s*(.+?)(?=\n|$)', content, re.IGNORECASE)
            risks_match = re.search(r'(?:风险|risks)[：:]\s*(.+?)(?=\n|$)', content, re.IGNORECASE)
            opportunities_match = re.search(r'(?:机会|opportunities)[：:]\s*(.+?)(?=\n|$)', content, re.IGNORECASE)
            recommendation_match = re.search(r'(?:建议|recommendation)[：:]\s*(\w+)', content, re.IGNORECASE)
            
            result = {}
            
            if insights_match:
                result["key_insights"] = [s.strip() for s in insights_match.group(1).split(",")]
            if risks_match:
                result["additional_risks"] = [s.strip() for s in risks_match.group(1).split(",")]
            if opportunities_match:
                result["opportunities"] = [s.strip() for s in opportunities_match.group(1).split(",")]
            if recommendation_match:
                rec = recommendation_match.group(1).lower()
                if rec in ["bullish", "bearish", "neutral"]:
                    result["adjusted_recommendation"] = rec
            
            return result
            
        except Exception as e:
            logger.error(f"解析AI响应失败: {e}")
            return {}
    
    def get_status(self) -> Dict:
        """获取状态"""
        return {
            "registered_sources": list(self.data_sources.keys()),
            "cache_size": len(self.analysis_cache),
            "config": self.config
        }
