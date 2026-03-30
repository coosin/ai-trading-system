#!/usr/bin/env python3
"""
数据融合引擎
融合多源数据，生成综合交易信号
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..core.data_sources.onchain_analyzer import OnChainMetrics, get_onchain_analyzer
from .decision_engine.multi_model import Decision, TradingSignal
from .sentiment_analyzer.social_sentiment import SocialSentiment, get_sentiment_analyzer


@dataclass
class FusedData:
    """融合数据"""

    timestamp: datetime
    symbol: str

    # 原始数据源
    market_data: Dict = field(default_factory=dict)  # 市场数据
    onchain_metrics: Optional[OnChainMetrics] = None  # 链上数据
    social_sentiment: Optional[SocialSentiment] = None  # 社交媒体情绪
    technical_signals: Dict = field(default_factory=dict)  # 技术信号

    # 融合后的综合指标
    data_quality_score: float = 0.0  # 数据质量得分 (0-1)
    data_consistency_score: float = 0.0  # 数据一致性得分 (0-1)
    overall_confidence: float = 0.0  # 综合置信度 (0-1)

    # 各维度得分
    technical_score: float = 0.5  # 技术分析得分
    onchain_score: float = 0.5  # 链上分析得分
    sentiment_score: float = 0.5  # 情绪分析得分

    # 风险指标
    risk_score: float = 0.5  # 风险得分 (0-1, 越高风险越大)
    volatility_score: float = 0.5  # 波动性得分

    # 融合信号
    fused_signal: Optional[TradingSignal] = None
    signal_strength: float = 0.0  # 信号强度
    signal_consistency: float = 0.0  # 信号一致性


@dataclass
class DataSourceWeight:
    """数据源权重配置"""

    technical_weight: float = 0.35  # 技术分析权重
    onchain_weight: float = 0.35  # 链上分析权重
    sentiment_weight: float = 0.20  # 情绪分析权重
    market_weight: float = 0.10  # 市场结构权重

    # 动态调整参数
    min_weight: float = 0.1  # 最小权重
    max_weight: float = 0.6  # 最大权重
    learning_rate: float = 0.01  # 学习率


class DataFusionEngine:
    """数据融合引擎"""

    def __init__(self, config_manager):
        self.config = config_manager

        # 数据源实例
        self.onchain_analyzer = get_onchain_analyzer(config_manager)
        self.sentiment_analyzer = get_sentiment_analyzer(config_manager)

        # 权重配置
        self.weights = DataSourceWeight()

        # 历史表现记录
        self.performance_history = []

        # 数据缓存
        self.data_cache = {}
        self.cache_ttl = 300  # 5分钟

    async def fuse_data(self, symbol: str, market_data: Dict) -> Optional[FusedData]:
        """融合多源数据"""

        try:
            # 并行获取所有数据源
            tasks = [
                self._get_market_indicators(symbol, market_data),
                self._get_onchain_data(symbol),
                self._get_sentiment_data(symbol),
                self._analyze_market_structure(symbol, market_data),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 处理结果
            technical_signals = results[0] if not isinstance(results[0], Exception) else {}
            onchain_metrics = results[1] if not isinstance(results[1], Exception) else None
            social_sentiment = results[2] if not isinstance(results[2], Exception) else None
            market_structure = results[3] if not isinstance(results[3], Exception) else {}

            # 计算数据质量
            data_quality = self._calculate_data_quality(
                technical_signals, onchain_metrics, social_sentiment, market_structure
            )

            # 计算数据一致性
            data_consistency = self._calculate_data_consistency(
                technical_signals, onchain_metrics, social_sentiment
            )

            # 计算各维度得分
            technical_score = self._calculate_technical_score(technical_signals)
            onchain_score = self._calculate_onchain_score(onchain_metrics)
            sentiment_score = self._calculate_sentiment_score(social_sentiment)

            # 计算风险指标
            risk_score = self._calculate_risk_score(
                technical_signals, onchain_metrics, social_sentiment
            )

            volatility_score = self._calculate_volatility_score(market_data)

            # 动态调整权重
            await self._adjust_weights_based_on_performance()

            # 计算综合置信度
            overall_confidence = self._calculate_overall_confidence(
                data_quality, data_consistency, technical_score, onchain_score, sentiment_score
            )

            # 生成融合信号
            fused_signal = await self._generate_fused_signal(
                symbol, technical_signals, onchain_metrics, social_sentiment, market_structure
            )

            # 构建融合数据对象
            fused_data = FusedData(
                timestamp=datetime.now(),
                symbol=symbol,
                market_data=market_data,
                onchain_metrics=onchain_metrics,
                social_sentiment=social_sentiment,
                technical_signals=technical_signals,
                data_quality_score=data_quality,
                data_consistency_score=data_consistency,
                overall_confidence=overall_confidence,
                technical_score=technical_score,
                onchain_score=onchain_score,
                sentiment_score=sentiment_score,
                risk_score=risk_score,
                volatility_score=volatility_score,
                fused_signal=fused_signal,
                signal_strength=(
                    self._calculate_signal_strength(fused_signal) if fused_signal else 0.0
                ),
                signal_consistency=(
                    self._calculate_signal_consistency(fused_signal, symbol)
                    if fused_signal
                    else 0.0
                ),
            )

            # 记录性能
            self._record_performance(fused_data)

            return fused_data

        except Exception as e:
            print(f"数据融合失败: {e}")
            return None

    async def _get_market_indicators(self, symbol: str, market_data: Dict) -> Dict:
        """获取技术指标"""

        try:
            # 从market_data中提取或计算技术指标
            indicators = market_data.get("indicators", {})

            # 计算额外的技术信号
            technical_signals = {
                "trend": self._analyze_trend(indicators),
                "momentum": self._analyze_momentum(indicators),
                "volatility": self._analyze_volatility(indicators),
                "volume": self._analyze_volume(indicators),
                "support_resistance": self._identify_support_resistance(market_data),
            }

            # 生成技术信号得分
            technical_score = self._calculate_technical_aggregate(technical_signals)
            technical_signals["overall_score"] = technical_score
            technical_signals["signal"] = self._generate_technical_signal(technical_score)

            return technical_signals

        except Exception as e:
            print(f"获取技术指标失败: {e}")
            return {}

    def _analyze_trend(self, indicators: Dict) -> Dict:
        """分析趋势"""

        try:
            # 使用移动平均线判断趋势
            trend_signals = {}

            if "sma_20" in indicators and "sma_50" in indicators:
                sma_20 = indicators["sma_20"]
                sma_50 = indicators["sma_50"]

                if sma_20 > sma_50:
                    trend_signals["direction"] = "bullish"
                    trend_signals["strength"] = (sma_20 - sma_50) / sma_50
                else:
                    trend_signals["direction"] = "bearish"
                    trend_signals["strength"] = (sma_50 - sma_20) / sma_20

            # 使用MACD判断趋势
            if "macd" in indicators and "macd_signal" in indicators:
                macd = indicators["macd"]
                macd_signal = indicators["macd_signal"]

                if macd > macd_signal:
                    trend_signals["macd_signal"] = "bullish"
                else:
                    trend_signals["macd_signal"] = "bearish"

            # 综合趋势判断
            if "direction" in trend_signals:
                if trend_signals["direction"] == "bullish":
                    trend_signals["score"] = 0.5 + min(0.5, trend_signals.get("strength", 0) * 5)
                else:
                    trend_signals["score"] = 0.5 - min(0.5, trend_signals.get("strength", 0) * 5)
            else:
                trend_signals["score"] = 0.5

            return trend_signals

        except Exception as e:
            print(f"趋势分析失败: {e}")
            return {"score": 0.5, "direction": "neutral"}

    def _analyze_momentum(self, indicators: Dict) -> Dict:
        """分析动量"""

        try:
            momentum_signals = {}

            # RSI动量
            if "rsi" in indicators:
                rsi = indicators["rsi"]
                momentum_signals["rsi"] = rsi

                if rsi > 70:
                    momentum_signals["rsi_signal"] = "overbought"
                    momentum_signals["rsi_score"] = 0.3
                elif rsi < 30:
                    momentum_signals["rsi_signal"] = "oversold"
                    momentum_signals["rsi_score"] = 0.7
                else:
                    momentum_signals["rsi_signal"] = "neutral"
                    momentum_signals["rsi_score"] = 0.5

            # 随机指标
            if "stoch_k" in indicators and "stoch_d" in indicators:
                k = indicators["stoch_k"]
                d = indicators["stoch_d"]

                if k > 80 and d > 80:
                    momentum_signals["stoch_signal"] = "overbought"
                    momentum_signals["stoch_score"] = 0.3
                elif k < 20 and d < 20:
                    momentum_signals["stoch_signal"] = "oversold"
                    momentum_signals["stoch_score"] = 0.7
                else:
                    momentum_signals["stoch_signal"] = "neutral"
                    momentum_signals["stoch_score"] = 0.5

            # 综合动量得分
            momentum_scores = [v for k, v in momentum_signals.items() if "score" in k]
            if momentum_scores:
                momentum_signals["overall_score"] = np.mean(momentum_scores)
            else:
                momentum_signals["overall_score"] = 0.5

            return momentum_signals

        except Exception as e:
            print(f"动量分析失败: {e}")
            return {"overall_score": 0.5}

    def _analyze_volatility(self, indicators: Dict) -> Dict:
        """分析波动性"""

        try:
            volatility_signals = {}

            # ATR波动率
            if "atr" in indicators and "close" in indicators:
                atr = indicators["atr"]
                close = indicators["close"]

                if close > 0:
                    atr_percent = atr / close
                    volatility_signals["atr_percent"] = atr_percent

                    # 波动率得分 (0-1, 0.5为正常)
                    if atr_percent > 0.05:
                        volatility_signals["score"] = 0.3  # 高波动，风险高
                    elif atr_percent < 0.01:
                        volatility_signals["score"] = 0.7  # 低波动，风险低
                    else:
                        volatility_signals["score"] = 0.5

            # 布林带宽度
            if "bb_upper" in indicators and "bb_lower" in indicators and "close" in indicators:
                bb_width = (indicators["bb_upper"] - indicators["bb_lower"]) / indicators["close"]
                volatility_signals["bb_width"] = bb_width

            if "score" not in volatility_signals:
                volatility_signals["score"] = 0.5

            return volatility_signals

        except Exception as e:
            print(f"波动性分析失败: {e}")
            return {"score": 0.5}

    def _analyze_volume(self, indicators: Dict) -> Dict:
        """分析成交量"""

        try:
            volume_signals = {}

            # 成交量指标
            if "volume" in indicators and "volume_ma" in indicators:
                volume = indicators["volume"]
                volume_ma = indicators["volume_ma"]

                if volume_ma > 0:
                    volume_ratio = volume / volume_ma
                    volume_signals["volume_ratio"] = volume_ratio

                    if volume_ratio > 1.5:
                        volume_signals["signal"] = "high_volume"
                        volume_signals["score"] = 0.7  # 高成交量通常看涨
                    elif volume_ratio < 0.5:
                        volume_signals["signal"] = "low_volume"
                        volume_signals["score"] = 0.4  # 低成交量通常看跌
                    else:
                        volume_signals["signal"] = "normal_volume"
                        volume_signals["score"] = 0.5

            # OBV能量潮
            if "obv" in indicators and "obv_ma" in indicators:
                obv_trend = indicators["obv"] - indicators["obv_ma"]
                if obv_trend > 0:
                    volume_signals["obv_signal"] = "bullish"
                else:
                    volume_signals["obv_signal"] = "bearish"

            if "score" not in volume_signals:
                volume_signals["score"] = 0.5

            return volume_signals

        except Exception as e:
            print(f"成交量分析失败: {e}")
            return {"score": 0.5}

    def _identify_support_resistance(self, market_data: Dict) -> Dict:
        """识别支撑阻力位"""

        try:
            # 简化的支撑阻力识别
            # 实际应该使用更复杂的算法
            sr_signals = {}

            # 使用近期高低点作为支撑阻力
            klines = market_data.get("klines", [])
            if len(klines) >= 20:
                recent_highs = [k["high"] for k in klines[-20:]]
                recent_lows = [k["low"] for k in klines[-20:]]

                current_price = market_data.get("price", 0)

                if current_price > 0:
                    resistance = max(recent_highs)
                    support = min(recent_lows)

                    sr_signals["resistance"] = resistance
                    sr_signals["support"] = support

                    # 计算距离支撑阻力的距离
                    distance_to_resistance = (resistance - current_price) / current_price
                    distance_to_support = (current_price - support) / current_price

                    sr_signals["distance_to_resistance"] = distance_to_resistance
                    sr_signals["distance_to_support"] = distance_to_support

                    # 判断当前位置
                    if distance_to_resistance < 0.02:  # 接近阻力
                        sr_signals["position"] = "near_resistance"
                        sr_signals["score"] = 0.4  # 看跌
                    elif distance_to_support < 0.02:  # 接近支撑
                        sr_signals["position"] = "near_support"
                        sr_signals["score"] = 0.6  # 看涨
                    else:
                        sr_signals["position"] = "middle"
                        sr_signals["score"] = 0.5

            if "score" not in sr_signals:
                sr_signals["score"] = 0.5

            return sr_signals

        except Exception as e:
            print(f"支撑阻力识别失败: {e}")
            return {"score": 0.5}

    def _calculate_technical_aggregate(self, technical_signals: Dict) -> float:
        """计算技术信号综合得分"""

        try:
            scores = []
            weights = {
                "trend": 0.3,
                "momentum": 0.25,
                "volume": 0.2,
                "support_resistance": 0.15,
                "volatility": 0.1,
            }

            for signal_name, weight in weights.items():
                if signal_name in technical_signals:
                    signal_data = technical_signals[signal_name]
                    if "score" in signal_data:
                        scores.append(signal_data["score"] * weight)

            if scores:
                return np.sum(scores) / sum(weights.values())
            else:
                return 0.5

        except Exception as e:
            print(f"技术信号聚合失败: {e}")
            return 0.5

    def _generate_technical_signal(self, technical_score: float) -> str:
        """生成技术信号"""

        if technical_score > 0.7:
            return "STRONG_BUY"
        elif technical_score > 0.6:
            return "BUY"
        elif technical_score > 0.55:
            return "WEAK_BUY"
        elif technical_score > 0.45:
            return "NEUTRAL"
        elif technical_score > 0.4:
            return "WEAK_SELL"
        elif technical_score > 0.3:
            return "SELL"
        else:
            return "STRONG_SELL"

    async def _get_onchain_data(self, symbol: str) -> Optional[OnChainMetrics]:
        """获取链上数据"""

        try:
            return await self.onchain_analyzer.fetch_onchain_data(symbol)
        except Exception as e:
            print(f"获取链上数据失败: {e}")
            return None

    async def _get_sentiment_data(self, symbol: str) -> Optional[SocialSentiment]:
        """获取情绪数据"""

        try:
            return await self.sentiment_analyzer.analyze_social_sentiment(symbol)
        except Exception as e:
            print(f"获取情绪数据失败: {e}")
            return None

    async def _analyze_market_structure(self, symbol: str, market_data: Dict) -> Dict:
        """分析市场结构"""

        try:
            structure_signals = {}

            # 订单簿分析
            order_book = market_data.get("order_book", {})
            if order_book:
                bids = order_book.get("bids", [])
                asks = order_book.get("asks", [])

                if bids and asks:
                    # 计算买卖压力
                    total_bid_volume = sum(qty for _, qty in bids[:10])
                    total_ask_volume = sum(qty for _, qty in asks[:10])

                    if total_bid_volume + total_ask_volume > 0:
                        bid_ask_ratio = total_bid_volume / (total_bid_volume + total_ask_volume)
                        structure_signals["bid_ask_ratio"] = bid_ask_ratio

                        if bid_ask_ratio > 0.6:
                            structure_signals["pressure"] = "buying"
                            structure_signals["score"] = 0.7
                        elif bid_ask_ratio < 0.4:
                            structure_signals["pressure"] = "selling"
                            structure_signals["score"] = 0.3
                        else:
                            structure_signals["pressure"] = "balanced"
                            structure_signals["score"] = 0.5

            # 流动性分析
            liquidity_score = self._analyze_liquidity(order_book)
            structure_signals["liquidity_score"] = liquidity_score

            if "score" not in structure_signals:
                structure_signals["score"] = 0.5

            return structure_signals

        except Exception as e:
            print(f"市场结构分析失败: {e}")
            return {"score": 0.5}

    def _analyze_liquidity(self, order_book: Dict) -> float:
        """分析流动性"""

        try:
            if not order_book:
                return 0.5

            bids = order_book.get("bids", [])
            asks = order_book.get("asks", [])

            if not bids or not asks:
                return 0.5

            # 计算前5档深度
            bid_depth = sum(qty for _, qty in bids[:5])
            ask_depth = sum(qty for _, qty in asks[:5])
            total_depth = bid_depth + ask_depth

            # 计算价差
            if bids and asks:
                best_bid = bids[0][0]
                best_ask = asks[0][0]
                spread = (best_ask - best_bid) / best_bid

                # 流动性得分: 深度大、价差小 -> 流动性好
                depth_score = min(1.0, total_depth / 100)  # 假设100为高流动性阈值
                spread_score = max(0.0, 1.0 - (spread / 0.01))  # 假设1%为正常价差

                liquidity_score = 0.6 * depth_score + 0.4 * spread_score
                return liquidity_score

            return 0.5

        except Exception as e:
            print(f"流动性分析失败: {e}")
            return 0.5

    def _calculate_data_quality(self, *data_sources) -> float:
        """计算数据质量"""

        quality_scores = []

        for data in data_sources:
            if data:
                # 数据存在性
                existence_score = 1.0

                # 数据完整性
                if isinstance(data, dict):
                    completeness_score = min(1.0, len(data) / 5)  # 假设至少5个字段
                else:
                    completeness_score = 0.8  # 对象类型通常更完整

                # 数据新鲜度（这里简化为存在即新鲜）
                freshness_score = 0.9

                quality_score = (
                    0.4 * existence_score + 0.4 * completeness_score + 0.2 * freshness_score
                )
                quality_scores.append(quality_score)

        if quality_scores:
            return np.mean(quality_scores)
        else:
            return 0.0

    def _calculate_data_consistency(self, *data_sources) -> float:
        """计算数据一致性"""

        # 收集所有信号的得分
        signal_scores = []

        for data in data_sources:
            if isinstance(data, dict) and "score" in data:
                signal_scores.append(data["score"])
            elif hasattr(data, "overall_sentiment"):
                # SocialSentiment对象
                signal_scores.append(data.overall_sentiment)
            elif hasattr(data, "onchain_sentiment"):
                # OnChainMetrics对象
                signal_scores.append(data.onchain_sentiment)

        if len(signal_scores) < 2:
            return 1.0  # 只有一个数据源，一致性为100%

        # 计算标准差，越低表示一致性越高
        std_dev = np.std(signal_scores)

        # 将标准差转换为一致性得分 (0-1)
        consistency = max(0.0, 1.0 - (std_dev * 2))

        return consistency

    def _calculate_technical_score(self, technical_signals: Dict) -> float:
        """计算技术分析得分"""

        if technical_signals and "overall_score" in technical_signals:
            return technical_signals["overall_score"]
        return 0.5

    def _calculate_onchain_score(self, onchain_metrics: Optional[OnChainMetrics]) -> float:
        """计算链上分析得分"""

        if onchain_metrics:
            return onchain_metrics.onchain_sentiment
        return 0.5

    def _calculate_sentiment_score(self, social_sentiment: Optional[SocialSentiment]) -> float:
        """计算情绪分析得分"""

        if social_sentiment:
            return social_sentiment.overall_sentiment
        return 0.5

    def _calculate_risk_score(self, *data_sources) -> float:
        """计算风险得分"""

        risk_factors = []

        for data in data_sources:
            if isinstance(data, dict):
                # 技术信号中的波动性
                if "volatility" in data and "score" in data["volatility"]:
                    vol_score = data["volatility"]["score"]
                    # 波动性高 -> 风险高
                    risk_factors.append(1.0 - vol_score)

            elif hasattr(data, "risk_level"):
                # OnChainMetrics风险等级
                risk_level = data.risk_level
                if risk_level == "high":
                    risk_factors.append(0.8)
                elif risk_level == "medium":
                    risk_factors.append(0.5)
                else:
                    risk_factors.append(0.2)

            elif hasattr(data, "market_impact"):
                # SocialSentiment市场影响
                impact = abs(data.market_impact)
                risk_factors.append(min(1.0, impact * 2))

        if risk_factors:
            return np.mean(risk_factors)
        else:
            return 0.5

    def _calculate_volatility_score(self, market_data: Dict) -> float:
        """计算波动性得分"""

        try:
            indicators = market_data.get("indicators", {})
            if "atr" in indicators and "close" in indicators:
                atr = indicators["atr"]
                close = indicators["close"]

                if close > 0:
                    atr_percent = atr / close

                    # 波动性得分: 波动性低 -> 得分高
                    if atr_percent > 0.05:
                        return 0.3
                    elif atr_percent < 0.01:
                        return 0.7
                    else:
                        return 0.5

            return 0.5

        except Exception as e:
            print(f"波动性得分计算失败: {e}")
            return 0.5

    async def _adjust_weights_based_on_performance(self):
        """根据历史表现调整权重"""

        if len(self.performance_history) < 10:
            return  # 数据不足，不调整

        # 计算各数据源的历史表现
        # 这里简化处理，实际应该使用更复杂的算法
        recent_performance = self.performance_history[-10:]

        # 暂时使用固定权重
        # 未来可以实现基于强化学习的权重调整

    def _calculate_overall_confidence(self, *scores) -> float:
        """计算综合置信度"""

        if not scores:
            return 0.0

        # 使用几何平均，对低分更敏感
        valid_scores = [s for s in scores if s > 0]
        if not valid_scores:
            return 0.0

        # 几何平均
        product = np.prod(valid_scores)
        geometric_mean = product ** (1 / len(valid_scores))

        return geometric_mean

    async def _generate_fused_signal(self, symbol: str, *data_sources) -> Optional[TradingSignal]:
        """生成融合信号"""

        try:
            # 收集各数据源的信号
            signals = []
            confidences = []
            reasonings = []

            for data in data_sources:
                if isinstance(data, dict) and "signal" in data:
                    # 技术信号
                    tech_signal = data["signal"]
                    signals.append(self._map_signal_to_value(tech_signal))
                    confidences.append(data.get("overall_score", 0.5))
                    reasonings.append(f"技术分析: {tech_signal}")

                elif hasattr(data, "onchain_sentiment"):
                    # 链上信号
                    onchain_sentiment = data.onchain_sentiment
                    onchain_signal = self._sentiment_to_signal(onchain_sentiment)
                    signals.append(self._map_signal_to_value(onchain_signal))
                    confidences.append(data.onchain_sentiment)
                    reasonings.append(f"链上分析: {data.onchain_sentiment:.2f}")

                elif hasattr(data, "overall_sentiment"):
                    # 情绪信号
                    sentiment = data.overall_sentiment
                    sentiment_signal = self._sentiment_to_signal(sentiment)
                    signals.append(self._map_signal_to_value(sentiment_signal))
                    confidences.append(sentiment)
                    reasonings.append(f"情绪分析: {sentiment:.2f}")

            if not signals:
                return None

            # 加权平均信号值
            weighted_signals = []
            total_weight = 0

            for i, signal_value in enumerate(signals):
                weight = confidences[i] * self._get_data_source_weight(i)
                weighted_signals.append(signal_value * weight)
                total_weight += weight

            if total_weight == 0:
                return None

            avg_signal_value = sum(weighted_signals) / total_weight

            # 映射回交易信号
            fused_decision = self._value_to_decision(avg_signal_value)

            # 计算平均置信度
            avg_confidence = np.mean(confidences) if confidences else 0.5

            # 构建融合信号
            fused_signal = TradingSignal(
                symbol=symbol,
                decision=fused_decision,
                confidence=avg_confidence,
                reasoning=" | ".join(reasonings),
                target_price=None,  # 需要额外计算
                stop_loss=None,
                take_profit=None,
                suggested_position_size=None,
                time_horizon="short_term",
            )

            return fused_signal

        except Exception as e:
            print(f"生成融合信号失败: {e}")
            return None

    def _map_signal_to_value(self, signal_str: str) -> float:
        """将信号字符串映射为数值"""

        signal_map = {
            "STRONG_BUY": 2.0,
            "BUY": 1.0,
            "WEAK_BUY": 0.5,
            "NEUTRAL": 0.0,
            "WEAK_SELL": -0.5,
            "SELL": -1.0,
            "STRONG_SELL": -2.0,
        }

        return signal_map.get(signal_str.upper(), 0.0)

    def _sentiment_to_signal(self, sentiment: float) -> str:
        """将情绪得分转换为信号"""

        if sentiment > 0.7:
            return "STRONG_BUY"
        elif sentiment > 0.6:
            return "BUY"
        elif sentiment > 0.55:
            return "WEAK_BUY"
        elif sentiment > 0.45:
            return "NEUTRAL"
        elif sentiment > 0.4:
            return "WEAK_SELL"
        elif sentiment > 0.3:
            return "SELL"
        else:
            return "STRONG_SELL"

    def _get_data_source_weight(self, source_index: int) -> float:
        """获取数据源权重"""

        weights = [
            self.weights.technical_weight,  # 技术分析
            self.weights.onchain_weight,  # 链上分析
            self.weights.sentiment_weight,  # 情绪分析
            self.weights.market_weight,  # 市场结构
        ]

        if 0 <= source_index < len(weights):
            return weights[source_index]
        else:
            return 0.1  # 默认权重

    def _value_to_decision(self, signal_value: float) -> Decision:
        """将信号值映射为决策枚举"""

        if signal_value > 1.5:
            return Decision.STRONG_BUY
        elif signal_value > 0.5:
            return Decision.BUY
        elif signal_value > 0.1:
            return Decision.HOLD  # 微弱看涨
        elif signal_value < -1.5:
            return Decision.STRONG_SELL
        elif signal_value < -0.5:
            return Decision.SELL
        elif signal_value < -0.1:
            return Decision.HOLD  # 微弱看跌
        else:
            return Decision.HOLD

    def _calculate_signal_strength(self, signal: TradingSignal) -> float:
        """计算信号强度"""

        # 信号强度 = 置信度 * 决策强度
        decision_strength = {
            Decision.STRONG_BUY: 1.0,
            Decision.BUY: 0.7,
            Decision.HOLD: 0.3,
            Decision.SELL: 0.7,
            Decision.STRONG_SELL: 1.0,
        }

        strength = decision_strength.get(signal.decision, 0.3)
        return signal.confidence * strength

    def _calculate_signal_consistency(self, signal: TradingSignal, symbol: str) -> float:
        """计算信号一致性"""

        # 这里应该与历史信号比较
        # 暂时返回固定值
        return 0.8

    def _record_performance(self, fused_data: FusedData):
        """记录性能数据"""

        performance_record = {
            "timestamp": fused_data.timestamp,
            "symbol": fused_data.symbol,
            "data_quality": fused_data.data_quality_score,
            "data_consistency": fused_data.data_consistency_score,
            "overall_confidence": fused_data.overall_confidence,
            "technical_score": fused_data.technical_score,
            "onchain_score": fused_data.onchain_score,
            "sentiment_score": fused_data.sentiment_score,
            "risk_score": fused_data.risk_score,
            "signal": fused_data.fused_signal.decision.value if fused_data.fused_signal else None,
            "signal_confidence": (
                fused_data.fused_signal.confidence if fused_data.fused_signal else None
            ),
        }

        self.performance_history.append(performance_record)

        # 保持历史记录长度
        if len(self.performance_history) > 1000:
            self.performance_history = self.performance_history[-1000:]

    def generate_fusion_report(self, fused_data: FusedData) -> Dict:
        """生成融合数据报告"""

        if not fused_data:
            return {"error": "无融合数据"}

        report = {
            "timestamp": fused_data.timestamp.isoformat(),
            "symbol": fused_data.symbol,
            "data_quality": {
                "quality_score": fused_data.data_quality_score,
                "consistency_score": fused_data.data_consistency_score,
                "overall_confidence": fused_data.overall_confidence,
            },
            "dimension_scores": {
                "technical": fused_data.technical_score,
                "onchain": fused_data.onchain_score,
                "sentiment": fused_data.sentiment_score,
            },
            "risk_metrics": {
                "risk_score": fused_data.risk_score,
                "volatility_score": fused_data.volatility_score,
            },
            "fused_signal": {
                "decision": (
                    fused_data.fused_signal.decision.value if fused_data.fused_signal else None
                ),
                "confidence": (
                    fused_data.fused_signal.confidence if fused_data.fused_signal else None
                ),
                "reasoning": fused_data.fused_signal.reasoning if fused_data.fused_signal else None,
                "strength": fused_data.signal_strength,
                "consistency": fused_data.signal_consistency,
            },
            "recommendation": self._generate_fusion_recommendation(fused_data),
        }

        return report

    def _generate_fusion_recommendation(self, fused_data: FusedData) -> str:
        """生成基于融合数据的交易建议"""

        if not fused_data.fused_signal:
            return "HOLD - 无有效信号"

        signal = fused_data.fused_signal
        confidence = signal.confidence

        recommendations = {
            Decision.STRONG_BUY: "STRONG_BUY - 强烈买入信号",
            Decision.BUY: "BUY - 买入信号",
            Decision.HOLD: "HOLD - 持有观望",
            Decision.SELL: "SELL - 卖出信号",
            Decision.STRONG_SELL: "STRONG_SELL - 强烈卖出信号",
        }

        base_recommendation = recommendations.get(signal.decision, "HOLD - 未知信号")

        # 添加置信度说明
        if confidence > 0.8:
            confidence_note = " (高置信度)"
        elif confidence > 0.6:
            confidence_note = " (中等置信度)"
        else:
            confidence_note = " (低置信度，谨慎操作)"

        # 添加风险说明
        if fused_data.risk_score > 0.7:
            risk_note = " [高风险警告]"
        elif fused_data.risk_score > 0.6:
            risk_note = " [风险较高]"
        else:
            risk_note = ""

        return base_recommendation + confidence_note + risk_note


# 单例实例
_fusion_engine = None


def get_fusion_engine(config_manager=None):
    """获取数据融合引擎单例"""
    global _fusion_engine
    if _fusion_engine is None:
        from ..core.config_manager import get_config_manager

        config = config_manager or get_config_manager()
        _fusion_engine = DataFusionEngine(config)
    return _fusion_engine
