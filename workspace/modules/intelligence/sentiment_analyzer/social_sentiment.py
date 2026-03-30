#!/usr/bin/env python3
"""
社交媒体情绪分析模块
监控和分析社交媒体情绪对加密货币市场的影响
"""

import asyncio
import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import aiohttp
import nltk
import numpy as np
from nltk.sentiment import SentimentIntensityAnalyzer

# 尝试下载NLTK数据
try:
    nltk.data.find("vader_lexicon")
except:
    try:
        nltk.download("vader_lexicon", quiet=True)
    except:
        print("警告: 无法下载NLTK数据，将使用简化情感分析")


@dataclass
class SocialSentiment:
    """社交媒体情绪数据"""

    timestamp: datetime
    symbol: str

    # 各平台情绪得分 (0-1, 0.5为中性)
    twitter_sentiment: float
    reddit_sentiment: float
    weibo_sentiment: float
    telegram_sentiment: float
    discord_sentiment: float

    # 讨论热度
    mention_count: int
    mention_change: float  # 24小时变化百分比

    # 情绪强度
    sentiment_strength: float  # 0-1, 情绪强烈程度
    sentiment_consistency: float  # 0-1, 各平台一致性

    # 关键词分析
    top_keywords: List[str]
    keyword_sentiments: Dict[str, float]

    # 综合指标
    overall_sentiment: float  # 综合情绪得分
    sentiment_trend: str  # rising, falling, stable
    market_impact: float  # 预期对市场的影响程度


class SocialSentimentAnalyzer:
    """社交媒体情绪分析器"""

    def __init__(self, config_manager):
        self.config = config_manager

        # 数据源配置
        self.data_sources = {
            "twitter": {
                "enabled": self.config.get("sentiment.twitter.enabled", True),
                "api_key": self.config.get("sentiment.twitter.api_key", ""),
                "bearer_token": self.config.get("sentiment.twitter.bearer_token", ""),
                "base_url": "https://api.twitter.com/2/tweets/search/recent",
            },
            "reddit": {
                "enabled": self.config.get("sentiment.reddit.enabled", True),
                "client_id": self.config.get("sentiment.reddit.client_id", ""),
                "client_secret": self.config.get("sentiment.reddit.client_secret", ""),
                "user_agent": "CryptoTraderBot/1.0",
            },
            "alternative": {
                "lunarcrush": {
                    "api_key": self.config.get("sentiment.lunarcrush.api_key", ""),
                    "base_url": "https://lunarcrush.com/api3",
                },
                "sentiment": {
                    "api_key": self.config.get("sentiment.sentiment.api_key", ""),
                    "base_url": "https://api.sentiment.io/v2",
                },
            },
        }

        # 情感分析器
        try:
            self.sia = SentimentIntensityAnalyzer()
            self.nltk_available = True
        except:
            self.sia = None
            self.nltk_available = False

        # 加密货币相关关键词
        self.crypto_keywords = {
            "positive": [
                "bullish",
                "moon",
                "lambo",
                "to the moon",
                "hodl",
                "buy the dip",
                "accumulate",
                "breakout",
                "rally",
                "pump",
                "surge",
                "soaring",
                "🚀",
                "🌕",
                "💎",
                "🙌",
                "📈",
                "🔥",
            ],
            "negative": [
                "bearish",
                "dump",
                "crash",
                "rekt",
                "fud",
                "scam",
                "rug pull",
                "sell",
                "panic",
                "collapse",
                "plummet",
                "tanking",
                "bloodbath",
                "📉",
                "😭",
                "💀",
                "😱",
                "⚠️",
                "🚨",
            ],
            "neutral": [
                "consolidation",
                "sideways",
                "range",
                "support",
                "resistance",
                "volatility",
                "uncertain",
                "waiting",
                "watching",
                "monitoring",
            ],
        }

        # 缓存系统
        self.cache = {}
        self.cache_ttl = 300  # 5分钟

        # 历史数据
        self.sentiment_history = {}

    async def analyze_social_sentiment(self, symbol: str) -> Optional[SocialSentiment]:
        """分析社交媒体情绪"""

        try:
            # 并行获取各平台数据
            tasks = [
                self._analyze_twitter_sentiment(symbol),
                self._analyze_reddit_sentiment(symbol),
                self._analyze_weibo_sentiment(symbol),
                self._analyze_telegram_sentiment(symbol),
                self._analyze_discord_sentiment(symbol),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 处理结果
            twitter_data = results[0] if not isinstance(results[0], Exception) else {}
            reddit_data = results[1] if not isinstance(results[1], Exception) else {}
            weibo_data = results[2] if not isinstance(results[2], Exception) else {}
            telegram_data = results[3] if not isinstance(results[3], Exception) else {}
            discord_data = results[4] if not isinstance(results[4], Exception) else {}

            # 计算综合情绪
            overall_sentiment = self._calculate_overall_sentiment(
                twitter_data, reddit_data, weibo_data, telegram_data, discord_data
            )

            # 计算情绪强度
            sentiment_strength = self._calculate_sentiment_strength(
                twitter_data, reddit_data, weibo_data, telegram_data, discord_data
            )

            # 计算情绪一致性
            sentiment_consistency = self._calculate_sentiment_consistency(
                twitter_data, reddit_data, weibo_data, telegram_data, discord_data
            )

            # 分析关键词
            all_texts = []
            all_texts.extend(twitter_data.get("texts", []))
            all_texts.extend(reddit_data.get("texts", []))
            all_texts.extend(weibo_data.get("texts", []))
            all_texts.extend(telegram_data.get("texts", []))
            all_texts.extend(discord_data.get("texts", []))

            top_keywords, keyword_sentiments = self._extract_keywords(all_texts)

            # 计算讨论热度
            mention_count = sum(
                [
                    twitter_data.get("mention_count", 0),
                    reddit_data.get("mention_count", 0),
                    weibo_data.get("mention_count", 0),
                    telegram_data.get("mention_count", 0),
                    discord_data.get("mention_count", 0),
                ]
            )

            # 计算讨论热度变化
            mention_change = self._calculate_mention_change(symbol, mention_count)

            # 确定情绪趋势
            sentiment_trend = self._determine_sentiment_trend(symbol, overall_sentiment)

            # 计算市场影响
            market_impact = self._calculate_market_impact(
                overall_sentiment, sentiment_strength, mention_count
            )

            # 构建情绪数据
            sentiment = SocialSentiment(
                timestamp=datetime.now(),
                symbol=symbol,
                twitter_sentiment=twitter_data.get("sentiment_score", 0.5),
                reddit_sentiment=reddit_data.get("sentiment_score", 0.5),
                weibo_sentiment=weibo_data.get("sentiment_score", 0.5),
                telegram_sentiment=telegram_data.get("sentiment_score", 0.5),
                discord_sentiment=discord_data.get("sentiment_score", 0.5),
                mention_count=mention_count,
                mention_change=mention_change,
                sentiment_strength=sentiment_strength,
                sentiment_consistency=sentiment_consistency,
                top_keywords=top_keywords[:10],  # 前10个关键词
                keyword_sentiments=keyword_sentiments,
                overall_sentiment=overall_sentiment,
                sentiment_trend=sentiment_trend,
                market_impact=market_impact,
            )

            # 保存历史数据
            self._update_sentiment_history(symbol, sentiment)

            return sentiment

        except Exception as e:
            print(f"分析社交媒体情绪失败: {e}")
            return None

    async def _analyze_twitter_sentiment(self, symbol: str) -> Dict:
        """分析Twitter情绪"""

        cache_key = f"twitter_{symbol}_{datetime.now().strftime('%Y%m%d%H')}"
        if (
            cache_key in self.cache
            and time.time() - self.cache[cache_key]["timestamp"] < self.cache_ttl
        ):
            return self.cache[cache_key]["data"]

        try:
            # 简化符号名（去掉USDT）
            base_symbol = symbol.replace("USDT", "")

            if (
                self.data_sources["twitter"]["enabled"]
                and self.data_sources["twitter"]["bearer_token"]
            ):
                # 使用Twitter API
                headers = {
                    "Authorization": f'Bearer {self.data_sources["twitter"]["bearer_token"]}'
                }

                # 构建查询
                query = f'({base_symbol} OR #{base_symbol} OR "bitcoin" OR "crypto") lang:en -is:retweet'

                params = {
                    "query": query,
                    "max_results": 100,
                    "tweet.fields": "created_at,public_metrics,lang",
                    "user.fields": "verified",
                }

                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        self.data_sources["twitter"]["base_url"], headers=headers, params=params
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            tweets = data.get("data", [])

                            # 分析情绪
                            sentiment_score, texts = self._analyze_texts(
                                [tweet.get("text", "") for tweet in tweets]
                            )

                            result = {
                                "sentiment_score": sentiment_score,
                                "mention_count": len(tweets),
                                "texts": texts,
                                "source": "twitter",
                            }

                            # 缓存结果
                            self.cache[cache_key] = {"timestamp": time.time(), "data": result}

                            return result

            # 如果API不可用，使用模拟数据
            return self._generate_mock_sentiment_data("twitter", symbol)

        except Exception as e:
            print(f"Twitter情绪分析失败: {e}")
            return self._generate_mock_sentiment_data("twitter", symbol)

    async def _analyze_reddit_sentiment(self, symbol: str) -> Dict:
        """分析Reddit情绪"""

        cache_key = f"reddit_{symbol}_{datetime.now().strftime('%Y%m%d%H')}"
        if (
            cache_key in self.cache
            and time.time() - self.cache[cache_key]["timestamp"] < self.cache_ttl
        ):
            return self.cache[cache_key]["data"]

        try:
            if self.data_sources["reddit"]["enabled"] and self.data_sources["reddit"]["client_id"]:
                # 使用Reddit API
                auth = aiohttp.BasicAuth(
                    self.data_sources["reddit"]["client_id"],
                    self.data_sources["reddit"]["client_secret"],
                )

                headers = {"User-Agent": self.data_sources["reddit"]["user_agent"]}

                # 获取热门帖子
                subreddits = ["CryptoCurrency", "Bitcoin", "ethereum", "CryptoMarkets"]
                all_posts = []

                async with aiohttp.ClientSession() as session:
                    for subreddit in subreddits:
                        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=50"

                        async with session.get(url, auth=auth, headers=headers) as response:
                            if response.status == 200:
                                data = await response.json()
                                posts = data.get("data", {}).get("children", [])
                                all_posts.extend(posts)

                # 提取帖子内容
                texts = []
                for post in all_posts:
                    post_data = post.get("data", {})
                    title = post_data.get("title", "")
                    selftext = post_data.get("selftext", "")

                    if title:
                        texts.append(title)
                    if selftext:
                        texts.append(selftext)

                # 分析情绪
                sentiment_score, analyzed_texts = self._analyze_texts(texts)

                result = {
                    "sentiment_score": sentiment_score,
                    "mention_count": len(all_posts),
                    "texts": analyzed_texts,
                    "source": "reddit",
                }

                # 缓存结果
                self.cache[cache_key] = {"timestamp": time.time(), "data": result}

                return result

            # 如果API不可用，使用模拟数据
            return self._generate_mock_sentiment_data("reddit", symbol)

        except Exception as e:
            print(f"Reddit情绪分析失败: {e}")
            return self._generate_mock_sentiment_data("reddit", symbol)

    async def _analyze_weibo_sentiment(self, symbol: str) -> Dict:
        """分析微博情绪"""

        # 微博API通常需要企业认证，这里使用模拟数据
        return self._generate_mock_sentiment_data("weibo", symbol)

    async def _analyze_telegram_sentiment(self, symbol: str) -> Dict:
        """分析Telegram情绪"""

        # Telegram API需要bot token和访问权限，这里使用模拟数据
        return self._generate_mock_sentiment_data("telegram", symbol)

    async def _analyze_discord_sentiment(self, symbol: str) -> Dict:
        """分析Discord情绪"""

        # Discord API需要bot token，这里使用模拟数据
        return self._generate_mock_sentiment_data("discord", symbol)

    def _analyze_texts(self, texts: List[str]) -> Tuple[float, List[Dict]]:
        """分析文本情绪"""

        if not texts:
            return 0.5, []

        analyzed_texts = []
        sentiment_scores = []

        for text in texts:
            if not text or len(text.strip()) < 3:
                continue

            # 使用NLTK情感分析
            if self.nltk_available and self.sia:
                try:
                    sentiment = self.sia.polarity_scores(text)
                    compound_score = sentiment["compound"]  # -1到1

                    # 转换为0-1范围
                    normalized_score = (compound_score + 1) / 2

                    analyzed_texts.append(
                        {
                            "text": text[:100],  # 截断
                            "sentiment": normalized_score,
                            "original_sentiment": sentiment,
                        }
                    )

                    sentiment_scores.append(normalized_score)

                except Exception as e:
                    # 如果NLTK分析失败，使用关键词分析
                    keyword_score = self._analyze_with_keywords(text)
                    analyzed_texts.append(
                        {"text": text[:100], "sentiment": keyword_score, "method": "keyword"}
                    )
                    sentiment_scores.append(keyword_score)
            else:
                # 使用关键词分析
                keyword_score = self._analyze_with_keywords(text)
                analyzed_texts.append(
                    {"text": text[:100], "sentiment": keyword_score, "method": "keyword"}
                )
                sentiment_scores.append(keyword_score)

        if sentiment_scores:
            avg_sentiment = np.mean(sentiment_scores)
        else:
            avg_sentiment = 0.5  # 中性

        return avg_sentiment, analyzed_texts

    def _analyze_with_keywords(self, text: str) -> float:
        """使用关键词分析情绪"""

        text_lower = text.lower()

        positive_count = 0
        negative_count = 0
        neutral_count = 0

        # 统计正面关键词
        for keyword in self.crypto_keywords["positive"]:
            if keyword.lower() in text_lower:
                positive_count += 1

        # 统计负面关键词
        for keyword in self.crypto_keywords["negative"]:
            if keyword.lower() in text_lower:
                negative_count += 1

        # 统计中性关键词
        for keyword in self.crypto_keywords["neutral"]:
            if keyword.lower() in text_lower:
                neutral_count += 1

        total_count = positive_count + negative_count + neutral_count

        if total_count == 0:
            return 0.5  # 中性

        # 计算情绪得分
        positive_weight = positive_count / total_count
        negative_weight = negative_count / total_count

        # 正面权重更高，负面权重更低
        sentiment_score = 0.5 + (positive_weight * 0.5) - (negative_weight * 0.5)

        return max(0.0, min(1.0, sentiment_score))

    def _generate_mock_sentiment_data(self, platform: str, symbol: str) -> Dict:
        """生成模拟情绪数据"""

        # 根据平台和币种生成不同的情绪模式
        base_sentiment = 0.5

        if platform == "twitter":
            # Twitter通常更活跃和极端
            base_sentiment += np.random.uniform(-0.2, 0.2)
            mention_count = int(np.random.uniform(1000, 10000))
        elif platform == "reddit":
            # Reddit讨论更深入
            base_sentiment += np.random.uniform(-0.15, 0.15)
            mention_count = int(np.random.uniform(500, 5000))
        elif platform == "weibo":
            # 微博情绪可能不同
            base_sentiment += np.random.uniform(-0.1, 0.1)
            mention_count = int(np.random.uniform(2000, 8000))
        elif platform == "telegram":
            # Telegram通常更积极
            base_sentiment += np.random.uniform(0, 0.1)
            mention_count = int(np.random.uniform(100, 1000))
        elif platform == "discord":
            # Discord社区讨论
            base_sentiment += np.random.uniform(-0.05, 0.05)
            mention_count = int(np.random.uniform(50, 500))
        else:
            mention_count = 0

        # 生成一些模拟文本
        mock_texts = [
            f"{symbol} looking bullish today!",
            f"Thinking about buying more {symbol}",
            f"{symbol} price action is interesting",
            f"Market sentiment for {symbol} seems positive",
            f"Watching {symbol} closely for entry",
        ]

        return {
            "sentiment_score": max(0.0, min(1.0, base_sentiment)),
            "mention_count": mention_count,
            "texts": mock_texts,
            "source": platform,
            "is_mock": True,
        }

    def _calculate_overall_sentiment(self, *platform_data) -> float:
        """计算综合情绪得分"""

        platform_weights = {
            "twitter": 0.3,  # Twitter权重最高
            "reddit": 0.25,  # Reddit权重次高
            "weibo": 0.2,  # 微博权重
            "telegram": 0.15,  # Telegram权重
            "discord": 0.1,  # Discord权重
        }

        weighted_sum = 0.0
        total_weight = 0.0

        for data in platform_data:
            if data and "source" in data and "sentiment_score" in data:
                source = data["source"]
                weight = platform_weights.get(source, 0.1)

                # 如果是模拟数据，降低权重
                if data.get("is_mock", False):
                    weight *= 0.5

                weighted_sum += data["sentiment_score"] * weight
                total_weight += weight

        if total_weight > 0:
            return weighted_sum / total_weight
        else:
            return 0.5  # 中性

    def _calculate_sentiment_strength(self, *platform_data) -> float:
        """计算情绪强度"""

        sentiment_scores = []

        for data in platform_data:
            if data and "sentiment_score" in data:
                score = data["sentiment_score"]
                # 距离中性的距离表示强度
                strength = abs(score - 0.5) * 2  # 映射到0-1
                sentiment_scores.append(strength)

        if sentiment_scores:
            return np.mean(sentiment_scores)
        else:
            return 0.0

    def _calculate_sentiment_consistency(self, *platform_data) -> float:
        """计算情绪一致性"""

        valid_scores = []

        for data in platform_data:
            if data and "sentiment_score" in data:
                valid_scores.append(data["sentiment_score"])

        if len(valid_scores) < 2:
            return 1.0  # 只有一个数据源，一致性为100%

        # 计算标准差，越低表示一致性越高
        std_dev = np.std(valid_scores)

        # 将标准差转换为一致性得分 (0-1)
        # 标准差为0时一致性为1，标准差为0.25时一致性为0
        consistency = max(0.0, 1.0 - (std_dev * 4))

        return consistency

    def _extract_keywords(self, texts: List[str]) -> Tuple[List[str], Dict[str, float]]:
        """提取关键词并分析情绪"""

        if not texts:
            return [], {}

        # 合并所有文本
        all_text = " ".join([str(t) for t in texts])

        # 简单的关键词提取（实际应该使用更复杂的方法）
        words = re.findall(r"\b[a-zA-Z]{3,}\b", all_text.lower())

        # 统计词频
        word_freq = Counter(words)

        # 过滤常见词
        common_words = {"the", "and", "for", "with", "this", "that", "have", "from", "they", "what"}
        filtered_words = {
            word: count
            for word, count in word_freq.items()
            if word not in common_words and count > 1
        }

        # 按频率排序
        top_keywords = [
            word for word, _ in sorted(filtered_words.items(), key=lambda x: x[1], reverse=True)
        ]

        # 分析关键词情绪
        keyword_sentiments = {}
        for keyword in top_keywords[:20]:  # 分析前20个关键词
            # 简单判断：如果关键词在正面列表中，情绪为正
            if keyword in [k.lower() for k in self.crypto_keywords["positive"]]:
                keyword_sentiments[keyword] = 0.8
            elif keyword in [k.lower() for k in self.crypto_keywords["negative"]]:
                keyword_sentiments[keyword] = 0.2
            elif keyword in [k.lower() for k in self.crypto_keywords["neutral"]]:
                keyword_sentiments[keyword] = 0.5
            else:
                # 中性
                keyword_sentiments[keyword] = 0.5

        return top_keywords[:10], keyword_sentiments

    def _calculate_mention_change(self, symbol: str, current_mention_count: int) -> float:
        """计算讨论热度变化"""

        if symbol not in self.sentiment_history:
            return 0.0

        history = self.sentiment_history[symbol]
        if len(history) < 2:
            return 0.0

        # 获取上一个时间点的提及次数
        prev_mention_count = history[-1].mention_count

        if prev_mention_count == 0:
            return 0.0

        # 计算变化百分比
        change = (current_mention_count - prev_mention_count) / prev_mention_count

        return change

    def _determine_sentiment_trend(self, symbol: str, current_sentiment: float) -> str:
        """确定情绪趋势"""

        if symbol not in self.sentiment_history:
            return "stable"

        history = self.sentiment_history[symbol]
        if len(history) < 3:
            return "stable"

        # 获取最近几个时间点的情绪
        recent_sentiments = [h.overall_sentiment for h in history[-3:]]
        recent_sentiments.append(current_sentiment)

        # 计算趋势
        if len(recent_sentiments) >= 2:
            changes = [
                recent_sentiments[i] - recent_sentiments[i - 1]
                for i in range(1, len(recent_sentiments))
            ]

            avg_change = np.mean(changes)

            if avg_change > 0.05:
                return "rising"
            elif avg_change < -0.05:
                return "falling"
            else:
                return "stable"

        return "stable"

    def _calculate_market_impact(
        self, sentiment: float, strength: float, mention_count: int
    ) -> float:
        """计算预期市场影响"""

        # 情绪强度权重
        strength_weight = strength

        # 讨论热度权重（标准化）
        mention_weight = min(1.0, mention_count / 10000)

        # 情绪方向（-1到1，0为中性）
        sentiment_direction = (sentiment - 0.5) * 2

        # 综合影响
        impact = sentiment_direction * strength_weight * mention_weight

        return impact

    def _update_sentiment_history(self, symbol: str, sentiment: SocialSentiment):
        """更新情绪历史"""

        if symbol not in self.sentiment_history:
            self.sentiment_history[symbol] = []

        self.sentiment_history[symbol].append(sentiment)

        # 保持历史记录长度
        if len(self.sentiment_history[symbol]) > 100:
            self.sentiment_history[symbol] = self.sentiment_history[symbol][-100:]

    def generate_sentiment_report(self, sentiment: SocialSentiment) -> Dict:
        """生成情绪分析报告"""

        if not sentiment:
            return {"error": "无情绪数据"}

        report = {
            "timestamp": sentiment.timestamp.isoformat(),
            "symbol": sentiment.symbol,
            "summary": {
                "overall_sentiment": sentiment.overall_sentiment,
                "sentiment_trend": sentiment.sentiment_trend,
                "market_impact": sentiment.market_impact,
                "recommendation": self._generate_sentiment_recommendation(sentiment),
            },
            "platform_sentiments": {
                "twitter": {
                    "score": sentiment.twitter_sentiment,
                    "interpretation": self._interpret_platform_sentiment(
                        "twitter", sentiment.twitter_sentiment
                    ),
                },
                "reddit": {
                    "score": sentiment.reddit_sentiment,
                    "interpretation": self._interpret_platform_sentiment(
                        "reddit", sentiment.reddit_sentiment
                    ),
                },
                "weibo": {
                    "score": sentiment.weibo_sentiment,
                    "interpretation": self._interpret_platform_sentiment(
                        "weibo", sentiment.weibo_sentiment
                    ),
                },
            },
            "metrics": {
                "mention_count": sentiment.mention_count,
                "mention_change": f"{sentiment.mention_change:.1%}",
                "sentiment_strength": sentiment.sentiment_strength,
                "sentiment_consistency": sentiment.sentiment_consistency,
            },
            "keywords": {
                "top_keywords": sentiment.top_keywords,
                "keyword_sentiments": sentiment.keyword_sentiments,
            },
        }

        return report

    def _generate_sentiment_recommendation(self, sentiment: SocialSentiment) -> str:
        """生成基于情绪的交易建议"""

        overall = sentiment.overall_sentiment
        trend = sentiment.sentiment_trend
        impact = sentiment.market_impact

        if overall > 0.7 and trend == "rising" and impact > 0.3:
            return "STRONG_BUY - 社交媒体极度看涨且情绪上升"
        elif overall > 0.6 and impact > 0.2:
            return "BUY - 社交媒体看涨情绪强烈"
        elif overall > 0.55 and trend == "rising":
            return "HOLD/BUY - 社交媒体情绪转好"
        elif overall > 0.45 and overall < 0.55:
            return "HOLD - 社交媒体情绪中性"
        elif overall < 0.45 and trend == "falling":
            return "HOLD/SELL - 社交媒体情绪转差"
        elif overall < 0.4 and impact < -0.2:
            return "SELL - 社交媒体看跌情绪强烈"
        elif overall < 0.3 and trend == "falling" and impact < -0.3:
            return "STRONG_SELL - 社交媒体极度看跌且情绪恶化"
        else:
            return "HOLD - 社交媒体信号不明确"

    def _interpret_platform_sentiment(self, platform: str, score: float) -> str:
        """解释平台情绪得分"""

        if score > 0.7:
            return f"{platform}情绪极度看涨"
        elif score > 0.6:
            return f"{platform}情绪看涨"
        elif score > 0.55:
            return f"{platform}情绪略微看涨"
        elif score > 0.45:
            return f"{platform}情绪中性"
        elif score > 0.4:
            return f"{platform}情绪略微看跌"
        elif score > 0.3:
            return f"{platform}情绪看跌"
        else:
            return f"{platform}情绪极度看跌"


# 单例实例
_sentiment_analyzer = None


def get_sentiment_analyzer(config_manager=None):
    """获取情绪分析器单例"""
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        from ...core.config_manager import get_config_manager

        config = config_manager or get_config_manager()
        _sentiment_analyzer = SocialSentimentAnalyzer(config)
    return _sentiment_analyzer
