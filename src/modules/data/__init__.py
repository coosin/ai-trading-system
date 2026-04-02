"""
数据模块 - 多源数据采集与融合
包含链上数据、第三方数据、实时数据采集等功能
"""
from .onchain_integrator import (
    OnChainDataIntegrator,
    OnChainDataProvider,
    GlassnodeProvider,
    CryptoQuantProvider,
    OnChainData,
    onchain_integrator
)

from .third_party_data_integrator import (
    ThirdPartyDataIntegrator,
    TwitterProvider,
    RedditProvider,
    NewsProvider,
    FearGreedIndexProvider,
    LunarCrushProvider,
    SocialMention,
    NewsArticle,
    MarketSentiment,
    DataSource,
    third_party_integrator
)

__all__ = [
    "OnChainDataIntegrator",
    "OnChainDataProvider",
    "GlassnodeProvider",
    "CryptoQuantProvider",
    "OnChainData",
    "onchain_integrator",
    "ThirdPartyDataIntegrator",
    "TwitterProvider",
    "RedditProvider",
    "NewsProvider",
    "FearGreedIndexProvider",
    "LunarCrushProvider",
    "SocialMention",
    "NewsArticle",
    "MarketSentiment",
    "DataSource",
    "third_party_integrator"
]
