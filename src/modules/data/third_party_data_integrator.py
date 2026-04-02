"""
第三方数据源集成模块
整合社交媒体、新闻、市场情绪等多源数据
"""
import asyncio
import aiohttp
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
import json
import hashlib
import os

logger = logging.getLogger(__name__)


class DataSource(Enum):
    TWITTER = "twitter"
    REDDIT = "reddit"
    TELEGRAM = "telegram"
    NEWS = "news"
    COINTELEGRAPH = "cointelegraph"
    COINDESK = "coindesk"
    FEAR_GREED_INDEX = "fear_greed_index"
    LUNARCRUSH = "lunarcrush"
    SANTIMENT = "santiment"


@dataclass
class SocialMention:
    source: DataSource
    content: str
    author: str
    timestamp: datetime
    sentiment: float
    engagement: int
    url: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NewsArticle:
    title: str
    content: str
    source: str
    url: str
    timestamp: datetime
    sentiment: float
    relevance: float
    categories: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    impact_score: float = 0.0


@dataclass
class MarketSentiment:
    timestamp: datetime
    fear_greed_index: float
    social_sentiment: float
    news_sentiment: float
    overall_sentiment: float
    trend: str
    confidence: float
    details: Dict[str, Any] = field(default_factory=dict)


class BaseDataProvider(ABC):
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, proxy_url: Optional[str] = None):
        self.api_key = api_key or os.getenv(self._get_env_key(), "")
        self.api_secret = api_secret or os.getenv(self._get_env_secret(), "")
        self.session: Optional[aiohttp.ClientSession] = None
        self._rate_limit_remaining = 100
        self._rate_limit_reset = datetime.now()
        self._proxy_url = proxy_url
    
    async def _init_proxy(self):
        """初始化代理"""
        if self._proxy_url is None:
            try:
                from src.utils.proxy_utils import get_proxy_url
                self._proxy_url = await get_proxy_url()
                if self._proxy_url:
                    logger.info(f"📊 {self.__class__.__name__} 使用代理: {self._proxy_url}")
            except Exception as e:
                logger.debug(f"获取代理失败: {e}")
    
    @abstractmethod
    def _get_env_key(self) -> str:
        pass
    
    @abstractmethod
    def _get_env_secret(self) -> str:
        pass
    
    @abstractmethod
    async def fetch_data(self, symbol: str, **kwargs) -> Dict[str, Any]:
        pass
    
    async def _make_request(self, url: str, headers: Dict[str, str] = None, params: Dict[str, Any] = None) -> Optional[Dict]:
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        await self._init_proxy()
        
        try:
            async with self.session.get(url, headers=headers, params=params, proxy=self._proxy_url, timeout=30) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 429:
                    logger.warning(f"Rate limit hit for {self.__class__.__name__}")
                    await asyncio.sleep(60)
                    return None
                else:
                    logger.error(f"API error: {response.status}")
                    return None
        except asyncio.TimeoutError:
            logger.error(f"Request timeout for {url}")
            return None
        except Exception as e:
            logger.error(f"Request error: {e}")
            return None
    
    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None


class TwitterProvider(BaseDataProvider):
    def _get_env_key(self) -> str:
        return "TWITTER_API_KEY"
    
    def _get_env_secret(self) -> str:
        return "TWITTER_API_SECRET"
    
    async def fetch_data(self, symbol: str, **kwargs) -> Dict[str, Any]:
        query = f"${symbol} OR #{symbol} -filter:retweets"
        params = {
            "query": query,
            "max_results": kwargs.get("max_results", 100),
            "tweet.fields": "created_at,public_metrics,entities"
        }
        
        mentions = []
        if self.api_key:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            data = await self._make_request(
                "https://api.twitter.com/2/tweets/search/recent",
                headers=headers,
                params=params
            )
            
            if data and "data" in data:
                for tweet in data["data"]:
                    sentiment = await self._analyze_sentiment(tweet["text"])
                    mentions.append(SocialMention(
                        source=DataSource.TWITTER,
                        content=tweet["text"],
                        author=tweet.get("author_id", "unknown"),
                        timestamp=datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00")),
                        sentiment=sentiment,
                        engagement=tweet["public_metrics"].get("like_count", 0) + tweet["public_metrics"].get("retweet_count", 0),
                        tags=[tag["tag"] for tag in tweet.get("entities", {}).get("hashtags", [])]
                    ))
        
        return {
            "source": DataSource.TWITTER.value,
            "symbol": symbol,
            "mentions": mentions,
            "timestamp": datetime.now(),
            "total_engagement": sum(m.engagement for m in mentions)
        }
    
    async def _analyze_sentiment(self, text: str) -> float:
        positive_words = ["bullish", "moon", "pump", "buy", "long", "support", "breakout", "rally"]
        negative_words = ["bearish", "dump", "sell", "short", "crash", "resistance", "breakdown"]
        
        text_lower = text.lower()
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)
        
        total = pos_count + neg_count
        if total == 0:
            return 0.5
        return pos_count / total


class RedditProvider(BaseDataProvider):
    def _get_env_key(self) -> str:
        return "REDDIT_CLIENT_ID"
    
    def _get_env_secret(self) -> str:
        return "REDDIT_CLIENT_SECRET"
    
    async def fetch_data(self, symbol: str, **kwargs) -> Dict[str, Any]:
        subreddits = kwargs.get("subreddits", ["CryptoCurrency", "CryptoMarkets", f"{symbol}"])
        mentions = []
        
        for subreddit in subreddits:
            url = f"https://www.reddit.com/r/{subreddit}/search.json"
            params = {
                "q": symbol,
                "restrict_sr": 1,
                "sort": "hot",
                "limit": kwargs.get("limit", 50)
            }
            
            headers = {"User-Agent": "OpenClawTrading/1.0"}
            data = await self._make_request(url, headers=headers, params=params)
            
            if data and "data" in data and "children" in data["data"]:
                for post in data["data"]["children"]:
                    post_data = post["data"]
                    sentiment = await self._analyze_sentiment(post_data["title"] + " " + post_data.get("selftext", ""))
                    mentions.append(SocialMention(
                        source=DataSource.REDDIT,
                        content=post_data["title"],
                        author=post_data["author"],
                        timestamp=datetime.fromtimestamp(post_data["created_utc"]),
                        sentiment=sentiment,
                        engagement=post_data["score"] + post_data["num_comments"],
                        url=f"https://reddit.com{post_data['permalink']}",
                        tags=[subreddit]
                    ))
        
        return {
            "source": DataSource.REDDIT.value,
            "symbol": symbol,
            "mentions": mentions,
            "timestamp": datetime.now(),
            "total_engagement": sum(m.engagement for m in mentions)
        }
    
    async def _analyze_sentiment(self, text: str) -> float:
        return await TwitterProvider(None, None)._analyze_sentiment(text)


class NewsProvider(BaseDataProvider):
    def __init__(self, api_key: Optional[str] = None, provider: str = "cryptocompare"):
        super().__init__(api_key)
        self.provider = provider
    
    def _get_env_key(self) -> str:
        return "NEWS_API_KEY"
    
    def _get_env_secret(self) -> str:
        return "NEWS_API_SECRET"
    
    async def fetch_data(self, symbol: str, **kwargs) -> Dict[str, Any]:
        articles = []
        
        if self.provider == "cryptocompare":
            articles = await self._fetch_crypto_compare(symbol, **kwargs)
        elif self.provider == "cointelegraph":
            articles = await self._fetch_cointelegraph(symbol, **kwargs)
        
        return {
            "source": self.provider,
            "symbol": symbol,
            "articles": articles,
            "timestamp": datetime.now()
        }
    
    async def _fetch_crypto_compare(self, symbol: str, **kwargs) -> List[NewsArticle]:
        url = "https://min-api.cryptocompare.com/data/v2/news/"
        params = {"categories": symbol, "limit": kwargs.get("limit", 30)}
        
        if self.api_key:
            params["api_key"] = self.api_key
        
        data = await self._make_request(url, params=params)
        articles = []
        
        if data and "Data" in data:
            for item in data["Data"]:
                sentiment = await self._analyze_news_sentiment(item["title"] + " " + item.get("body", ""))
                articles.append(NewsArticle(
                    title=item["title"],
                    content=item.get("body", ""),
                    source=item["source"],
                    url=item["url"],
                    timestamp=datetime.fromtimestamp(item["published_on"]),
                    sentiment=sentiment,
                    relevance=self._calculate_relevance(item, symbol),
                    categories=item.get("categories", "").split(",")
                ))
        
        return articles
    
    async def _fetch_cointelegraph(self, symbol: str, **kwargs) -> List[NewsArticle]:
        url = "https://cointelegraph.com/api/v1/content/json"
        params = {"tag": symbol, "limit": kwargs.get("limit", 20)}
        
        data = await self._make_request(url, params=params)
        articles = []
        
        if data and "data" in data:
            for item in data["data"]:
                sentiment = await self._analyze_news_sentiment(item.get("title", ""))
                articles.append(NewsArticle(
                    title=item.get("title", ""),
                    content=item.get("lead", ""),
                    source="CoinTelegraph",
                    url=f"https://cointelegraph.com{item.get('url', '')}",
                    timestamp=datetime.fromisoformat(item.get("published", "").replace("Z", "+00:00")),
                    sentiment=sentiment,
                    relevance=0.8,
                    categories=[symbol]
                ))
        
        return articles
    
    async def _analyze_news_sentiment(self, text: str) -> float:
        positive_phrases = [
            "surge", "rally", "gain", "rise", "bullish", "breakout",
            "adoption", "partnership", "launch", "upgrade", "approval"
        ]
        negative_phrases = [
            "crash", "dump", "fall", "bearish", "breakdown", "hack",
            "regulation", "ban", "lawsuit", "fraud", "collapse"
        ]
        
        text_lower = text.lower()
        pos_score = sum(1 for phrase in positive_phrases if phrase in text_lower)
        neg_score = sum(1 for phrase in negative_phrases if phrase in text_lower)
        
        total = pos_score + neg_score
        if total == 0:
            return 0.5
        return pos_score / total
    
    def _calculate_relevance(self, item: Dict, symbol: str) -> float:
        title = item.get("title", "").lower()
        body = item.get("body", "").lower()
        symbol_lower = symbol.lower()
        
        relevance = 0.0
        if symbol_lower in title:
            relevance += 0.5
        if symbol_lower in body:
            relevance += 0.3
        if item.get("categories", "").lower().find(symbol_lower) >= 0:
            relevance += 0.2
        
        return min(relevance, 1.0)


class FearGreedIndexProvider(BaseDataProvider):
    def _get_env_key(self) -> str:
        return "ALTERNATIVE_ME_API_KEY"
    
    def _get_env_secret(self) -> str:
        return "ALTERNATIVE_ME_API_SECRET"
    
    async def fetch_data(self, symbol: str = "BTC", **kwargs) -> Dict[str, Any]:
        url = "https://api.alternative.me/fng/"
        params = {"limit": kwargs.get("limit", 1)}
        
        data = await self._make_request(url, params=params)
        
        if data and "data" in data:
            latest = data["data"][0]
            return {
                "source": DataSource.FEAR_GREED_INDEX.value,
                "value": int(latest["value"]),
                "classification": latest["value_classification"],
                "timestamp": datetime.fromtimestamp(int(latest["timestamp"])),
                "symbol": symbol
            }
        
        return {
            "source": DataSource.FEAR_GREED_INDEX.value,
            "value": 50,
            "classification": "Neutral",
            "timestamp": datetime.now(),
            "symbol": symbol
        }


class LunarCrushProvider(BaseDataProvider):
    def _get_env_key(self) -> str:
        return "LUNARCRUSH_API_KEY"
    
    def _get_env_secret(self) -> str:
        return "LUNARCRUSH_API_SECRET"
    
    async def fetch_data(self, symbol: str, **kwargs) -> Dict[str, Any]:
        if not self.api_key:
            return {"error": "LunarCrush API key required"}
        
        url = f"https://lunarcrush.com/api3/coins/{symbol.lower()}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        data = await self._make_request(url, headers=headers)
        
        if data:
            return {
                "source": DataSource.LUNARCRUSH.value,
                "symbol": symbol,
                "galaxy_score": data.get("galaxy_score", 0),
                "alt_rank": data.get("alt_rank", 0),
                "social_score": data.get("social_score", 0),
                "average_sentiment": data.get("average_sentiment", 0),
                "social_volume": data.get("social_volume", 0),
                "social_contributors": data.get("social_contributors", 0),
                "timestamp": datetime.now()
            }
        
        return {"error": "Failed to fetch LunarCrush data"}


class ThirdPartyDataIntegrator:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.providers: Dict[DataSource, BaseDataProvider] = {}
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = timedelta(minutes=15)
        self._initialize_providers()
    
    def _initialize_providers(self):
        self.providers[DataSource.TWITTER] = TwitterProvider()
        self.providers[DataSource.REDDIT] = RedditProvider()
        self.providers[DataSource.NEWS] = NewsProvider()
        self.providers[DataSource.FEAR_GREED_INDEX] = FearGreedIndexProvider()
        self.providers[DataSource.LUNARCRUSH] = LunarCrushProvider()
    
    async def get_social_sentiment(self, symbol: str, sources: Optional[List[DataSource]] = None) -> Dict[str, Any]:
        sources = sources or [DataSource.TWITTER, DataSource.REDDIT]
        cache_key = f"social_{symbol}_{'-'.join(s.value for s in sources)}"
        
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]["data"]
        
        results = {}
        tasks = []
        
        for source in sources:
            if source in self.providers:
                tasks.append(self._fetch_with_source(source, symbol))
        
        fetch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for source, result in zip(sources, fetch_results):
            if isinstance(result, Exception):
                logger.error(f"Error fetching {source.value}: {result}")
            else:
                results[source.value] = result
        
        aggregated = self._aggregate_social_sentiment(results)
        self._cache_data(cache_key, aggregated)
        
        return aggregated
    
    async def _fetch_with_source(self, source: DataSource, symbol: str) -> Dict[str, Any]:
        provider = self.providers.get(source)
        if provider:
            return await provider.fetch_data(symbol)
        return {}
    
    def _aggregate_social_sentiment(self, results: Dict[str, Any]) -> Dict[str, Any]:
        all_mentions: List[SocialMention] = []
        total_engagement = 0
        sentiment_scores = []
        
        for source, data in results.items():
            if "mentions" in data:
                all_mentions.extend(data["mentions"])
                total_engagement += data.get("total_engagement", 0)
                sentiment_scores.extend([m.sentiment for m in data["mentions"]])
        
        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.5
        
        return {
            "total_mentions": len(all_mentions),
            "total_engagement": total_engagement,
            "average_sentiment": avg_sentiment,
            "sentiment_trend": self._calculate_sentiment_trend(sentiment_scores),
            "top_mentions": sorted(all_mentions, key=lambda x: x.engagement, reverse=True)[:10],
            "source_breakdown": {s: len(d.get("mentions", [])) for s, d in results.items()},
            "timestamp": datetime.now()
        }
    
    def _calculate_sentiment_trend(self, scores: List[float]) -> str:
        if len(scores) < 2:
            return "neutral"
        
        recent = scores[-min(10, len(scores)):]
        older = scores[-min(20, len(scores)):-min(10, len(scores))] if len(scores) > 10 else scores[:-1]
        
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older) if older else recent_avg
        
        diff = recent_avg - older_avg
        if diff > 0.1:
            return "improving"
        elif diff < -0.1:
            return "declining"
        return "stable"
    
    async def get_news_sentiment(self, symbol: str, hours: int = 24) -> Dict[str, Any]:
        cache_key = f"news_{symbol}_{hours}"
        
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]["data"]
        
        news_provider = self.providers.get(DataSource.NEWS)
        if not news_provider:
            return {"error": "News provider not available"}
        
        data = await news_provider.fetch_data(symbol, limit=50)
        
        articles = data.get("articles", [])
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_articles = [a for a in articles if a.timestamp > cutoff_time]
        
        if recent_articles:
            avg_sentiment = sum(a.sentiment for a in recent_articles) / len(recent_articles)
            avg_relevance = sum(a.relevance for a in recent_articles) / len(recent_articles)
        else:
            avg_sentiment = 0.5
            avg_relevance = 0.0
        
        result = {
            "total_articles": len(recent_articles),
            "average_sentiment": avg_sentiment,
            "average_relevance": avg_relevance,
            "high_impact_articles": [a for a in recent_articles if a.relevance > 0.7][:5],
            "positive_articles": [a for a in recent_articles if a.sentiment > 0.6][:5],
            "negative_articles": [a for a in recent_articles if a.sentiment < 0.4][:5],
            "categories": self._extract_categories(recent_articles),
            "timestamp": datetime.now()
        }
        
        self._cache_data(cache_key, result)
        return result
    
    def _extract_categories(self, articles: List[NewsArticle]) -> Dict[str, int]:
        categories: Dict[str, int] = {}
        for article in articles:
            for cat in article.categories:
                cat = cat.strip()
                if cat:
                    categories[cat] = categories.get(cat, 0) + 1
        return dict(sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10])
    
    async def get_fear_greed_index(self) -> Dict[str, Any]:
        cache_key = "fear_greed_index"
        
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]["data"]
        
        provider = self.providers.get(DataSource.FEAR_GREED_INDEX)
        if provider:
            data = await provider.fetch_data()
            self._cache_data(cache_key, data)
            return data
        
        return {"value": 50, "classification": "Neutral", "timestamp": datetime.now()}
    
    async def get_comprehensive_sentiment(self, symbol: str) -> MarketSentiment:
        social_task = self.get_social_sentiment(symbol)
        news_task = self.get_news_sentiment(symbol)
        fg_task = self.get_fear_greed_index()
        
        social_data, news_data, fg_data = await asyncio.gather(
            social_task, news_task, fg_task, return_exceptions=True
        )
        
        if isinstance(social_data, Exception):
            social_data = {"average_sentiment": 0.5}
        if isinstance(news_data, Exception):
            news_data = {"average_sentiment": 0.5}
        if isinstance(fg_data, Exception):
            fg_data = {"value": 50}
        
        social_sentiment = social_data.get("average_sentiment", 0.5)
        news_sentiment = news_data.get("average_sentiment", 0.5)
        fg_normalized = fg_data.get("value", 50) / 100.0
        
        weights = self.config.get("sentiment_weights", {
            "social": 0.3,
            "news": 0.3,
            "fear_greed": 0.4
        })
        
        overall = (
            social_sentiment * weights.get("social", 0.3) +
            news_sentiment * weights.get("news", 0.3) +
            fg_normalized * weights.get("fear_greed", 0.4)
        )
        
        trend = self._determine_overall_trend(
            social_data.get("sentiment_trend", "stable"),
            news_data.get("average_sentiment", 0.5)
        )
        
        confidence = self._calculate_confidence(social_data, news_data, fg_data)
        
        return MarketSentiment(
            timestamp=datetime.now(),
            fear_greed_index=fg_normalized,
            social_sentiment=social_sentiment,
            news_sentiment=news_sentiment,
            overall_sentiment=overall,
            trend=trend,
            confidence=confidence,
            details={
                "social_mentions": social_data.get("total_mentions", 0),
                "social_engagement": social_data.get("total_engagement", 0),
                "news_articles": news_data.get("total_articles", 0),
                "fg_classification": fg_data.get("classification", "Neutral")
            }
        )
    
    def _determine_overall_trend(self, social_trend: str, news_sentiment: float) -> str:
        if social_trend == "improving" and news_sentiment > 0.6:
            return "strongly_bullish"
        elif social_trend == "improving" or news_sentiment > 0.6:
            return "bullish"
        elif social_trend == "declining" and news_sentiment < 0.4:
            return "strongly_bearish"
        elif social_trend == "declining" or news_sentiment < 0.4:
            return "bearish"
        return "neutral"
    
    def _calculate_confidence(self, social_data: Dict, news_data: Dict, fg_data: Dict) -> float:
        confidence = 0.0
        
        if social_data.get("total_mentions", 0) > 50:
            confidence += 0.3
        elif social_data.get("total_mentions", 0) > 10:
            confidence += 0.2
        
        if news_data.get("total_articles", 0) > 10:
            confidence += 0.3
        elif news_data.get("total_articles", 0) > 3:
            confidence += 0.2
        
        if fg_data.get("value") is not None:
            confidence += 0.4
        
        return min(confidence, 1.0)
    
    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache:
            return False
        cached = self._cache[key]
        return datetime.now() - cached["timestamp"] < self._cache_ttl
    
    def _cache_data(self, key: str, data: Any):
        self._cache[key] = {
            "data": data,
            "timestamp": datetime.now()
        }
    
    async def close(self):
        for provider in self.providers.values():
            await provider.close()


third_party_integrator = ThirdPartyDataIntegrator()
