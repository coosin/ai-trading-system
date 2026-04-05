"""
动态币种筛选器

功能：
1. 自动发现高流动性币种
2. 根据波动性筛选交易机会
3. 根据趋势强度排序
4. 动态调整监控列表
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import random

logger = logging.getLogger(__name__)


class SelectionCriteria(Enum):
    """筛选标准"""
    LIQUIDITY = "liquidity"         # 流动性
    VOLATILITY = "volatility"       # 波动性
    TREND_STRENGTH = "trend"        # 趋势强度
    VOLUME = "volume"               # 成交量
    MOMENTUM = "momentum"           # 动量
    COMPREHENSIVE = "comprehensive" # 综合评分


@dataclass
class SymbolScore:
    """币种评分"""
    symbol: str
    liquidity_score: float = 0.0
    volatility_score: float = 0.0
    trend_score: float = 0.0
    volume_score: float = 0.0
    momentum_score: float = 0.0
    comprehensive_score: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "liquidity_score": self.liquidity_score,
            "volatility_score": self.volatility_score,
            "trend_score": self.trend_score,
            "volume_score": self.volume_score,
            "momentum_score": self.momentum_score,
            "comprehensive_score": self.comprehensive_score,
            "last_updated": self.last_updated.isoformat()
        }


@dataclass
class DynamicSymbolSelectorConfig:
    """动态币种筛选器配置"""
    max_symbols: int = 10                   # 最大监控币种数
    min_symbols: int = 3                    # 最小监控币种数
    selection_interval: int = 300           # 筛选间隔（秒）
    min_24h_volume: float = 10000000        # 最小24小时成交量（USDT）
    min_volatility: float = 0.01            # 最小波动率（1%）
    max_volatility: float = 0.20            # 最大波动率（20%）
    min_liquidity_score: float = 0.5        # 最小流动性评分
    enable_auto_discovery: bool = True      # 启用自动发现
    discovery_interval: int = 3600          # 发现间隔（秒）
    always_include: List[str] = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    always_exclude: List[str] = field(default_factory=list)
    scoring_weights: Dict[str, float] = field(default_factory=lambda: {
        "liquidity": 0.25,
        "volatility": 0.20,
        "trend": 0.25,
        "volume": 0.15,
        "momentum": 0.15
    })


class DynamicSymbolSelector:
    """
    动态币种筛选器
    
    自动发现和筛选最佳交易币种
    """
    
    def __init__(self, config: Optional[DynamicSymbolSelectorConfig] = None):
        self.config = config or DynamicSymbolSelectorConfig()
        
        self.symbol_scores: Dict[str, SymbolScore] = {}
        self.current_symbols: List[str] = []
        self.candidate_symbols: List[str] = []
        
        self._exchange = None
        self._running = False
        self._selection_task: Optional[asyncio.Task] = None
        self._discovery_task: Optional[asyncio.Task] = None
        
        self._stats = {
            "total_discovered": 0,
            "total_selected": 0,
            "selection_rounds": 0
        }
        
        logger.info("动态币种筛选器初始化完成")
    
    def set_exchange(self, exchange):
        """设置交易所实例"""
        self._exchange = exchange
    
    async def initialize(self) -> bool:
        """初始化筛选器"""
        logger.info("动态币种筛选器初始化...")
        
        if self.config.always_include:
            self.current_symbols = list(self.config.always_include)
            logger.info(f"初始监控币种: {self.current_symbols}")
        
        return True
    
    async def start(self):
        """启动筛选器"""
        if self._running:
            return
        
        self._running = True
        
        if self.config.enable_auto_discovery:
            self._discovery_task = asyncio.create_task(self._discovery_loop())
        
        self._selection_task = asyncio.create_task(self._selection_loop())
        
        logger.info("✅ 动态币种筛选器已启动")
    
    async def stop(self):
        """停止筛选器"""
        self._running = False
        
        if self._selection_task:
            self._selection_task.cancel()
        if self._discovery_task:
            self._discovery_task.cancel()
        
        logger.info("动态币种筛选器已停止")
    
    async def get_trading_symbols(self) -> List[str]:
        """获取当前交易币种列表"""
        if not self.current_symbols:
            return self.config.always_include
        return self.current_symbols
    
    async def discover_symbols(self) -> List[str]:
        """
        发现可交易币种
        
        Returns:
            发现的币种列表
        """
        if not self._exchange:
            logger.warning("交易所未连接，使用默认币种")
            return self.config.always_include
        
        discovered = []
        
        try:
            markets = await self._exchange.fetch_markets()
            
            for market in markets:
                symbol = market.get("symbol", "")
                
                if not symbol.endswith("/USDT"):
                    continue
                
                if symbol in self.config.always_exclude:
                    continue
                
                if market.get("type") not in ["swap", "future"]:
                    continue
                
                try:
                    ticker = await self._exchange.fetch_ticker(symbol)
                    
                    volume_24h = ticker.get("quoteVolume", 0)
                    if volume_24h < self.config.min_24h_volume:
                        continue
                    
                    discovered.append(symbol)
                    
                except Exception as e:
                    continue
            
            self._stats["total_discovered"] = len(discovered)
            logger.info(f"发现 {len(discovered)} 个可交易币种")
            
        except Exception as e:
            logger.error(f"发现币种失败: {e}")
            return self.config.always_include
        
        return discovered
    
    async def evaluate_symbol(self, symbol: str) -> SymbolScore:
        """
        评估币种
        
        Args:
            symbol: 交易对
        
        Returns:
            币种评分
        """
        score = SymbolScore(symbol=symbol)
        
        if not self._exchange:
            return score
        
        try:
            ticker = await self._exchange.fetch_ticker(symbol)
            ohlcv = await self._exchange.fetch_ohlcv(symbol, "1h", limit=24)
            
            if not ticker or not ohlcv:
                return score
            
            volume_24h = ticker.get("quoteVolume", 0)
            score.volume_score = min(volume_24h / 100000000, 1.0)
            
            prices = [c[4] for c in ohlcv]
            if len(prices) >= 2:
                high = max(prices)
                low = min(prices)
                current = prices[-1]
                
                volatility = (high - low) / low if low > 0 else 0
                score.volatility_score = min(volatility / self.config.max_volatility, 1.0)
                
                if volatility < self.config.min_volatility:
                    score.volatility_score = 0
            
            if len(prices) >= 24:
                start_price = prices[0]
                end_price = prices[-1]
                change = (end_price - start_price) / start_price if start_price > 0 else 0
                score.trend_score = min(abs(change) / 0.1, 1.0)
                
                if change > 0:
                    score.trend_score *= 1.2
            
            if len(prices) >= 12:
                recent = prices[-4:]
                earlier = prices[-12:-8]
                recent_avg = sum(recent) / len(recent)
                earlier_avg = sum(earlier) / len(earlier)
                momentum = (recent_avg - earlier_avg) / earlier_avg if earlier_avg > 0 else 0
                score.momentum_score = min(abs(momentum) / 0.05, 1.0)
            
            bid = ticker.get("bid", 0)
            ask = ticker.get("ask", 0)
            spread = (ask - bid) / bid if bid > 0 else 1
            score.liquidity_score = max(0, 1 - spread * 100)
            
            weights = self.config.scoring_weights
            score.comprehensive_score = (
                score.liquidity_score * weights.get("liquidity", 0.25) +
                score.volatility_score * weights.get("volatility", 0.20) +
                score.trend_score * weights.get("trend", 0.25) +
                score.volume_score * weights.get("volume", 0.15) +
                score.momentum_score * weights.get("momentum", 0.15)
            )
            
            score.last_updated = datetime.now()
            
        except Exception as e:
            logger.debug(f"评估 {symbol} 失败: {e}")
        
        return score
    
    async def select_best_symbols(self, candidates: List[str]) -> List[str]:
        """
        选择最佳币种
        
        Args:
            candidates: 候选币种列表
        
        Returns:
            最佳币种列表
        """
        scores = []
        
        for symbol in candidates:
            score = await self.evaluate_symbol(symbol)
            if score.comprehensive_score > 0:
                scores.append(score)
                self.symbol_scores[symbol] = score
        
        scores.sort(key=lambda s: s.comprehensive_score, reverse=True)
        
        selected = list(self.config.always_include)
        
        for score in scores:
            if len(selected) >= self.config.max_symbols:
                break
            
            if score.symbol not in selected:
                if score.liquidity_score >= self.config.min_liquidity_score:
                    selected.append(score.symbol)
        
        while len(selected) < self.config.min_symbols and len(scores) > len(selected):
            for score in scores:
                if score.symbol not in selected:
                    selected.append(score.symbol)
                    if len(selected) >= self.config.min_symbols:
                        break
        
        self._stats["total_selected"] = len(selected)
        self._stats["selection_rounds"] += 1
        
        return selected
    
    async def update_selection(self) -> List[str]:
        """更新选择"""
        candidates = await self.discover_symbols()
        self.candidate_symbols = candidates
        
        best_symbols = await self.select_best_symbols(candidates)
        
        old_symbols = set(self.current_symbols)
        new_symbols = set(best_symbols)
        
        added = new_symbols - old_symbols
        removed = old_symbols - new_symbols
        
        if added or removed:
            logger.info(f"📊 币种更新:")
            if added:
                logger.info(f"   新增: {added}")
            if removed:
                logger.info(f"   移除: {removed}")
        
        self.current_symbols = best_symbols
        
        return best_symbols
    
    async def _selection_loop(self):
        """选择循环"""
        while self._running:
            try:
                await self.update_selection()
                await asyncio.sleep(self.config.selection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"选择循环错误: {e}")
                await asyncio.sleep(60)
    
    async def _discovery_loop(self):
        """发现循环"""
        while self._running:
            try:
                candidates = await self.discover_symbols()
                self.candidate_symbols = candidates
                await asyncio.sleep(self.config.discovery_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"发现循环错误: {e}")
                await asyncio.sleep(300)
    
    def get_symbol_score(self, symbol: str) -> Optional[SymbolScore]:
        """获取币种评分"""
        return self.symbol_scores.get(symbol)
    
    def get_top_symbols(self, limit: int = 10) -> List[SymbolScore]:
        """获取评分最高的币种"""
        scores = list(self.symbol_scores.values())
        scores.sort(key=lambda s: s.comprehensive_score, reverse=True)
        return scores[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "current_symbols_count": len(self.current_symbols),
            "candidate_symbols_count": len(self.candidate_symbols),
            "current_symbols": self.current_symbols
        }
    
    async def cleanup(self):
        """清理资源"""
        await self.stop()
        logger.info("动态币种筛选器清理完成")


def create_dynamic_symbol_selector(
    config: Optional[DynamicSymbolSelectorConfig] = None
) -> DynamicSymbolSelector:
    """创建动态币种筛选器实例"""
    return DynamicSymbolSelector(config)
