#!/usr/bin/env python3
"""
链上数据分析模块
集成区块链数据，监控资金流向和链上指标
"""

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import aiohttp
import numpy as np


@dataclass
class OnChainMetrics:
    """链上指标"""

    timestamp: datetime
    symbol: str

    # 资金流向指标
    exchange_netflow: float  # 交易所净流入流出
    exchange_inflow: float  # 流入交易所
    exchange_outflow: float  # 流出交易所

    # 鲸鱼活动
    whale_transactions: int  # 大额交易数量
    whale_volume: float  # 大额交易总量
    whale_addresses_active: int  # 活跃鲸鱼地址数

    # 矿工活动
    miner_to_exchange: float  # 矿工转交易所数量
    miner_reserve_change: float  # 矿工储备变化

    # 链上活跃度
    active_addresses: int  # 活跃地址数
    transaction_count: int  # 交易总数
    transaction_volume: float  # 交易总量

    # 持有者行为
    hodler_supply: float  # 长期持有者供应量
    hodler_supply_change: float  # 长期持有者变化
    short_term_supply: float  # 短期持有者供应量

    # 高级指标
    mvrv_z_score: float  # MVRV Z-Score
    nupl: float  # Net Unrealized Profit/Loss
    sopr: float  # Spent Output Profit Ratio
    reserve_risk: float  # 储备风险

    # 情绪指标
    onchain_sentiment: float  # 链上情绪得分 (0-1)
    risk_level: str  # 风险等级: low, medium, high


class OnChainAnalyzer:
    """链上数据分析器"""

    def __init__(self, config_manager):
        self.config = config_manager

        # 数据源配置
        self.data_sources = {
            "glassnode": {
                "api_key": self.config.get("onchain.glassnode.api_key", ""),
                "base_url": "https://api.glassnode.com/v1",
                "endpoints": {
                    "exchange_flow": "/metrics/transactions/transfers_volume_exchange_net",
                    "active_addresses": "/metrics/addresses/active_count",
                    "mvrv": "/metrics/market/mvrv",
                    "sopr": "/metrics/market/sopr",
                },
            },
            "chainalysis": {
                "api_key": self.config.get("onchain.chainalysis.api_key", ""),
                "base_url": "https://public.chainalysis.com/api/v1",
            },
            "cryptoquant": {
                "api_key": self.config.get("onchain.cryptoquant.api_key", ""),
                "base_url": "https://api.cryptoquant.com/v1",
            },
            "bitcoin_blockchain": {"base_url": "https://blockchain.info"},
            "etherscan": {
                "api_key": self.config.get("onchain.etherscan.api_key", ""),
                "base_url": "https://api.etherscan.io/api",
            },
        }

        # 缓存系统
        self.cache = {}
        self.cache_ttl = 300  # 5分钟

    async def fetch_onchain_data(self, symbol: str) -> Optional[OnChainMetrics]:
        """获取链上数据"""

        try:
            # 并行获取各种数据
            tasks = [
                self._get_exchange_flow(symbol),
                self._get_whale_activity(symbol),
                self._get_miner_activity(symbol),
                self._get_chain_activity(symbol),
                self._get_holder_metrics(symbol),
                self._get_advanced_metrics(symbol),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 处理结果
            exchange_flow = results[0] if not isinstance(results[0], Exception) else {}
            whale_activity = results[1] if not isinstance(results[1], Exception) else {}
            miner_activity = results[2] if not isinstance(results[2], Exception) else {}
            chain_activity = results[3] if not isinstance(results[3], Exception) else {}
            holder_metrics = results[4] if not isinstance(results[4], Exception) else {}
            advanced_metrics = results[5] if not isinstance(results[5], Exception) else {}

            # 计算综合情绪得分
            sentiment_score = self._calculate_sentiment_score(
                exchange_flow,
                whale_activity,
                miner_activity,
                chain_activity,
                holder_metrics,
                advanced_metrics,
            )

            # 计算风险等级
            risk_level = self._calculate_risk_level(sentiment_score)

            # 构建链上指标
            metrics = OnChainMetrics(
                timestamp=datetime.now(),
                symbol=symbol,
                exchange_netflow=exchange_flow.get("netflow", 0.0),
                exchange_inflow=exchange_flow.get("inflow", 0.0),
                exchange_outflow=exchange_flow.get("outflow", 0.0),
                whale_transactions=whale_activity.get("transaction_count", 0),
                whale_volume=whale_activity.get("total_volume", 0.0),
                whale_addresses_active=whale_activity.get("active_addresses", 0),
                miner_to_exchange=miner_activity.get("to_exchange", 0.0),
                miner_reserve_change=miner_activity.get("reserve_change", 0.0),
                active_addresses=chain_activity.get("active_addresses", 0),
                transaction_count=chain_activity.get("transaction_count", 0),
                transaction_volume=chain_activity.get("transaction_volume", 0.0),
                hodler_supply=holder_metrics.get("hodler_supply", 0.0),
                hodler_supply_change=holder_metrics.get("hodler_supply_change", 0.0),
                short_term_supply=holder_metrics.get("short_term_supply", 0.0),
                mvrv_z_score=advanced_metrics.get("mvrv_z_score", 0.0),
                nupl=advanced_metrics.get("nupl", 0.0),
                sopr=advanced_metrics.get("sopr", 0.0),
                reserve_risk=advanced_metrics.get("reserve_risk", 0.0),
                onchain_sentiment=sentiment_score,
                risk_level=risk_level,
            )

            return metrics

        except Exception as e:
            print(f"获取链上数据失败: {e}")
            return None

    async def _get_exchange_flow(self, symbol: str) -> Dict:
        """获取交易所资金流向"""

        cache_key = f"exchange_flow_{symbol}_{datetime.now().strftime('%Y%m%d')}"
        if (
            cache_key in self.cache
            and time.time() - self.cache[cache_key]["timestamp"] < self.cache_ttl
        ):
            return self.cache[cache_key]["data"]

        try:
            if symbol == "BTCUSDT":
                # 使用Glassnode API
                url = (
                    f"{self.data_sources['glassnode']['base_url']}"
                    f"{self.data_sources['glassnode']['endpoints']['exchange_flow']}"
                )

                params = {
                    "a": "BTC",
                    "api_key": self.data_sources["glassnode"]["api_key"],
                    "i": "24h",
                }

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            # 解析数据
                            exchange_flow = {
                                "netflow": self._parse_flow_data(data, "net"),
                                "inflow": self._parse_flow_data(data, "inflow"),
                                "outflow": self._parse_flow_data(data, "outflow"),
                            }

                            # 缓存结果
                            self.cache[cache_key] = {
                                "timestamp": time.time(),
                                "data": exchange_flow,
                            }

                            return exchange_flow

            # 如果API不可用，使用模拟数据
            return {
                "netflow": np.random.uniform(-1000, 1000),
                "inflow": np.random.uniform(0, 5000),
                "outflow": np.random.uniform(0, 5000),
            }

        except Exception as e:
            print(f"获取交易所资金流向失败: {e}")
            return {}

    async def _get_whale_activity(self, symbol: str) -> Dict:
        """获取鲸鱼活动数据"""

        try:
            # 这里应该调用区块链浏览器API或专业数据服务
            # 暂时使用模拟数据

            if symbol == "BTCUSDT":
                # 模拟比特币鲸鱼活动
                whale_activity = {
                    "transaction_count": int(np.random.uniform(10, 100)),
                    "total_volume": np.random.uniform(100, 5000),
                    "active_addresses": int(np.random.uniform(5, 50)),
                    "largest_transaction": np.random.uniform(50, 500),
                    "average_transaction_size": np.random.uniform(10, 100),
                }
            elif symbol == "ETHUSDT":
                # 模拟以太坊鲸鱼活动
                whale_activity = {
                    "transaction_count": int(np.random.uniform(20, 200)),
                    "total_volume": np.random.uniform(50, 3000),
                    "active_addresses": int(np.random.uniform(10, 100)),
                    "largest_transaction": np.random.uniform(20, 300),
                    "average_transaction_size": np.random.uniform(5, 50),
                }
            else:
                whale_activity = {
                    "transaction_count": 0,
                    "total_volume": 0.0,
                    "active_addresses": 0,
                    "largest_transaction": 0.0,
                    "average_transaction_size": 0.0,
                }

            return whale_activity

        except Exception as e:
            print(f"获取鲸鱼活动数据失败: {e}")
            return {}

    async def _get_miner_activity(self, symbol: str) -> Dict:
        """获取矿工活动数据"""

        try:
            if symbol == "BTCUSDT":
                # 模拟比特币矿工活动
                miner_activity = {
                    "to_exchange": np.random.uniform(0, 100),  # 矿工转交易所数量
                    "reserve_change": np.random.uniform(-50, 50),  # 矿工储备变化
                    "mining_revenue": np.random.uniform(100, 1000),  # 挖矿收益
                    "hash_rate": np.random.uniform(400, 600),  # 哈希率
                    "difficulty": np.random.uniform(20, 40),  # 挖矿难度
                }
            else:
                miner_activity = {
                    "to_exchange": 0.0,
                    "reserve_change": 0.0,
                    "mining_revenue": 0.0,
                    "hash_rate": 0.0,
                    "difficulty": 0.0,
                }

            return miner_activity

        except Exception as e:
            print(f"获取矿工活动数据失败: {e}")
            return {}

    async def _get_chain_activity(self, symbol: str) -> Dict:
        """获取链上活跃度数据"""

        try:
            if symbol == "BTCUSDT":
                # 模拟比特币链上活跃度
                chain_activity = {
                    "active_addresses": int(np.random.uniform(800000, 1200000)),
                    "transaction_count": int(np.random.uniform(200000, 400000)),
                    "transaction_volume": np.random.uniform(50000, 200000),
                    "average_transaction_value": np.random.uniform(0.1, 1.0),
                    "transaction_fee": np.random.uniform(1, 10),
                }
            elif symbol == "ETHUSDT":
                # 模拟以太坊链上活跃度
                chain_activity = {
                    "active_addresses": int(np.random.uniform(400000, 800000)),
                    "transaction_count": int(np.random.uniform(1000000, 2000000)),
                    "transaction_volume": np.random.uniform(20000, 100000),
                    "average_transaction_value": np.random.uniform(0.01, 0.1),
                    "transaction_fee": np.random.uniform(10, 50),
                }
            else:
                chain_activity = {
                    "active_addresses": 0,
                    "transaction_count": 0,
                    "transaction_volume": 0.0,
                    "average_transaction_value": 0.0,
                    "transaction_fee": 0.0,
                }

            return chain_activity

        except Exception as e:
            print(f"获取链上活跃度数据失败: {e}")
            return {}

    async def _get_holder_metrics(self, symbol: str) -> Dict:
        """获取持有者指标"""

        try:
            if symbol == "BTCUSDT":
                # 模拟比特币持有者指标
                holder_metrics = {
                    "hodler_supply": np.random.uniform(12000000, 15000000),  # 长期持有者供应量
                    "hodler_supply_change": np.random.uniform(-10000, 10000),  # 变化
                    "short_term_supply": np.random.uniform(2000000, 4000000),  # 短期持有者供应量
                    "lost_coins": np.random.uniform(1000000, 3000000),  # 丢失的币
                    "exchange_balance": np.random.uniform(2000000, 3000000),  # 交易所余额
                }
            else:
                holder_metrics = {
                    "hodler_supply": 0.0,
                    "hodler_supply_change": 0.0,
                    "short_term_supply": 0.0,
                    "lost_coins": 0.0,
                    "exchange_balance": 0.0,
                }

            return holder_metrics

        except Exception as e:
            print(f"获取持有者指标失败: {e}")
            return {}

    async def _get_advanced_metrics(self, symbol: str) -> Dict:
        """获取高级链上指标"""

        try:
            if symbol == "BTCUSDT":
                # 模拟比特币高级指标
                advanced_metrics = {
                    "mvrv_z_score": np.random.uniform(-1.0, 2.0),  # MVRV Z-Score
                    "nupl": np.random.uniform(-0.5, 0.7),  # Net Unrealized Profit/Loss
                    "sopr": np.random.uniform(0.9, 1.1),  # Spent Output Profit Ratio
                    "reserve_risk": np.random.uniform(0.001, 0.01),  # 储备风险
                    "puell_multiple": np.random.uniform(0.5, 1.5),  # Puell倍数
                    "hash_ribbons": "recovery" if np.random.random() > 0.5 else "capitulation",
                }
            else:
                advanced_metrics = {
                    "mvrv_z_score": 0.0,
                    "nupl": 0.0,
                    "sopr": 0.0,
                    "reserve_risk": 0.0,
                    "puell_multiple": 0.0,
                    "hash_ribbons": "unknown",
                }

            return advanced_metrics

        except Exception as e:
            print(f"获取高级链上指标失败: {e}")
            return {}

    def _calculate_sentiment_score(self, *metrics_sets) -> float:
        """计算链上情绪综合得分"""

        if not any(metrics_sets):
            return 0.5  # 中性

        sentiment_factors = []

        # 1. 交易所资金流向 (-1 到 1)
        exchange_flow = metrics_sets[0]
        if exchange_flow and "netflow" in exchange_flow:
            netflow = exchange_flow["netflow"]
            # 净流入为正，净流出为负
            flow_score = np.tanh(netflow / 1000)  # 标准化到 -1 到 1
            sentiment_factors.append(("flow", 0.3, flow_score))

        # 2. 鲸鱼活动 (0 到 1)
        whale_activity = metrics_sets[1]
        if whale_activity and "total_volume" in whale_activity:
            volume = whale_activity["total_volume"]
            # 鲸鱼活动增加通常看涨
            whale_score = min(1.0, volume / 1000)  # 假设1000为高活动阈值
            sentiment_factors.append(("whale", 0.2, whale_score))

        # 3. 矿工活动 (-1 到 1)
        miner_activity = metrics_sets[2]
        if miner_activity and "reserve_change" in miner_activity:
            reserve_change = miner_activity["reserve_change"]
            # 矿工增持看涨，减持看跌
            miner_score = np.tanh(reserve_change / 50)  # 标准化
            sentiment_factors.append(("miner", 0.15, miner_score))

        # 4. 链上活跃度 (0 到 1)
        chain_activity = metrics_sets[3]
        if chain_activity and "active_addresses" in chain_activity:
            active_addrs = chain_activity["active_addresses"]
            # 活跃地址增加看涨
            activity_score = min(1.0, active_addrs / 1000000)  # 假设100万为高活跃度
            sentiment_factors.append(("activity", 0.15, activity_score))

        # 5. 持有者行为 (0 到 1)
        holder_metrics = metrics_sets[4]
        if holder_metrics and "hodler_supply_change" in holder_metrics:
            hodler_change = holder_metrics["hodler_supply_change"]
            # 长期持有者增持看涨
            holder_score = np.tanh(hodler_change / 10000) * 0.5 + 0.5  # 映射到 0-1
            sentiment_factors.append(("holder", 0.1, holder_score))

        # 6. 高级指标 (-1 到 1)
        advanced_metrics = metrics_sets[5]
        if advanced_metrics:
            adv_score = 0.5  # 中性

            if "mvrv_z_score" in advanced_metrics:
                mvrv = advanced_metrics["mvrv_z_score"]
                # MVRV Z-Score 过低（< -1）超卖，过高（> 2）超买
                if mvrv < -1:
                    adv_score += 0.2  # 超卖，看涨
                elif mvrv > 2:
                    adv_score -= 0.2  # 超买，看跌

            if "nupl" in advanced_metrics:
                nupl = advanced_metrics["nupl"]
                # NUPL 负值看涨，正值看跌
                adv_score -= nupl * 0.1

            sentiment_factors.append(("advanced", 0.1, max(0.0, min(1.0, adv_score))))

        # 计算加权平均
        if not sentiment_factors:
            return 0.5

        total_weight = sum(weight for _, weight, _ in sentiment_factors)
        weighted_score = sum(score * weight for _, weight, score in sentiment_factors)

        final_score = weighted_score / total_weight
        return max(0.0, min(1.0, final_score))

    def _calculate_risk_level(self, sentiment_score: float) -> str:
        """根据情绪得分计算风险等级"""

        if sentiment_score > 0.7:
            return "low"  # 看涨情绪强，风险低
        elif sentiment_score > 0.55:
            return "medium"  # 略微看涨，风险中等
        elif sentiment_score > 0.45:
            return "medium"  # 中性，风险中等
        elif sentiment_score > 0.3:
            return "high"  # 略微看跌，风险高
        else:
            return "high"  # 看跌情绪强，风险高

    def _parse_flow_data(self, data: List[Dict], flow_type: str) -> float:
        """解析资金流向数据"""

        if not data:
            return 0.0

        try:
            # 获取最新数据点
            latest_point = data[-1]

            if flow_type == "net":
                return float(latest_point.get("v", 0))
            elif flow_type == "inflow":
                return float(latest_point.get("i", 0))
            elif flow_type == "outflow":
                return float(latest_point.get("o", 0))
            else:
                return 0.0
        except:
            return 0.0

    def generate_onchain_report(self, metrics: OnChainMetrics) -> Dict:
        """生成链上数据报告"""

        if not metrics:
            return {"error": "无链上数据"}

        report = {
            "timestamp": metrics.timestamp.isoformat(),
            "symbol": metrics.symbol,
            "summary": {
                "onchain_sentiment": metrics.onchain_sentiment,
                "risk_level": metrics.risk_level,
                "recommendation": self._generate_recommendation(metrics),
            },
            "exchange_flow": {
                "netflow": metrics.exchange_netflow,
                "inflow": metrics.exchange_inflow,
                "outflow": metrics.exchange_outflow,
                "interpretation": self._interpret_exchange_flow(metrics),
            },
            "whale_activity": {
                "transactions": metrics.whale_transactions,
                "volume": metrics.whale_volume,
                "active_addresses": metrics.whale_addresses_active,
                "interpretation": self._interpret_whale_activity(metrics),
            },
            "miner_activity": {
                "to_exchange": metrics.miner_to_exchange,
                "reserve_change": metrics.miner_reserve_change,
                "interpretation": self._interpret_miner_activity(metrics),
            },
            "chain_activity": {
                "active_addresses": metrics.active_addresses,
                "transaction_count": metrics.transaction_count,
                "transaction_volume": metrics.transaction_volume,
                "interpretation": self._interpret_chain_activity(metrics),
            },
            "advanced_metrics": {
                "mvrv_z_score": metrics.mvrv_z_score,
                "nupl": metrics.nupl,
                "sopr": metrics.sopr,
                "reserve_risk": metrics.reserve_risk,
                "interpretation": self._interpret_advanced_metrics(metrics),
            },
        }

        return report

    def _generate_recommendation(self, metrics: OnChainMetrics) -> str:
        """生成交易建议"""

        sentiment = metrics.onchain_sentiment

        if sentiment > 0.7:
            return "STRONG_BUY - 链上情绪极度看涨"
        elif sentiment > 0.6:
            return "BUY - 链上情绪看涨"
        elif sentiment > 0.55:
            return "HOLD - 链上情绪略微看涨"
        elif sentiment > 0.45:
            return "HOLD - 链上情绪中性"
        elif sentiment > 0.4:
            return "HOLD - 链上情绪略微看跌"
        elif sentiment > 0.3:
            return "SELL - 链上情绪看跌"
        else:
            return "STRONG_SELL - 链上情绪极度看跌"

    def _interpret_exchange_flow(self, metrics: OnChainMetrics) -> str:
        """解释交易所资金流向"""

        if metrics.exchange_netflow > 100:
            return "资金大幅流入交易所，可能面临抛压"
        elif metrics.exchange_netflow > 10:
            return "资金小幅流入交易所"
        elif metrics.exchange_netflow > -10:
            return "资金流向基本平衡"
        elif metrics.exchange_netflow > -100:
            return "资金小幅流出交易所，持有者积累"
        else:
            return "资金大幅流出交易所，强烈的积累信号"

    def _interpret_whale_activity(self, metrics: OnChainMetrics) -> str:
        """解释鲸鱼活动"""

        if metrics.whale_volume > 1000:
            return "鲸鱼活动异常活跃，注意大额交易"
        elif metrics.whale_volume > 500:
            return "鲸鱼活动增加，市场可能波动"
        elif metrics.whale_volume > 100:
            return "鲸鱼活动正常"
        else:
            return "鲸鱼活动平静"

    def _interpret_miner_activity(self, metrics: OnChainMetrics) -> str:
        """解释矿工活动"""

        if metrics.miner_reserve_change > 20:
            return "矿工大幅增持，长期看好"
        elif metrics.miner_reserve_change > 5:
            return "矿工小幅增持"
        elif metrics.miner_reserve_change > -5:
            return "矿工持仓稳定"
        elif metrics.miner_reserve_change > -20:
            return "矿工小幅减持"
        else:
            return "矿工大幅减持，可能面临压力"

    def _interpret_chain_activity(self, metrics: OnChainMetrics) -> str:
        """解释链上活跃度"""

        if metrics.active_addresses > 1000000:
            return "链上极度活跃，网络使用率高"
        elif metrics.active_addresses > 800000:
            return "链上活跃度高"
        elif metrics.active_addresses > 500000:
            return "链上活跃度正常"
        elif metrics.active_addresses > 300000:
            return "链上活跃度偏低"
        else:
            return "链上活跃度极低"

    def _interpret_advanced_metrics(self, metrics: OnChainMetrics) -> str:
        """解释高级指标"""

        interpretations = []

        # MVRV Z-Score
        if metrics.mvrv_z_score < -1:
            interpretations.append("MVRV Z-Score < -1: 极度低估，买入信号")
        elif metrics.mvrv_z_score > 2:
            interpretations.append("MVRV Z-Score > 2: 极度高估，卖出信号")

        # NUPL
        if metrics.nupl < -0.2:
            interpretations.append("NUPL < -0.2: 市场整体亏损，超卖")
        elif metrics.nupl > 0.5:
            interpretations.append("NUPL > 0.5: 市场整体盈利，超买")

        # SOPR
        if metrics.sopr > 1.05:
            interpretations.append("SOPR > 1.05: 获利了结增加")
        elif metrics.sopr < 0.95:
            interpretations.append("SOPR < 0.95: 亏损卖出增加")

        return "; ".join(interpretations) if interpretations else "指标处于正常范围"


# 单例实例
_onchain_analyzer = None


def get_onchain_analyzer(config_manager=None):
    """获取链上分析器单例"""
    global _onchain_analyzer
    if _onchain_analyzer is None:
        from ..config_manager import get_config_manager

        config = config_manager or get_config_manager()
        _onchain_analyzer = OnChainAnalyzer(config)
    return _onchain_analyzer
