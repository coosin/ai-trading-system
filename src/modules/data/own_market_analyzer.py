"""
自主市场分析器 - 完全属于自己的市场数据分析系统
功能类似AiCoin，但完全自主开发
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import statistics

logger = logging.getLogger(__name__)


@dataclass
class MarketSentiment:
    """市场情绪"""
    sentiment: str
    fear_greed_index: float
    strength: float
    sources: List[str]


@dataclass
class LongShortData:
    """多空比数据"""
    long_ratio: float
    short_ratio: float
    long_short_ratio: float
    change_1d: float
    change_1w: float


@dataclass
class LiquidationData:
    """爆仓数据"""
    total_1h: float
    total_24h: float
    long_liq_1h: float
    short_liq_1h: float
    max_liq_price: float


@dataclass
class BigOrderData:
    """主力大单数据"""
    orders: List[Dict]
    total_volume: float
    avg_size: float
    buy_ratio: float


@dataclass
class ChangeSignal:
    """异动信号"""
    signal_type: str
    symbol: str
    price: float
    change_pct: float
    volume: float
    timestamp: datetime
    severity: str


class OwnMarketAnalyzer:
    """
    自主市场分析器
    完全属于自己的市场数据分析系统
    """
    
    def __init__(self, exchange):
        self.exchange = exchange
        self._cache = {}
        self._cache_ttl = 60
        
        self.watchlist = [
            "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
            "XRP/USDT", "ADA/USDT", "DOGE/USDT", "AVAX/USDT"
        ]
        
        self._price_history: Dict[str, List[float]] = {}
        self._volume_history: Dict[str, List[float]] = {}
        self._order_book_history: Dict[str, Dict] = {}
        self._change_signals: List[ChangeSignal] = []
        
    async def analyze_symbol(self, symbol: str) -> Dict[str, Any]:
        """分析单个交易对"""
        result = {}
        
        try:
            sentiment_task = self._analyze_sentiment(symbol)
            ls_task = self._calculate_long_short_ratio(symbol)
            liq_task = self._analyze_liquidation_risk(symbol)
            big_order_task = self._detect_big_orders(symbol)
            change_task = self._detect_change_signals(symbol)
            
            sentiment, ls_ratio, liq_data, big_orders, changes = await asyncio.gather(
                sentiment_task, ls_task, liq_task, big_order_task, change_task
            )
            
            if sentiment:
                result["sentiment"] = sentiment
            if ls_ratio:
                result["long_short_ratio"] = ls_ratio
            if liq_data:
                result["liquidation"] = liq_data
            if big_orders:
                result["big_orders"] = big_orders
            if changes:
                result["change_signals"] = changes
                
            result["analysis_time"] = datetime.now().isoformat()
            result["symbol"] = symbol
            
            logger.info(f"📊 自主市场分析完成: {symbol}, 情绪: {sentiment.get('sentiment', 'neutral') if sentiment else 'neutral'}")
            
        except Exception as e:
            logger.error(f"分析{symbol}失败: {e}")
            
        return result
    
    async def _analyze_sentiment(self, symbol: str) -> Optional[Dict]:
        """分析市场情绪"""
        try:
            okx_symbol = symbol.replace('/', '-') + '-SWAP'
            
            klines_1h = await self.exchange.get_klines(okx_symbol, '1H', limit=24)
            klines_4h = await self.exchange.get_klines(okx_symbol, '4H', limit=24)
            
            if not klines_1h:
                klines_1h = await self.exchange.get_klines(symbol.replace('/', '-'), '1H', limit=24)
            if not klines_4h:
                klines_4h = await self.exchange.get_klines(symbol.replace('/', '-'), '4H', limit=24)
            
            if not klines_1h:
                return None
            
            closes_1h = [k.get('close', 0) for k in klines_1h]
            closes_4h = [k.get('close', 0) for k in klines_4h] if klines_4h else closes_1h
            
            momentum_1h = (closes_1h[-1] - closes_1h[-5]) / closes_1h[-5] if len(closes_1h) >= 5 and closes_1h[-5] > 0 else 0
            momentum_4h = (closes_4h[-1] - closes_4h[-6]) / closes_4h[-6] if len(closes_4h) >= 6 and closes_4h[-6] > 0 else 0
            
            volumes = [k.get('volume', 0) for k in klines_1h]
            avg_volume = statistics.mean(volumes[-10:]) if len(volumes) >= 10 else 1
            volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1
            
            returns = [(closes_1h[i] - closes_1h[i-1]) / closes_1h[i-1] for i in range(1, len(closes_1h)) if closes_1h[i-1] > 0]
            volatility = statistics.stdev(returns) if len(returns) > 1 else 0
            
            ma5 = sum(closes_1h[-5:]) / 5
            ma20 = sum(closes_1h[-20:]) / 20 if len(closes_1h) >= 20 else ma5
            trend = "bullish" if ma5 > ma20 else "bearish" if ma5 < ma20 else "neutral"
            
            fear_greed = 50
            
            if momentum_1h > 0.03:
                fear_greed += 15
            elif momentum_1h < -0.03:
                fear_greed -= 15
            
            if volume_ratio > 1.5:
                fear_greed += 10
            elif volume_ratio < 0.5:
                fear_greed -= 10
            
            if volatility > 0.03:
                fear_greed -= 5
                
            fear_greed = max(0, min(100, fear_greed))
            
            if fear_greed > 60:
                sentiment = "bullish"
            elif fear_greed < 40:
                sentiment = "bearish"
            else:
                sentiment = "neutral"
            
            strength = abs(fear_greed - 50) / 50
            
            return {
                "sentiment": sentiment,
                "fear_greed_index": fear_greed,
                "strength": strength,
                "momentum_1h": momentum_1h,
                "momentum_4h": momentum_4h,
                "volume_ratio": volume_ratio,
                "volatility": volatility,
                "trend": trend,
                "sources": ["price_momentum", "volume", "volatility"]
            }
            
        except Exception as e:
            logger.debug(f"分析{symbol}情绪失败: {e}")
            return None
    
    async def _calculate_long_short_ratio(self, symbol: str) -> Optional[Dict]:
        """计算多空比 - 优先使用交易所API"""
        try:
            okx_symbol = symbol.replace('/', '-') + '-SWAP'
            
            if hasattr(self.exchange, 'get_long_short_ratio'):
                ls_data = await self.exchange.get_long_short_ratio(symbol)
                if ls_data:
                    long_ratio = ls_data.get('long', 0.5)
                    short_ratio = ls_data.get('short', 0.5)
                    return {
                        "long_ratio": long_ratio,
                        "short_ratio": short_ratio,
                        "long_short_ratio": long_ratio / short_ratio if short_ratio > 0 else 1,
                        "source": "exchange_api",
                        "change_1d": 0,
                        "change_1w": 0
                    }
            
            order_book = await self.exchange.get_order_book(okx_symbol, depth=20)
            
            if not order_book:
                order_book = await self.exchange.get_order_book(symbol.replace('/', '-'), depth=20)
            
            if not order_book:
                return None
            
            bids = order_book.bids if hasattr(order_book, 'bids') else order_book.get('bids', [])
            asks = order_book.asks if hasattr(order_book, 'asks') else order_book.get('asks', [])
            
            if not bids or not asks:
                return None
            
            bid_volume = sum(float(b[1]) if len(b) > 1 else 0 for b in bids)
            ask_volume = sum(float(a[1]) if len(a) > 1 else 0 for a in asks)
            
            total = bid_volume + ask_volume
            if total == 0:
                return None
            
            long_ratio = bid_volume / total
            short_ratio = ask_volume / total
            ls_ratio = long_ratio / short_ratio if short_ratio > 0 else 1
            
            return {
                "long_ratio": long_ratio,
                "short_ratio": short_ratio,
                "long_short_ratio": ls_ratio,
                "bid_volume": bid_volume,
                "ask_volume": ask_volume,
                "source": "order_book",
                "change_1d": 0,
                "change_1w": 0
            }
            
        except Exception as e:
            logger.debug(f"计算{symbol}多空比失败: {e}")
            return None
    
    async def _analyze_liquidation_risk(self, symbol: str) -> Optional[Dict]:
        """分析爆仓风险"""
        try:
            positions = await self.exchange.get_positions()
            
            okx_symbol = symbol.replace('/', '-') + '-SWAP'
            symbol_pos = None
            for p in positions:
                pos_symbol = p.get('instId', '') or p.get('symbol', '')
                if okx_symbol in pos_symbol or symbol.replace('/', '-') in pos_symbol:
                    symbol_pos = p
                    break
            
            if not symbol_pos:
                return None
            
            size = float(symbol_pos.get('pos', 0) or symbol_pos.get('size', 0) or 0)
            if size == 0:
                return None
            
            ticker = await self.exchange.get_ticker(okx_symbol)
            if not ticker:
                ticker = await self.exchange.get_ticker(symbol.replace('/', '-'))
            current_price = float(ticker.get('last', 0) or ticker.get('close', 0) or 0)
            
            entry_price = float(symbol_pos.get('avgPx', 0) or symbol_pos.get('entry_price', 0) or 0)
            leverage = float(symbol_pos.get('lever', 1) or symbol_pos.get('leverage', 1) or 1)
            
            liq_price = float(symbol_pos.get('liqPx', 0) or symbol_pos.get('liquidation_price', 0) or 0)
            
            if liq_price > 0 and current_price > 0:
                liquidation_distance = abs(current_price - liq_price) / current_price * 100
            elif leverage > 1:
                liquidation_distance = (leverage - 1) / leverage * 100
            else:
                liquidation_distance = 100
            
            return {
                "leverage": leverage,
                "liquidation_distance_pct": liquidation_distance,
                "entry_price": entry_price,
                "current_price": current_price,
                "liquidation_price": liq_price,
                "position_size": size,
                "risk_level": "high" if liquidation_distance < 10 else "medium" if liquidation_distance < 30 else "low"
            }
            
        except Exception as e:
            logger.debug(f"分析{symbol}爆仓风险失败: {e}")
            return None
    
    async def _detect_big_orders(self, symbol: str) -> Optional[Dict]:
        """检测主力大单 - 基于K线成交量分析"""
        try:
            okx_symbol = symbol.replace('/', '-') + '-SWAP'
            
            klines = await self.exchange.get_klines(okx_symbol, '15m', limit=48)
            if not klines:
                klines = await self.exchange.get_klines(symbol.replace('/', '-'), '15m', limit=48)
            
            if not klines:
                return None
            
            volumes = [k.get('volume', 0) for k in klines]
            avg_volume = statistics.mean(volumes) if volumes else 1
            
            high_volume_bars = []
            for i, k in enumerate(klines):
                vol = k.get('volume', 0)
                if vol > avg_volume * 2:
                    high_volume_bars.append({
                        "index": i,
                        "volume": vol,
                        "volume_ratio": vol / avg_volume if avg_volume > 0 else 0,
                        "close": k.get('close', 0),
                        "open": k.get('open', 0),
                        "direction": "up" if k.get('close', 0) > k.get('open', 0) else "down"
                    })
            
            up_volume = sum(h['volume'] for h in high_volume_bars if h['direction'] == 'up')
            total_high_volume = sum(h['volume'] for h in high_volume_bars)
            buy_ratio = up_volume / total_high_volume if total_high_volume > 0 else 0.5
            
            return {
                "high_volume_bars": len(high_volume_bars),
                "total_high_volume": total_high_volume,
                "avg_volume_ratio": statistics.mean([h['volume_ratio'] for h in high_volume_bars]) if high_volume_bars else 0,
                "buy_ratio": buy_ratio,
                "threshold": avg_volume * 2,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.debug(f"检测{symbol}大单失败: {e}")
            return None
    
    async def _detect_change_signals(self, symbol: str) -> List[Dict]:
        """检测异动信号"""
        signals = []
        
        try:
            okx_symbol = symbol.replace('/', '-') + '-SWAP'
            
            klines = await self.exchange.get_klines(okx_symbol, '1H', limit=24)
            if not klines:
                klines = await self.exchange.get_klines(symbol.replace('/', '-'), '1H', limit=24)
            
            if not klines:
                return signals
            
            closes = [k.get('close', 0) for k in klines]
            volumes = [k.get('volume', 0) for k in klines]
            
            if len(closes) < 2:
                return signals
            
            change_1h = (closes[-1] - closes[-2]) / closes[-2] if closes[-2] > 0 else 0
            
            avg_volume = statistics.mean(volumes[-10:]) if len(volumes) >= 10 else 1
            volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1
            
            if change_1h > 0.02 and volume_ratio > 2:
                signals.append({
                    "type": "放量上攻",
                    "severity": "high",
                    "price_change": change_1h,
                    "volume_ratio": volume_ratio
                })
            
            if change_1h < -0.02 and volume_ratio > 2:
                signals.append({
                    "type": "放量下探",
                    "severity": "high",
                    "price_change": change_1h,
                    "volume_ratio": volume_ratio
                })
            
            if change_1h > 0.05:
                signals.append({
                    "type": "盘中大涨",
                    "severity": "medium",
                    "price_change": change_1h
                })
            
            if change_1h < -0.05:
                signals.append({
                    "type": "盘中大跌",
                    "severity": "medium",
                    "price_change": change_1h
                })
            
            high_24h = max(closes[-24:]) if len(closes) >= 24 else max(closes)
            low_24h = min(closes[-24:]) if len(closes) >= 24 else min(closes)
            
            if closes[-1] >= high_24h * 0.99:
                signals.append({
                    "type": "近期新高",
                    "severity": "medium",
                    "price": closes[-1],
                    "high": high_24h
                })
            
            if closes[-1] <= low_24h * 1.01:
                signals.append({
                    "type": "近期新低",
                    "severity": "medium",
                    "price": closes[-1],
                    "low": low_24h
                })
                
        except Exception as e:
            logger.debug(f"检测{symbol}异动信号失败: {e}")
            
        return signals
    
    async def get_market_overview(self) -> Dict[str, Any]:
        """获取市场概览"""
        overview = {
            "timestamp": datetime.now().isoformat(),
            "symbols": {}
        }
        
        tasks = [self.analyze_symbol(s) for s in self.watchlist]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for symbol, result in zip(self.watchlist, results):
            if isinstance(result, dict) and result:
                overview["symbols"][symbol] = result
        
        return overview


_own_market_analyzer: Optional[OwnMarketAnalyzer] = None


async def get_own_market_analyzer(exchange) -> Optional[OwnMarketAnalyzer]:
    """获取自主市场分析器实例"""
    global _own_market_analyzer
    
    if _own_market_analyzer is None and exchange is not None:
        _own_market_analyzer = OwnMarketAnalyzer(exchange)
        logger.info("✅ 自主市场分析器已初始化")
    
    return _own_market_analyzer
