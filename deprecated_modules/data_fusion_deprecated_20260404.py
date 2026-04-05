from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Union

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.decomposition import PCA

from src.modules.core.data_pipeline import DataPoint
from src.modules.core.database_manager import DatabaseManager

logger = logging.getLogger(__name__)


class DataSourceType(Enum):
    """数据源类型"""
    MARKET = "market"  # 市场数据
    ONCHAIN = "onchain"  # 链上数据
    SOCIAL = "social"  # 社交媒体数据
    NEWS = "news"  # 新闻数据
    MACRO = "macro"  # 宏观经济数据


class DataQualityLevel(Enum):
    """数据质量等级"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    INVALID = "invalid"


@dataclass
class DataSourceConfig:
    """数据源配置"""
    name: str
    type: DataSourceType
    url: str
    api_key: Optional[str] = None
    refresh_interval: int = 60  # 刷新间隔（秒）
    enabled: bool = True


@dataclass
class FusedDataPoint:
    """融合数据点"""
    timestamp: float
    symbol: str
    data: Dict[str, Any]
    sources: List[str]
    quality_score: float
    confidence: float


class DataFusionSystem:
    """数据融合系统"""

    def __init__(self, db_manager: DatabaseManager, config: Dict[str, Any]):
        """初始化数据融合系统

        Args:
            db_manager: 数据库管理器
            config: 配置信息
        """
        self.db_manager = db_manager
        self.config = config
        self.data_sources = {}
        self.data_cache = {}
        self.quality_scores = {}
        self.scalers = {}
        self.pca_models = {}
        self.enabled = False

    async def initialize(self) -> bool:
        """初始化数据融合系统

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 加载数据源配置
            source_configs = self.config.get("data_sources", [])
            for config in source_configs:
                source = DataSourceConfig(**config)
                self.data_sources[source.name] = source
                self.data_cache[source.name] = []
                self.quality_scores[source.name] = DataQualityLevel.GOOD

            # 初始化数据采集任务
            asyncio.create_task(self._collect_data_loop())

            self.enabled = True
            logger.info("DataFusionSystem initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize DataFusionSystem: {e}")
            return False

    async def shutdown(self) -> bool:
        """关闭数据融合系统

        Returns:
            bool: 关闭是否成功
        """
        try:
            self.enabled = False
            self.data_sources.clear()
            self.data_cache.clear()
            self.quality_scores.clear()
            self.scalers.clear()
            self.pca_models.clear()
            logger.info("DataFusionSystem shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown DataFusionSystem: {e}")
            return False

    async def _collect_data_loop(self):
        """数据采集循环"""
        while self.enabled:
            for source_name, source_config in self.data_sources.items():
                if source_config.enabled:
                    try:
                        data = await self._collect_data(source_name, source_config)
                        if data:
                            self.data_cache[source_name].extend(data)
                            # 限制缓存大小
                            if len(self.data_cache[source_name]) > 1000:
                                self.data_cache[source_name] = self.data_cache[source_name][-1000:]
                    except Exception as e:
                        logger.error(f"Error collecting data from {source_name}: {e}")
                        self.quality_scores[source_name] = DataQualityLevel.POOR
            
            await asyncio.sleep(10)  # 每10秒检查一次

    async def _collect_data(self, source_name: str, config: DataSourceConfig) -> List[DataPoint]:
        """从数据源采集数据

        Args:
            source_name: 数据源名称
            config: 数据源配置

        Returns:
            List[DataPoint]: 数据点列表
        """
        # 这里应该实现实际的数据采集逻辑
        # 暂时返回模拟数据
        if config.type == DataSourceType.MARKET:
            return await self._mock_market_data(source_name)
        elif config.type == DataSourceType.ONCHAIN:
            return await self._mock_onchain_data(source_name)
        elif config.type == DataSourceType.SOCIAL:
            return await self._mock_social_data(source_name)
        elif config.type == DataSourceType.NEWS:
            return await self._mock_news_data(source_name)
        elif config.type == DataSourceType.MACRO:
            return await self._mock_macro_data(source_name)
        else:
            return []

    async def _mock_market_data(self, source_name: str) -> List[DataPoint]:
        """模拟市场数据"""
        timestamp = time.time()
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        data_points = []
        
        for symbol in symbols:
            price = 50000 + np.random.normal(0, 1000)
            volume = 1000000 + np.random.normal(0, 100000)
            data = {
                "price": price,
                "volume": volume,
                "high": price * (1 + np.random.normal(0, 0.01)),
                "low": price * (1 - np.random.normal(0, 0.01)),
                "open": price * (1 + np.random.normal(0, 0.005)),
                "close": price
            }
            data_points.append(DataPoint(
                symbol=symbol,
                timestamp=timestamp,
                data=data,
                source=source_name
            ))
        
        return data_points

    async def _mock_onchain_data(self, source_name: str) -> List[DataPoint]:
        """模拟链上数据"""
        timestamp = time.time()
        symbols = ["BTC", "ETH"]
        data_points = []
        
        for symbol in symbols:
            data = {
                "hash_rate": 200 + np.random.normal(0, 10),
                "difficulty": 300000000000 + np.random.normal(0, 10000000000),
                "active_addresses": 1000000 + np.random.normal(0, 100000),
                "transaction_count": 300000 + np.random.normal(0, 10000),
                "block_height": 800000 + np.random.normal(0, 1000)
            }
            data_points.append(DataPoint(
                symbol=symbol,
                timestamp=timestamp,
                data=data,
                source=source_name
            ))
        
        return data_points

    async def _mock_social_data(self, source_name: str) -> List[DataPoint]:
        """模拟社交媒体数据"""
        timestamp = time.time()
        symbols = ["BTC", "ETH"]
        data_points = []
        
        for symbol in symbols:
            data = {
                "mention_count": 10000 + np.random.normal(0, 1000),
                "sentiment_score": np.random.normal(0, 0.5),
                "engagement_rate": 0.05 + np.random.normal(0, 0.01),
                "positive_mentions": 6000 + np.random.normal(0, 500),
                "negative_mentions": 2000 + np.random.normal(0, 300)
            }
            data_points.append(DataPoint(
                symbol=symbol,
                timestamp=timestamp,
                data=data,
                source=source_name
            ))
        
        return data_points

    async def _mock_news_data(self, source_name: str) -> List[DataPoint]:
        """模拟新闻数据"""
        timestamp = time.time()
        symbols = ["BTC", "ETH"]
        data_points = []
        
        for symbol in symbols:
            data = {
                "news_count": 50 + np.random.normal(0, 10),
                "sentiment_score": np.random.normal(0, 0.3),
                "relevance_score": 0.7 + np.random.normal(0, 0.1),
                "impact_score": 0.5 + np.random.normal(0, 0.2)
            }
            data_points.append(DataPoint(
                symbol=symbol,
                timestamp=timestamp,
                data=data,
                source=source_name
            ))
        
        return data_points

    async def _mock_macro_data(self, source_name: str) -> List[DataPoint]:
        """模拟宏观经济数据"""
        timestamp = time.time()
        data_points = []
        
        data = {
            "inflation_rate": 2.5 + np.random.normal(0, 0.5),
            "interest_rate": 3.0 + np.random.normal(0, 0.25),
            "gdp_growth": 2.0 + np.random.normal(0, 0.5),
            "unemployment_rate": 4.0 + np.random.normal(0.2),
            "dollar_index": 100 + np.random.normal(0, 2)
        }
        data_points.append(DataPoint(
            symbol="MACRO",
            timestamp=timestamp,
            data=data,
            source=source_name
        ))
        
        return data_points

    async def fuse_data(self, symbol: str, time_window: int = 3600) -> Optional[FusedDataPoint]:
        """融合多源数据

        Args:
            symbol: 交易对
            time_window: 时间窗口（秒）

        Returns:
            Optional[FusedDataPoint]: 融合数据点
        """
        try:
            if not self.enabled:
                logger.warning("DataFusionSystem is not enabled")
                return None

            # 收集时间窗口内的数据
            current_time = time.time()
            start_time = current_time - time_window

            # 从所有数据源收集数据
            all_data = []
            sources_used = []

            for source_name, data_list in self.data_cache.items():
                relevant_data = [d for d in data_list if d.symbol == symbol and d.timestamp >= start_time]
                if relevant_data:
                    all_data.extend(relevant_data)
                    sources_used.append(source_name)

            if not all_data:
                logger.warning(f"No data available for {symbol} in the last {time_window} seconds")
                return None

            # 数据预处理
            processed_data = await self._preprocess_data(all_data)

            # 特征提取和选择
            features = await self._extract_features(processed_data)

            # 数据融合
            fused_data = await self._fuse_features(features, sources_used)

            # 计算质量分数和置信度
            quality_score = await self._calculate_quality_score(sources_used)
            confidence = await self._calculate_confidence(features)

            # 创建融合数据点
            fused_point = FusedDataPoint(
                timestamp=current_time,
                symbol=symbol,
                data=fused_data,
                sources=sources_used,
                quality_score=quality_score,
                confidence=confidence
            )

            return fused_point
        except Exception as e:
            logger.error(f"Error fusing data: {e}")
            return None

    async def _preprocess_data(self, data_points: List[DataPoint]) -> pd.DataFrame:
        """预处理数据

        Args:
            data_points: 数据点列表

        Returns:
            pd.DataFrame: 预处理后的数据
        """
        # 转换为DataFrame
        data_list = []
        for dp in data_points:
            row = {
                "timestamp": dp.timestamp,
                "symbol": dp.symbol,
                "source": dp.source,
                **dp.data
            }
            data_list.append(row)

        df = pd.DataFrame(data_list)

        # 处理缺失值
        df = df.fillna(method="ffill").fillna(method="bfill")

        # 标准化数据
        numeric_columns = df.select_dtypes(include=[np.number]).columns
        for col in numeric_columns:
            if col not in ["timestamp"]:
                if col not in self.scalers:
                    self.scalers[col] = MinMaxScaler()
                    self.scalers[col].fit(df[[col]])
                df[col] = self.scalers[col].transform(df[[col]])

        return df

    async def _extract_features(self, data: pd.DataFrame) -> Dict[str, Any]:
        """提取特征

        Args:
            data: 预处理后的数据

        Returns:
            Dict[str, Any]: 提取的特征
        """
        features = {}

        # 按数据源分组提取特征
        for source in data["source"].unique():
            source_data = data[data["source"] == source]
            if not source_data.empty:
                # 计算统计特征
                numeric_columns = source_data.select_dtypes(include=[np.number]).columns
                for col in numeric_columns:
                    if col not in ["timestamp"]:
                        features[f"{source}_{col}_mean"] = source_data[col].mean()
                        features[f"{source}_{col}_std"] = source_data[col].std()
                        features[f"{source}_{col}_max"] = source_data[col].max()
                        features[f"{source}_{col}_min"] = source_data[col].min()
                        features[f"{source}_{col}_trend"] = self._calculate_trend(source_data[col].values)

        # 跨数据源特征
        if len(data["source"].unique()) > 1:
            features["data_diversity"] = len(data["source"].unique())
            features["data_volume"] = len(data)

        return features

    def _calculate_trend(self, values: np.ndarray) -> float:
        """计算趋势

        Args:
            values: 值数组

        Returns:
            float: 趋势值
        """
        if len(values) < 2:
            return 0.0
        x = np.arange(len(values))
        slope = np.polyfit(x, values, 1)[0]
        return slope

    async def _fuse_features(self, features: Dict[str, Any], sources: List[str]) -> Dict[str, Any]:
        """融合特征

        Args:
            features: 提取的特征
            sources: 使用的数据源

        Returns:
            Dict[str, Any]: 融合后的数据
        """
        fused_data = {}

        # 按数据源类型分组融合
        source_types = {}
        for source in sources:
            source_config = self.data_sources.get(source)
            if source_config:
                if source_config.type not in source_types:
                    source_types[source_config.type] = []
                source_types[source_config.type].append(source)

        # 融合市场数据
        if DataSourceType.MARKET in source_types:
            market_sources = source_types[DataSourceType.MARKET]
            market_features = {k: v for k, v in features.items() if any(s in k for s in market_sources)}
            if market_features:
                fused_data["market_price"] = np.mean([v for k, v in market_features.items() if "price" in k and "mean" in k])
                fused_data["market_volume"] = np.mean([v for k, v in market_features.items() if "volume" in k and "mean" in k])
                fused_data["market_volatility"] = np.mean([v for k, v in market_features.items() if "price" in k and "std" in k])

        # 融合链上数据
        if DataSourceType.ONCHAIN in source_types:
            onchain_sources = source_types[DataSourceType.ONCHAIN]
            onchain_features = {k: v for k, v in features.items() if any(s in k for s in onchain_sources)}
            if onchain_features:
                fused_data["onchain_activity"] = np.mean([v for k, v in onchain_features.items() if "active_addresses" in k or "transaction_count" in k])
                fused_data["onchain_difficulty"] = np.mean([v for k, v in onchain_features.items() if "difficulty" in k and "mean" in k])

        # 融合社交媒体数据
        if DataSourceType.SOCIAL in source_types:
            social_sources = source_types[DataSourceType.SOCIAL]
            social_features = {k: v for k, v in features.items() if any(s in k for s in social_sources)}
            if social_features:
                fused_data["social_sentiment"] = np.mean([v for k, v in social_features.items() if "sentiment_score" in k])
                fused_data["social_engagement"] = np.mean([v for k, v in social_features.items() if "engagement_rate" in k])

        # 融合新闻数据
        if DataSourceType.NEWS in source_types:
            news_sources = source_types[DataSourceType.NEWS]
            news_features = {k: v for k, v in features.items() if any(s in k for s in news_sources)}
            if news_features:
                fused_data["news_sentiment"] = np.mean([v for k, v in news_features.items() if "sentiment_score" in k])
                fused_data["news_impact"] = np.mean([v for k, v in news_features.items() if "impact_score" in k])

        # 融合宏观经济数据
        if DataSourceType.MACRO in source_types:
            macro_sources = source_types[DataSourceType.MACRO]
            macro_features = {k: v for k, v in features.items() if any(s in k for s in macro_sources)}
            if macro_features:
                fused_data["macro_conditions"] = np.mean([v for k, v in macro_features.values()])

        # 添加融合特征
        fused_data["data_quality"] = len(sources) / len(self.data_sources)
        fused_data["confidence"] = self._calculate_overall_confidence(features)

        return fused_data

    def _calculate_overall_confidence(self, features: Dict[str, Any]) -> float:
        """计算整体置信度

        Args:
            features: 提取的特征

        Returns:
            float: 整体置信度
        """
        # 基于特征数量和一致性计算置信度
        feature_count = len(features)
        if feature_count == 0:
            return 0.0

        # 计算特征一致性（标准差的倒数）
        values = list(features.values())
        if len(values) > 1:
            std = np.std(values)
            consistency = 1.0 / (std + 0.001)  # 避免除零
        else:
            consistency = 1.0

        # 综合计算置信度
        confidence = min(1.0, (feature_count / 50) * consistency)
        return confidence

    async def _calculate_quality_score(self, sources: List[str]) -> float:
        """计算数据质量分数

        Args:
            sources: 使用的数据源

        Returns:
            float: 质量分数
        """
        if not sources:
            return 0.0

        quality_scores = []
        for source in sources:
            quality = self.quality_scores.get(source, DataQualityLevel.FAIR)
            if quality == DataQualityLevel.EXCELLENT:
                quality_scores.append(1.0)
            elif quality == DataQualityLevel.GOOD:
                quality_scores.append(0.8)
            elif quality == DataQualityLevel.FAIR:
                quality_scores.append(0.6)
            elif quality == DataQualityLevel.POOR:
                quality_scores.append(0.4)
            else:
                quality_scores.append(0.2)

        return np.mean(quality_scores)

    async def _calculate_confidence(self, features: Dict[str, Any]) -> float:
        """计算置信度

        Args:
            features: 提取的特征

        Returns:
            float: 置信度
        """
        if not features:
            return 0.0

        # 基于特征数量和多样性计算置信度
        feature_count = len(features)
        source_diversity = len(set([k.split('_')[0] for k in features.keys()]))

        confidence = min(1.0, (feature_count / 20) * (source_diversity / 5))
        return confidence

    async def get_data_quality(self, source_name: Optional[str] = None) -> Dict[str, Any]:
        """获取数据质量

        Args:
            source_name: 数据源名称，如果为None则返回所有数据源的质量

        Returns:
            Dict[str, Any]: 数据质量信息
        """
        if source_name:
            return {
                source_name: {
                    "quality": self.quality_scores.get(source_name, DataQualityLevel.FAIR).value,
                    "data_count": len(self.data_cache.get(source_name, []))
                }
            }
        else:
            quality_info = {}
            for source_name in self.data_sources:
                quality_info[source_name] = {
                    "quality": self.quality_scores.get(source_name, DataQualityLevel.FAIR).value,
                    "data_count": len(self.data_cache.get(source_name, []))
                }
            return quality_info

    def is_healthy(self) -> bool:
        """检查数据融合系统健康状态

        Returns:
            bool: 健康状态
        """
        return self.enabled and len(self.data_sources) > 0