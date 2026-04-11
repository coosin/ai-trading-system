"""
AI主动性增强模块

让AI智能体主动工作，主动介入交易系统的各个环节：
1. 主动市场扫描 - 持续扫描市场，发现交易机会
2. 主动信息收集 - 自动获取第三方资源信息分析
3. 主动策略评估 - 评估并选择最优策略
4. 主动行动触发 - 在发现机会时立即行动
"""

import asyncio
import logging
import json
import math
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from src.modules.core.module_config_utils import resolve_module_config

logger = logging.getLogger(__name__)

from .timing_constants import SLEEP_1S, SLEEP_5S, SLEEP_10S, SLEEP_30S, SLEEP_60S, SLEEP_5MIN


def _coerce_fear_greed_index(raw: Any) -> Optional[float]:
    """Normalize API responses (float / int / nested dict) to a scalar index."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        try:
            x = float(raw)
            return x if math.isfinite(x) else None
        except Exception:
            return None
    if isinstance(raw, dict):
        for key in ("value", "index", "score", "data", "fear_greed_index", "fearAndGreedIndex"):
            if key not in raw:
                continue
            inner = _coerce_fear_greed_index(raw.get(key))
            if inner is not None:
                return inner
    return None


class ProactiveLevel(Enum):
    """主动性等级"""
    PASSIVE = "passive"         # 被动 - 只响应请求
    MODERATE = "moderate"       # 适度 - 定期扫描
    ACTIVE = "active"           # 主动 - 持续监控
    AGGRESSIVE = "aggressive"   # 激进 - 积极寻找机会


class OpportunityType(Enum):
    """机会类型"""
    TREND_REVERSAL = "trend_reversal"     # 趋势反转
    BREAKOUT = "breakout"                 # 突破
    MEAN_REVERSION = "mean_reversion"     # 均值回归
    NEWS_DRIVEN = "news_driven"           # 新闻驱动
    SENTIMENT_SHIFT = "sentiment_shift"   # 情绪转变
    ARBITRAGE = "arbitrage"               # 套利
    VOLATILITY_SPIKE = "volatility_spike" # 波动率飙升
    LIQUIDITY_EVENT = "liquidity_event"   # 流动性事件


@dataclass
class MarketOpportunity:
    """市场机会"""
    symbol: str
    opportunity_type: OpportunityType
    direction: str  # long, short, neutral
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    reasoning: str
    data_sources: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    priority: int = 0  # 越高越优先
    expires_at: Optional[datetime] = None


@dataclass
class MarketInsight:
    """市场洞察"""
    symbol: str
    trend: str
    trend_strength: float
    volatility: float
    volume_profile: str
    support_levels: List[float]
    resistance_levels: List[float]
    sentiment: str
    sentiment_score: float
    news_impact: Optional[str] = None
    onchain_signals: Optional[Dict] = None
    timestamp: datetime = field(default_factory=datetime.now)


class ProactiveMarketScanner:
    """主动性市场扫描器"""
    
    def __init__(self, main_controller=None, config: Optional[Dict] = None):
        self.main_controller = main_controller
        self.config = config or {}
        
        self.exchange = None
        self.llm = None
        self.data_integration = None
        self.memory = None
        self.telegram_bot = None
        
        self._running = False
        self._scan_interval = self.config.get("scan_interval", 30)
        self._deep_scan_interval = self.config.get("deep_scan_interval", 300)
        self._proactive_level = ProactiveLevel.ACTIVE
        
        self._opportunities: List[MarketOpportunity] = []
        self._insights: Dict[str, MarketInsight] = {}
        self._watch_list: List[str] = []
        self._alert_callbacks: List[Callable] = []
        
        self._market_state = {
            "trend": "unknown",
            "volatility_regime": "normal",
            "risk_sentiment": "neutral",
            "liquidity": "normal",
        }
        
        self._stats = {
            "total_scans": 0,
            "opportunities_found": 0,
            "actions_taken": 0,
            "insights_generated": 0,
        }

        # 主动性下单节流：减少突破类重复开仓与同品种高频触发
        self._last_proactive_trade_at: Dict[str, datetime] = {}
        self._proactive_symbol_cooldown_sec = float(
            self.config.get("proactive_symbol_trade_cooldown_sec", 180)
        )
        self._breakout_trade_cooldown_sec = float(
            self.config.get("breakout_trade_cooldown_sec", 600)
        )
        self._skip_breakout_if_same_side = bool(
            self.config.get("proactive_skip_breakout_if_same_side_position", True)
        )
        # 执行门槛：默认高于 0.7，减少「略靠近极值就开仓」
        self._execute_min_confidence = float(
            self.config.get("proactive_execute_min_confidence", 0.78)
        )
        # 均值回归：24h 涨跌幅绝对值低于此则不生成机会（原 5% 过易触发）
        self._mean_reversion_min_abs_change = float(
            self.config.get("mean_reversion_min_abs_change", 0.08)
        )
        # 突破：最后一根成交量需 >= 前 N 根均量 × 该比例；0 表示不检查成交量
        self._breakout_min_vol_ratio = float(
            self.config.get("breakout_min_volume_vs_prior_avg", 0) or 0
        )
        # False：掃描器不直接開倉，只把機會交給 ai_core 在決策循環中研判
        self._auto_execute_opportunities = bool(
            self.config.get("proactive_auto_execute_opportunities", False)
        )
        self._ai_core_forward_cooldown_sec = float(
            self.config.get("proactive_ai_core_forward_cooldown_sec", 180)
        )
        self._last_ai_core_hint_at: Dict[str, datetime] = {}
        self._opportunity_gate: Any = None
        self._last_opportunity_log_at: Dict[str, datetime] = {}
        self._opportunity_log_cooldown_sec: float = float(self.config.get("opportunity_log_cooldown_sec", 120) or 120)

    def _upsert_opportunity(self, opportunity: MarketOpportunity) -> None:
        """同品种+类型+方向只保留最新一条，避免列表堆满重复机会每 10s 反复尝试。"""
        key = (opportunity.symbol, opportunity.opportunity_type, opportunity.direction)
        self._opportunities = [
            o
            for o in self._opportunities
            if (o.symbol, o.opportunity_type, o.direction) != key
        ]
        self._opportunities.append(opportunity)

    @staticmethod
    def _norm_symbol_key(symbol: str) -> str:
        return str(symbol or "").replace(" ", "").upper()

    @staticmethod
    def _breakout_sl_tp(
        direction: str, entry: float, low_24h: float, high_24h: float
    ) -> tuple:
        """突破单：止损必须在入场正确一侧（多下、空上），避免 24h 极值与现价错位时传错绝对价。"""
        e, lo, hi = float(entry), float(low_24h), float(high_24h)
        sl_buf, tp_buf = 0.02, 0.05
        if direction == "long":
            sl = min(lo, e * (1 - sl_buf))
            if sl >= e:
                sl = e * (1 - sl_buf)
            tp = max(e * (1 + tp_buf), e * 1.05)
        else:
            sl = max(hi, e * (1 + sl_buf))
            if sl <= e:
                sl = e * (1 + sl_buf)
            tp = min(e * (1 - tp_buf), e * 0.95)
        return sl, tp

    async def _has_same_side_position(self, symbol: str, direction: str) -> bool:
        if not self.exchange or not hasattr(self.exchange, "get_positions"):
            return False
        want = str(direction or "").strip().lower()
        if want not in ("long", "short"):
            return False
        base = str(symbol or "").split("/")[0].strip().upper()
        if not base:
            return False
        try:
            rows = await self.exchange.get_positions()
        except Exception:
            return False
        for p in rows or []:
            if not isinstance(p, dict):
                continue
            sz = float(p.get("size", 0) or 0)
            if sz <= 1e-12:
                continue
            if str(p.get("side", "")).lower() != want:
                continue
            iid = str(p.get("instId", "")).upper()
            sym = str(p.get("symbol", "")).upper().replace("-", "/")
            if base in iid or (base + "/") in sym or sym.startswith(base + "/"):
                return True
        return False

    @staticmethod
    def _zh_direction(v: str) -> str:
        m = {"long": "做多", "short": "做空", "neutral": "中性"}
        return m.get(str(v or "").lower(), str(v))

    @staticmethod
    def _zh_trend(v: str) -> str:
        m = {"bullish": "看涨", "bearish": "看跌", "sideways": "震荡", "mixed": "混合", "unknown": "未知"}
        return m.get(str(v or "").lower(), str(v))

    @staticmethod
    def _zh_sentiment(v: str) -> str:
        m = {"bullish": "乐观", "bearish": "悲观", "neutral": "中性", "fear": "恐惧", "greed": "贪婪"}
        return m.get(str(v or "").lower(), str(v))

    @staticmethod
    def _zh_volatility(v: str) -> str:
        m = {"low": "低", "normal": "正常", "high": "高", "extreme": "极高"}
        return m.get(str(v or "").lower(), str(v))

    @staticmethod
    def _zh_opp_type(v: str) -> str:
        m = {
            "breakout": "突破",
            "trend_reversal": "趋势反转",
            "mean_reversion": "均值回归",
            "news_driven": "新闻驱动",
            "sentiment_shift": "情绪转折",
            "arbitrage": "套利",
            "volatility_spike": "波动率飙升",
            "liquidity_event": "流动性事件",
        }
        return m.get(str(v or "").lower(), str(v))
    
    async def initialize(self) -> bool:
        """初始化"""
        logger.info("🚀 初始化主动性市场扫描器...")
        
        if self.main_controller:
            config_manager = getattr(self.main_controller, "config_manager", None)
            if config_manager:
                try:
                    cfg = await config_manager.get_config("proactive_scanner", {})
                    if isinstance(cfg, dict):
                        merged = dict(cfg)
                        merged.update(self.config)
                        self.config = merged
                except Exception as e:
                    logger.debug(f"读取proactive_scanner配置失败，使用当前配置: {e}")

            self._scan_interval = self.config.get("scan_interval", self._scan_interval)
            self._deep_scan_interval = self.config.get("deep_scan_interval", self._deep_scan_interval)
            self._execute_min_confidence = float(
                self.config.get("proactive_execute_min_confidence", self._execute_min_confidence)
            )
            self._mean_reversion_min_abs_change = float(
                self.config.get("mean_reversion_min_abs_change", self._mean_reversion_min_abs_change)
            )
            self._breakout_min_vol_ratio = float(
                self.config.get("breakout_min_volume_vs_prior_avg", self._breakout_min_vol_ratio)
                or 0
            )
            self._proactive_symbol_cooldown_sec = float(
                self.config.get("proactive_symbol_trade_cooldown_sec", self._proactive_symbol_cooldown_sec)
            )
            self._breakout_trade_cooldown_sec = float(
                self.config.get("breakout_trade_cooldown_sec", self._breakout_trade_cooldown_sec)
            )
            self._skip_breakout_if_same_side = bool(
                self.config.get("proactive_skip_breakout_if_same_side_position", self._skip_breakout_if_same_side)
            )
            self._auto_execute_opportunities = bool(
                self.config.get("proactive_auto_execute_opportunities", self._auto_execute_opportunities)
            )
            self._ai_core_forward_cooldown_sec = float(
                self.config.get(
                    "proactive_ai_core_forward_cooldown_sec",
                    self._ai_core_forward_cooldown_sec,
                )
            )

            self.exchange = getattr(self.main_controller, 'okx_exchange', None) or \
                           getattr(self.main_controller, 'exchange', None)
            self.llm = getattr(self.main_controller, 'llm_integration', None)
            self.data_integration = getattr(self.main_controller, 'data_integration', None)
            self.memory = getattr(self.main_controller, 'memory', None)
            self.telegram_bot = getattr(self.main_controller, 'telegram_bot', None)

            try:
                from src.modules.core.scanner_opportunity_gate import ScannerOpportunityGate

                gc = self.config.get("scanner_opportunity_gate") or {}
                self._opportunity_gate = (
                    ScannerOpportunityGate(self.exchange, gc, main_controller=self.main_controller) if self.exchange else None
                )
            except Exception as e:
                logger.debug("ScannerOpportunityGate 初始化跳过: %s", e)
                self._opportunity_gate = None
        
        logger.info("✅ 主动性市场扫描器初始化完成")
        return True
    
    async def start(self) -> None:
        """启动主动扫描"""
        if self._running:
            return
        
        self._running = True
        logger.info(f"🔍 启动主动性市场扫描 (级别: {self._proactive_level.value})")
        
        asyncio.create_task(self._continuous_scan_loop())
        asyncio.create_task(self._deep_analysis_loop())
        asyncio.create_task(self._opportunity_monitoring_loop())
        asyncio.create_task(self._market_state_update_loop())
    
    async def stop(self) -> None:
        """停止"""
        self._running = False
        logger.info("🛑 主动性市场扫描器已停止")
    
    async def _continuous_scan_loop(self) -> None:
        """持续扫描循环 - 快速发现机会"""
        while self._running:
            try:
                self._stats["total_scans"] += 1
                
                symbols = await self._get_active_symbols()
                
                for symbol in symbols:
                    try:
                        opportunity = await self._quick_scan_symbol(symbol)
                        if opportunity:
                            self._upsert_opportunity(opportunity)
                            self._stats["opportunities_found"] += 1
                            
                            await self._notify_opportunity(opportunity)
                    except Exception as e:
                        logger.debug(f"扫描 {symbol} 失败: {e}")
                
                self._opportunities = [o for o in self._opportunities 
                                       if not o.expires_at or o.expires_at > datetime.now()]
                
                await asyncio.sleep(self._scan_interval)
                
            except Exception as e:
                logger.error(f"持续扫描循环错误: {e}")
                await asyncio.sleep(SLEEP_5S)
    
    async def _deep_analysis_loop(self) -> None:
        """深度分析循环 - 全面市场分析"""
        while self._running:
            try:
                logger.info("🔍 执行深度市场分析...")
                
                symbols = await self._get_active_symbols()
                
                for symbol in symbols[:10]:
                    try:
                        insight = await self._deep_analyze_symbol(symbol)
                        if insight:
                            self._insights[symbol] = insight
                            self._stats["insights_generated"] += 1
                    except Exception as e:
                        logger.debug(f"深度分析 {symbol} 失败: {e}")
                
                await self._generate_market_report()
                
                await asyncio.sleep(self._deep_scan_interval)
                
            except Exception as e:
                logger.error(f"深度分析循环错误: {e}")
                await asyncio.sleep(SLEEP_60S)
    
    async def _opportunity_monitoring_loop(self) -> None:
        """机会监控循环 - 监控并执行机会"""
        while self._running:
            try:
                if self._opportunities:
                    sorted_opportunities = sorted(
                        self._opportunities,
                        key=lambda o: (o.priority, o.confidence),
                        reverse=True
                    )
                    
                    for opp in sorted_opportunities[:3]:
                        if opp.confidence >= self._execute_min_confidence:
                            if self._auto_execute_opportunities:
                                await self._evaluate_and_execute(opp)
                            else:
                                await self._forward_opportunity_to_ai_core(opp)
                
                await asyncio.sleep(SLEEP_10S)
                
            except Exception as e:
                logger.error(f"机会监控循环错误: {e}")
                await asyncio.sleep(SLEEP_5S)
    
    async def _market_state_update_loop(self) -> None:
        """市场状态更新循环"""
        while self._running:
            try:
                self._market_state = await self._assess_market_state()
                await asyncio.sleep(SLEEP_60S)
            except Exception as e:
                logger.error(f"市场状态更新错误: {e}")
                await asyncio.sleep(SLEEP_30S)
    
    async def _get_active_symbols(self) -> List[str]:
        """获取活跃交易对"""
        default_symbols = self.config.get("default_symbols", [
            "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
            "XRP/USDT", "DOGE/USDT", "ADA/USDT", "AVAX/USDT",
            "DOT/USDT", "MATIC/USDT", "LINK/USDT", "ATOM/USDT"
        ])
        
        if not self.exchange:
            return default_symbols
        
        try:
            if hasattr(self.exchange, 'get_symbols'):
                symbols = await self.exchange.get_symbols()
                usdt_symbols = [s for s in symbols if '/USDT' in s or '-USDT' in s]
                if usdt_symbols:
                    return usdt_symbols[:20]
        except Exception as e:
            logger.debug(f"读取交易所交易对失败，使用默认列表: {e}")
        
        return default_symbols
    
    async def _quick_scan_symbol(self, symbol: str) -> Optional[MarketOpportunity]:
        """快速扫描单个交易对"""
        if not self.exchange:
            return None
        
        try:
            ticker = await self.exchange.get_ticker(symbol.replace('/', '-'))
            if not ticker:
                return None
            
            price = float(ticker.get('last', 0))
            change_24h = float(ticker.get('change24h', 0) or ticker.get('change', 0))
            volume = float(ticker.get('volume', 0) or 0)
            
            if abs(change_24h) > self._mean_reversion_min_abs_change:
                direction = "short" if change_24h > 0 else "long"
                confidence = min(0.9, abs(change_24h) * 10)
                
                return MarketOpportunity(
                    symbol=symbol,
                    opportunity_type=OpportunityType.MEAN_REVERSION,
                    direction=direction,
                    confidence=confidence,
                    entry_price=price,
                    stop_loss=price * (1 + 0.02 if direction == "short" else -0.02),
                    take_profit=price * (1 - 0.05 if direction == "short" else 1.05),
                    reasoning=f"24小时{'涨幅' if change_24h > 0 else '跌幅'} {abs(change_24h)*100:.1f}%，均值回归机会",
                    data_sources=["ticker"],
                    priority=int(confidence * 10),
                    expires_at=datetime.now() + timedelta(minutes=30)
                )
            
            if volume > 0:
                try:
                    klines = await self.exchange.get_klines(symbol.replace('/', '-'), '1h', limit=24)
                    if klines and len(klines) >= 20:
                        closes = self._extract_kline_values(klines, "close")
                        volumes = self._extract_kline_values(klines, "volume")
                        if len(closes) < 6:
                            return None
                        current_price = closes[-1]
                        prior = closes[:-1]
                        prior_high = max(prior)
                        prior_low = min(prior)
                        high_24h = max(closes)
                        low_24h = min(closes)

                        def _vol_ok() -> bool:
                            r = self._breakout_min_vol_ratio
                            if r <= 0 or len(volumes) < len(closes):
                                return True
                            if len(volumes) < 6:
                                return True
                            last_v = float(volumes[-1] or 0)
                            prev = [float(volumes[i] or 0) for i in range(-6, -1)]
                            avg_v = sum(prev) / max(1, len(prev))
                            if avg_v <= 0:
                                return True
                            return last_v >= avg_v * r

                        # 须「当前收盘」真正创出前 23 根内新高/新低，而非仅贴近 24h 收盘区间上沿
                        if current_price > prior_high and _vol_ok():
                            sl, tp = self._breakout_sl_tp(
                                "long", current_price, low_24h, high_24h
                            )
                            return MarketOpportunity(
                                symbol=symbol,
                                opportunity_type=OpportunityType.BREAKOUT,
                                direction="long",
                                confidence=0.82,
                                entry_price=current_price,
                                stop_loss=sl,
                                take_profit=tp,
                                reasoning=(
                                    f"突破前23根收盘区间高点 "
                                    f"(前高 {prior_high:.4f} → 收盘 {current_price:.4f})"
                                ),
                                data_sources=["ticker", "klines"],
                                priority=7,
                                expires_at=datetime.now() + timedelta(hours=2)
                            )

                        if current_price < prior_low and _vol_ok():
                            sl, tp = self._breakout_sl_tp(
                                "short", current_price, low_24h, high_24h
                            )
                            return MarketOpportunity(
                                symbol=symbol,
                                opportunity_type=OpportunityType.BREAKOUT,
                                direction="short",
                                confidence=0.82,
                                entry_price=current_price,
                                stop_loss=sl,
                                take_profit=tp,
                                reasoning=(
                                    f"跌破前23根收盘区间低点 "
                                    f"(前低 {prior_low:.4f} → 收盘 {current_price:.4f})"
                                ),
                                data_sources=["ticker", "klines"],
                                priority=7,
                                expires_at=datetime.now() + timedelta(hours=2)
                            )
                except Exception as e:
                    logger.debug(f"获取K线失败 {symbol}: {e}")
            
        except Exception as e:
            logger.debug(f"快速扫描 {symbol} 失败: {e}")
        
        return None
    
    async def _deep_analyze_symbol(self, symbol: str) -> Optional[MarketInsight]:
        """深度分析单个交易对"""
        if not self.exchange:
            return None
        
        try:
            ticker = await self.exchange.get_ticker(symbol.replace('/', '-'))
            if not ticker:
                return None
            
            price = float(ticker.get('last', 0))
            
            klines_1h = await self.exchange.get_klines(symbol.replace('/', '-'), '1h', limit=100)
            klines_4h = await self.exchange.get_klines(symbol.replace('/', '-'), '4h', limit=50)
            
            if not klines_1h or len(klines_1h) < 20:
                return None
            
            closes_1h = self._extract_kline_values(klines_1h, "close")
            highs_1h = self._extract_kline_values(klines_1h, "high")
            lows_1h = self._extract_kline_values(klines_1h, "low")
            volumes_1h = self._extract_kline_values(klines_1h, "volume")
            if len(closes_1h) < 20 or len(highs_1h) < 20 or len(lows_1h) < 20:
                return None
            
            ma20 = sum(closes_1h[-20:]) / 20
            ma50 = sum(closes_1h[-50:]) / 50 if len(closes_1h) >= 50 else ma20
            
            current_price = closes_1h[-1]
            trend = "bullish" if current_price > ma20 > ma50 else "bearish" if current_price < ma20 < ma50 else "sideways"
            
            returns = [(closes_1h[i] - closes_1h[i-1]) / closes_1h[i-1] 
                      for i in range(1, len(closes_1h))]
            volatility = (sum(r**2 for r in returns) / len(returns)) ** 0.5 * (24 ** 0.5)
            
            recent_high = max(highs_1h[-24:])
            recent_low = min(lows_1h[-24:])
            
            resistance_levels = self._find_levels(highs_1h[-50:], closes_1h[-50:])
            support_levels = self._find_levels(lows_1h[-50:], closes_1h[-50:], is_support=True)
            
            avg_volume = sum(volumes_1h[-24:]) / 24
            current_volume = volumes_1h[-1]
            volume_profile = "high" if current_volume > avg_volume * 1.5 else "low" if current_volume < avg_volume * 0.5 else "normal"
            
            sentiment = "neutral"
            sentiment_score = 0.5
            news_impact = None
            
            if self.data_integration:
                try:
                    third_party_data = await self.data_integration.get_third_party_data(symbol)
                    if third_party_data:
                        sentiment_score = third_party_data.get('sentiment_score', 0.5)
                        if sentiment_score > 0.6:
                            sentiment = "bullish"
                        elif sentiment_score < 0.4:
                            sentiment = "bearish"
                        news_impact = third_party_data.get('news_summary', None)
                except Exception as e:
                    logger.debug(f"读取第三方情绪数据失败 {symbol}: {e}")
            
            trend_strength = abs(current_price - ma20) / ma20 if ma20 > 0 else 0
            
            return MarketInsight(
                symbol=symbol,
                trend=trend,
                trend_strength=trend_strength,
                volatility=volatility,
                volume_profile=volume_profile,
                support_levels=support_levels[-3:] if support_levels else [recent_low],
                resistance_levels=resistance_levels[-3:] if resistance_levels else [recent_high],
                sentiment=sentiment,
                sentiment_score=sentiment_score,
                news_impact=news_impact,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"深度分析 {symbol} 失败: {e}")
            return None

    def _extract_kline_values(self, klines: List[Any], field: str) -> List[float]:
        """
        Normalize kline payloads from dict/list formats.
        Expected list format: [ts, open, high, low, close, volume, ...]
        """
        idx_map = {"high": 2, "low": 3, "close": 4, "volume": 5}
        dict_keys = {
            "high": ("high", "h"),
            "low": ("low", "l"),
            "close": ("close", "c"),
            "volume": ("volume", "v"),
        }
        values: List[float] = []
        for k in klines:
            raw = None
            if isinstance(k, dict):
                for key in dict_keys[field]:
                    if key in k:
                        raw = k.get(key)
                        break
            elif isinstance(k, (list, tuple)) and len(k) > idx_map[field]:
                raw = k[idx_map[field]]
            try:
                if raw is not None:
                    values.append(float(raw))
            except (TypeError, ValueError):
                continue
        return values
    
    def _find_levels(self, price_series: List[float], closes: List[float], 
                     is_support: bool = False) -> List[float]:
        """寻找支撑/阻力位"""
        levels = []
        if len(price_series) < 5:
            return levels
        
        for i in range(2, len(price_series) - 2):
            if is_support:
                if (price_series[i] < price_series[i-1] and 
                    price_series[i] < price_series[i-2] and
                    price_series[i] < price_series[i+1] and
                    price_series[i] < price_series[i+2]):
                    levels.append(price_series[i])
            else:
                if (price_series[i] > price_series[i-1] and 
                    price_series[i] > price_series[i-2] and
                    price_series[i] > price_series[i+1] and
                    price_series[i] > price_series[i+2]):
                    levels.append(price_series[i])
        
        return sorted(set(levels), reverse=not is_support)
    
    async def _assess_market_state(self) -> Dict[str, str]:
        """评估市场状态"""
        state = {
            "trend": "unknown",
            "volatility_regime": "normal",
            "risk_sentiment": "neutral",
            "liquidity": "normal",
        }
        
        if not self._insights:
            return state
        
        bullish_count = sum(1 for i in self._insights.values() if i.trend == "bullish")
        bearish_count = sum(1 for i in self._insights.values() if i.trend == "bearish")
        total = len(self._insights)
        
        if bullish_count > total * 0.6:
            state["trend"] = "bullish"
        elif bearish_count > total * 0.6:
            state["trend"] = "bearish"
        else:
            state["trend"] = "mixed"
        
        avg_volatility = sum(i.volatility for i in self._insights.values()) / len(self._insights)
        if avg_volatility > 0.05:
            state["volatility_regime"] = "high"
        elif avg_volatility < 0.02:
            state["volatility_regime"] = "low"
        
        avg_sentiment = sum(i.sentiment_score for i in self._insights.values()) / len(self._insights)
        if avg_sentiment > 0.6:
            state["risk_sentiment"] = "risk_on"
        elif avg_sentiment < 0.4:
            state["risk_sentiment"] = "risk_off"
        
        return state
    
    async def _notify_opportunity(self, opportunity: MarketOpportunity) -> None:
        """通知发现的机会"""
        # 注意：机会发现属于高频事件，默认不写 INFO（否则会刷爆 app.log）。
        # 需要观测时可通过 market.update / 前端事件流查看。
        try:
            logger.debug(
                "发现交易机会(已降级为debug): %s %s conf=%.0f%% type=%s",
                opportunity.symbol,
                opportunity.direction,
                opportunity.confidence * 100,
                opportunity.opportunity_type.value,
            )
        except Exception:
            pass
        
        for callback in self._alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(opportunity)
                else:
                    callback(opportunity)
            except Exception as e:
                logger.error(f"机会通知回调失败: {e}")
    
    async def _forward_opportunity_to_ai_core(self, opportunity: MarketOpportunity) -> None:
        """
        將掃描到的機會交給「统一行情分析层」二次分析后再推送：
        扫描器只负责发现+初筛，不直接影响 ai_core 的决策上下文。
        """
        mc = self.main_controller
        if not mc:
            return
        mi = getattr(mc, "market_intelligence", None)
        if not mi or not hasattr(mi, "ingest_scanner_opportunity"):
            logger.debug("未找到 market_intelligence.ingest_scanner_opportunity，跳過掃描機會轉發")
            return
        fk = (
            f"aicore:{self._norm_symbol_key(opportunity.symbol)}:"
            f"{opportunity.opportunity_type.value}:{opportunity.direction}"
        )
        now = datetime.now()
        last = self._last_ai_core_hint_at.get(fk)
        if last and (now - last).total_seconds() < self._ai_core_forward_cooldown_sec:
            return

        gate_metrics: Dict[str, Any] = {}
        gate_reason = ""
        if self._opportunity_gate:
            gr = await self._opportunity_gate.evaluate(
                opportunity, self._insights.get(opportunity.symbol)
            )
            if not gr.passed:
                logger.info(
                    "⛔ 实时数据预检未通过，不报 ai_core: %s — %s",
                    opportunity.symbol,
                    gr.reason,
                )
                return
            gate_reason = gr.reason
            gate_metrics = dict(gr.metrics or {})

        self._last_ai_core_hint_at[fk] = now
        payload = {
            "symbol": opportunity.symbol,
            "direction": opportunity.direction,
            "opportunity_type": opportunity.opportunity_type.value,
            "confidence": opportunity.confidence,
            "entry_price": opportunity.entry_price,
            "stop_loss": opportunity.stop_loss,
            "take_profit": opportunity.take_profit,
            "reasoning": opportunity.reasoning,
            "priority": opportunity.priority,
            "data_sources": list(opportunity.data_sources or []),
        }
        if gate_metrics:
            payload["gate_pass_reason"] = gate_reason
            payload["gate_metrics"] = gate_metrics
        try:
            await mi.ingest_scanner_opportunity(payload)
            logger.info(
                "📨 掃描機會已交給统一行情分析层二次研判并推送: %s %s %s",
                opportunity.symbol,
                self._zh_direction(opportunity.direction),
                self._zh_opp_type(opportunity.opportunity_type.value),
            )
        except Exception as e:
            logger.warning("掃描機會轉發分析层失敗: %s", e)

    async def _evaluate_and_execute(self, opportunity: MarketOpportunity) -> bool:
        """评估并执行机会（僅在 proactive_auto_execute_opportunities=true 時由監控迴圈調用）"""
        logger.info(f"⚡ 评估机会: {opportunity.symbol} {self._zh_direction(opportunity.direction)}")

        sym_key = self._norm_symbol_key(opportunity.symbol)
        now = datetime.now()
        last_any = self._last_proactive_trade_at.get(f"sym:{sym_key}")
        if last_any and (now - last_any).total_seconds() < self._proactive_symbol_cooldown_sec:
            logger.info(
                "⏳ 跳过机会(同品种冷却 %ds): %s",
                int(self._proactive_symbol_cooldown_sec),
                sym_key,
            )
            return False
        if opportunity.opportunity_type == OpportunityType.BREAKOUT:
            last_bo = self._last_proactive_trade_at.get(f"breakout:{sym_key}")
            if last_bo and (now - last_bo).total_seconds() < self._breakout_trade_cooldown_sec:
                logger.info(
                    "⏳ 跳过机会(突破冷却 %ds): %s",
                    int(self._breakout_trade_cooldown_sec),
                    sym_key,
                )
                return False
            if self._skip_breakout_if_same_side:
                if await self._has_same_side_position(
                    opportunity.symbol, opportunity.direction
                ):
                    logger.info(
                        "⏳ 跳过突破机会(已有同向持仓): %s %s",
                        sym_key,
                        opportunity.direction,
                    )
                    return False
        
        insight = self._insights.get(opportunity.symbol)
        
        if insight:
            if opportunity.direction == "long" and insight.trend == "bearish" and insight.trend_strength > 0.05:
                logger.info(f"❌ 跳过机会: {opportunity.symbol} 做多信号与下跌趋势冲突")
                return False
            
            if opportunity.direction == "short" and insight.trend == "bullish" and insight.trend_strength > 0.05:
                logger.info(f"❌ 跳过机会: {opportunity.symbol} 做空信号与上涨趋势冲突")
                return False

        if self._opportunity_gate:
            gr = await self._opportunity_gate.evaluate(opportunity, insight)
            if not gr.passed:
                logger.info(
                    "⛔ 实时数据预检未通过，跳过自动开仓: %s — %s",
                    opportunity.symbol,
                    gr.reason,
                )
                return False
        
        if self.main_controller and hasattr(self.main_controller, 'ai_trading_engine'):
            engine = self.main_controller.ai_trading_engine
            if engine and hasattr(engine, 'execute_trade'):
                try:
                    result = await engine.execute_trade(
                        symbol=opportunity.symbol,
                        side=opportunity.direction,
                        quantity=None,
                        stop_loss=opportunity.stop_loss,
                        take_profit=opportunity.take_profit,
                        reasoning=opportunity.reasoning
                    )
                    if result:
                        self._stats["actions_taken"] += 1
                        ts = datetime.now()
                        self._last_proactive_trade_at[f"sym:{sym_key}"] = ts
                        if opportunity.opportunity_type == OpportunityType.BREAKOUT:
                            self._last_proactive_trade_at[f"breakout:{sym_key}"] = ts
                        logger.info(f"✅ 执行机会成功: {opportunity.symbol}")
                        return True
                except Exception as e:
                    logger.error(f"执行机会失败: {e}")
        
        return False
    
    async def _generate_market_report(self) -> None:
        """生成市场报告"""
        if not self._insights:
            return
        
        report_lines = [
            "📊 市场分析报告",
            f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"市场状态: {self._zh_trend(self._market_state['trend'])} | 波动率: {self._zh_volatility(self._market_state['volatility_regime'])} | 情绪: {self._zh_sentiment(self._market_state['risk_sentiment'])}",
            "",
            "主要洞察:"
        ]
        
        sorted_insights = sorted(
            self._insights.items(),
            key=lambda x: abs(x[1].trend_strength),
            reverse=True
        )[:5]
        
        for symbol, insight in sorted_insights:
            trend_emoji = "📈" if insight.trend == "bullish" else "📉" if insight.trend == "bearish" else "➡️"
            report_lines.append(
                f"  {trend_emoji} {symbol}: {self._zh_trend(insight.trend)} (强度: {insight.trend_strength:.1%}) | "
                f"波动率: {insight.volatility:.2%} | 情绪: {self._zh_sentiment(insight.sentiment)}"
            )
        
        if self._opportunities:
            report_lines.append("")
            report_lines.append(f"🎯 发现 {len(self._opportunities)} 个交易机会:")
            for opp in sorted(self._opportunities, key=lambda o: o.priority, reverse=True)[:3]:
                report_lines.append(
                    f"  • {opp.symbol}: {self._zh_direction(opp.direction)}（{self._zh_opp_type(opp.opportunity_type.value)}）- 置信度 {opp.confidence:.0%}"
                )
        
        report = "\n".join(report_lines)
        logger.info(report)
        
        if self.main_controller and hasattr(self.main_controller, "_send_notification_handler") and self._stats["total_scans"] % 10 == 0:
            try:
                await self.main_controller._send_notification_handler("扫描报告", report, priority="low")
            except Exception:
                pass
    
    def add_alert_callback(self, callback: Callable) -> None:
        """添加告警回调"""
        self._alert_callbacks.append(callback)
    
    def get_opportunities(self) -> List[MarketOpportunity]:
        """获取当前机会列表"""
        return self._opportunities.copy()
    
    def get_insights(self) -> Dict[str, MarketInsight]:
        """获取市场洞察"""
        return self._insights.copy()
    
    def get_market_state(self) -> Dict[str, str]:
        """获取市场状态"""
        return self._market_state.copy()
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self._stats.copy()


class ProactiveInformationCollector:
    """主动性信息收集器"""
    
    def __init__(self, main_controller=None, config: Optional[Dict] = None):
        self.main_controller = main_controller
        self.config = config or {}
        
        self._running = False
        self._collect_interval = self.config.get("collect_interval", 300)
        
        self._news_cache: List[Dict] = []
        self._social_sentiment: Dict[str, float] = {}
        self._onchain_data: Dict[str, Dict] = {}
        self._fear_greed_index: Optional[float] = None
    
    async def initialize(self) -> bool:
        """初始化"""
        logger.info("📡 初始化主动性信息收集器...")
        return True
    
    async def start(self) -> None:
        """启动"""
        self._running = True
        logger.info("📡 启动主动性信息收集...")
        
        asyncio.create_task(self._collection_loop())
    
    async def stop(self) -> None:
        """停止"""
        self._running = False
    
    async def _collection_loop(self) -> None:
        """信息收集循环"""
        while self._running:
            try:
                await self._collect_news()
                await self._collect_social_sentiment()
                await self._collect_onchain_data()
                await self._collect_fear_greed_index()
                
                await self._analyze_collected_data()
                
                await asyncio.sleep(self._collect_interval)
                
            except Exception as e:
                logger.error(f"信息收集循环错误: {e}")
                await asyncio.sleep(SLEEP_60S)
    
    async def _collect_news(self) -> None:
        """收集新闻"""
        if not self.main_controller:
            return
        
        try:
            data_integration = (
                self.main_controller.get_data_integration()
                if hasattr(self.main_controller, "get_data_integration")
                else getattr(self.main_controller, "data_integration", None)
            )
            if data_integration and hasattr(data_integration, 'get_crypto_news'):
                news = await data_integration.get_crypto_news(limit=10)
                if news:
                    self._news_cache = news
                    logger.debug(f"📰 收集到 {len(news)} 条新闻")
        except Exception as e:
            logger.debug(f"收集新闻失败: {e}")
    
    async def _collect_social_sentiment(self) -> None:
        """收集社交媒体情绪"""
        try:
            if self.main_controller:
                third_party = (
                    self.main_controller.get_third_party_data_integrator()
                    if hasattr(self.main_controller, "get_third_party_data_integrator")
                    else getattr(self.main_controller, "third_party_data_integrator", None)
                )
                if third_party and hasattr(third_party, 'get_social_sentiment'):
                    symbols = ["BTC", "ETH", "SOL"]
                    for symbol in symbols:
                        sentiment = await third_party.get_social_sentiment(symbol)
                        if sentiment:
                            self._social_sentiment[symbol] = sentiment
        except Exception as e:
            logger.debug(f"收集社交情绪失败: {e}")
    
    async def _collect_onchain_data(self) -> None:
        """收集链上数据"""
        try:
            if self.main_controller:
                onchain = (
                    self.main_controller.get_onchain_integrator()
                    if hasattr(self.main_controller, "get_onchain_integrator")
                    else getattr(self.main_controller, "onchain_integrator", None)
                )
                if onchain and hasattr(onchain, 'get_onchain_metrics'):
                    metrics = await onchain.get_onchain_metrics()
                    if metrics:
                        self._onchain_data = metrics
        except Exception as e:
            logger.debug(f"收集链上数据失败: {e}")
    
    async def _collect_fear_greed_index(self) -> None:
        """收集恐慌贪婪指数"""
        try:
            if self.main_controller:
                third_party = getattr(self.main_controller, 'third_party_data_integrator', None)
                if third_party and hasattr(third_party, 'get_fear_greed_index'):
                    index = await third_party.get_fear_greed_index()
                    coerced = _coerce_fear_greed_index(index)
                    if coerced is not None:
                        self._fear_greed_index = coerced
                        logger.info(f"😰 恐慌贪婪指数: {coerced}")
                    elif index not in (None, 0, 0.0, False, ""):
                        logger.debug(
                            "恐慌贪婪指数无法解析为数值，已忽略 raw_type=%s",
                            type(index).__name__,
                        )
        except Exception as e:
            logger.debug(f"收集恐慌贪婪指数失败: {e}")
    
    async def _analyze_collected_data(self) -> None:
        """分析收集的数据"""
        if self._news_cache:
            important_news = [n for n in self._news_cache if n.get('importance', 0) > 0.7]
            if important_news:
                logger.info(f"📰 发现 {len(important_news)} 条重要新闻")
        
        fg = self._fear_greed_index
        if fg is not None:
            if fg < 25:
                logger.info("😰 市场极度恐慌，可能是买入机会")
            elif fg > 75:
                logger.info("🤑 市场极度贪婪，注意风险")
    
    def get_latest_news(self) -> List[Dict]:
        """获取最新新闻"""
        return self._news_cache.copy()
    
    def get_social_sentiment(self) -> Dict[str, float]:
        """获取社交情绪"""
        return self._social_sentiment.copy()
    
    def get_onchain_data(self) -> Dict[str, Dict]:
        """获取链上数据"""
        return self._onchain_data.copy()
    
    def get_fear_greed_index(self) -> Optional[float]:
        """获取恐慌贪婪指数"""
        return self._fear_greed_index


class ProactiveStrategySelector:
    """主动性策略选择器"""
    
    def __init__(self, main_controller=None, config: Optional[Dict] = None):
        self.main_controller = main_controller
        self.config = config or {}
        
        self._running = False
        self._strategy_scores: Dict[str, float] = {}
        self._best_strategy: Optional[str] = None
    
    async def initialize(self) -> bool:
        """初始化"""
        logger.info("🎯 初始化主动性策略选择器...")
        return True
    
    async def start(self) -> None:
        """启动"""
        self._running = True
        logger.info("🎯 启动主动性策略选择...")
        
        asyncio.create_task(self._strategy_evaluation_loop())
    
    async def stop(self) -> None:
        """停止"""
        self._running = False
    
    async def _strategy_evaluation_loop(self) -> None:
        """策略评估循环"""
        while self._running:
            try:
                await self._evaluate_all_strategies()
                
                await self._select_best_strategy()
                
                await asyncio.sleep(SLEEP_5MIN)
                
            except Exception as e:
                logger.error(f"策略评估循环错误: {e}")
                await asyncio.sleep(SLEEP_60S)
    
    async def _evaluate_all_strategies(self) -> None:
        """评估所有策略"""
        if not self.main_controller:
            return
        
        strategy_manager = getattr(self.main_controller, 'strategy_manager', None)
        if not strategy_manager:
            return
        
        try:
            strategies = getattr(strategy_manager, 'strategy_configs', {})
            
            for strategy_id, config in strategies.items():
                score = await self._evaluate_strategy(strategy_id, config)
                self._strategy_scores[strategy_id] = score
                logger.debug(f"策略 {strategy_id} 评分: {score:.2f}")
                
        except Exception as e:
            logger.error(f"评估策略失败: {e}")
    
    async def _evaluate_strategy(self, strategy_id: str, config: Any) -> float:
        """评估单个策略"""
        score = 0.5
        
        try:
            if hasattr(config, 'win_rate'):
                score += config.win_rate * 0.3
            
            if hasattr(config, 'total_return'):
                score += min(0.2, config.total_return * 0.1)
            
            if hasattr(config, 'sharpe_ratio'):
                score += min(0.1, config.sharpe_ratio * 0.02)
            
        except Exception as e:
            logger.debug(f"读取策略指标失败 {strategy_id}: {e}")
        
        return min(1.0, max(0.0, score))
    
    async def _select_best_strategy(self) -> None:
        """选择最佳策略"""
        if not self._strategy_scores:
            return
        
        best = max(self._strategy_scores.items(), key=lambda x: x[1])
        
        if best[1] >= 0.6:
            self._best_strategy = best[0]
            logger.info(f"🎯 当前最佳策略: {best[0]} (评分: {best[1]:.2f})")
    
    def get_best_strategy(self) -> Optional[str]:
        """获取最佳策略"""
        return self._best_strategy
    
    def get_strategy_scores(self) -> Dict[str, float]:
        """获取策略评分"""
        return self._strategy_scores.copy()


class ProactiveActionTrigger:
    """主动性行动触发器"""
    
    def __init__(self, main_controller=None, config: Optional[Dict] = None):
        self.main_controller = main_controller
        self.config = config or {}
        
        self._running = False
        self._action_queue: List[Dict] = []
        self._last_action_time: Dict[str, datetime] = {}
        self._action_cooldown = self.config.get("action_cooldown", 60)
        notif_cfg = self.config.get("notifications", {}) if isinstance(self.config.get("notifications", {}), dict) else {}
        self._opportunity_notification_enabled = bool(notif_cfg.get("opportunity_enabled", False))
        self._opportunity_min_confidence = float(notif_cfg.get("opportunity_min_confidence", 0.85))
        self._opportunity_min_priority = int(notif_cfg.get("opportunity_min_priority", 7))
        self._opportunity_min_risk_reward = float(notif_cfg.get("opportunity_min_risk_reward", 1.5))
        self._opportunity_require_trend_alignment = bool(notif_cfg.get("opportunity_require_trend_alignment", True))
        self._opportunity_trend_strength_threshold = float(notif_cfg.get("opportunity_trend_strength_threshold", 0.05))
        self._opportunity_notification_cooldown = int(notif_cfg.get("opportunity_cooldown_sec", 3600))

    def _reload_opportunity_notification_config(self) -> None:
        """Load latest opportunity gates from ConfigManager snapshot if available."""
        if not self.main_controller:
            return
        config_manager = getattr(self.main_controller, "config_manager", None)
        if config_manager is None:
            return
        try:
            notif_cfg = config_manager.get_config_path_sync("proactive_ai.notifications", {})
            if not isinstance(notif_cfg, dict):
                return
            self._opportunity_notification_enabled = bool(
                notif_cfg.get("opportunity_enabled", self._opportunity_notification_enabled)
            )
            self._opportunity_min_confidence = float(
                notif_cfg.get("opportunity_min_confidence", self._opportunity_min_confidence)
            )
            self._opportunity_min_priority = int(
                notif_cfg.get("opportunity_min_priority", self._opportunity_min_priority)
            )
            self._opportunity_min_risk_reward = float(
                notif_cfg.get("opportunity_min_risk_reward", self._opportunity_min_risk_reward)
            )
            self._opportunity_require_trend_alignment = bool(
                notif_cfg.get("opportunity_require_trend_alignment", self._opportunity_require_trend_alignment)
            )
            self._opportunity_trend_strength_threshold = float(
                notif_cfg.get("opportunity_trend_strength_threshold", self._opportunity_trend_strength_threshold)
            )
            self._opportunity_notification_cooldown = int(
                notif_cfg.get("opportunity_cooldown_sec", self._opportunity_notification_cooldown)
            )
        except Exception as e:
            logger.debug(f"刷新机会通知阈值失败，使用现有配置: {e}")
    
    async def initialize(self) -> bool:
        """初始化"""
        logger.info("⚡ 初始化主动性行动触发器...")
        return True
    
    async def start(self) -> None:
        """启动"""
        self._running = True
        logger.info("⚡ 启动主动性行动触发...")
        
        asyncio.create_task(self._action_execution_loop())
    
    async def stop(self) -> None:
        """停止"""
        self._running = False
    
    def queue_action(self, action: Dict) -> None:
        """添加行动到队列"""
        action_type = action.get('type', 'unknown')

        if action_type == "send_notification" and action.get("kind") == "opportunity":
            self._reload_opportunity_notification_config()
            if not self._opportunity_notification_enabled:
                logger.debug("机会通知已禁用，跳过")
                return
            confidence = float(action.get("confidence", 0.0) or 0.0)
            if confidence < self._opportunity_min_confidence:
                logger.debug(f"机会通知置信度不足({confidence:.2f}<{self._opportunity_min_confidence:.2f})，跳过")
                return
            priority = int(action.get("priority_score", 0) or 0)
            if priority < self._opportunity_min_priority:
                logger.debug(f"机会通知优先级不足({priority}<{self._opportunity_min_priority})，跳过")
                return
            rr = float(action.get("risk_reward", 0.0) or 0.0)
            if rr < self._opportunity_min_risk_reward:
                logger.debug(f"机会通知盈亏比不足({rr:.2f}<{self._opportunity_min_risk_reward:.2f})，跳过")
                return
            if self._opportunity_require_trend_alignment:
                trend = str(action.get("trend", "unknown")).lower()
                trend_strength = float(action.get("trend_strength", 0.0) or 0.0)
                direction = str(action.get("direction", "")).lower()
                if trend in {"bullish", "bearish"} and trend_strength >= self._opportunity_trend_strength_threshold:
                    if direction == "long" and trend == "bearish":
                        logger.debug("机会通知趋势冲突（long vs bearish），跳过")
                        return
                    if direction == "short" and trend == "bullish":
                        logger.debug("机会通知趋势冲突（short vs bullish），跳过")
                        return
            cooldown_key = str(action.get("cooldown_key") or "send_notification:opportunity")
            if cooldown_key in self._last_action_time:
                elapsed = (datetime.now() - self._last_action_time[cooldown_key]).total_seconds()
                if elapsed < self._opportunity_notification_cooldown:
                    logger.debug(f"机会通知冷却中({cooldown_key})，跳过")
                    return
            action["_cooldown_key"] = cooldown_key
        else:
            if action_type in self._last_action_time:
                elapsed = (datetime.now() - self._last_action_time[action_type]).total_seconds()
                if elapsed < self._action_cooldown:
                    logger.debug(f"行动 {action_type} 冷却中，跳过")
                    return
        
        self._action_queue.append(action)
        logger.info(f"📥 行动已加入队列: {action_type}")
    
    async def _action_execution_loop(self) -> None:
        """行动执行循环"""
        while self._running:
            try:
                if self._action_queue:
                    action = self._action_queue.pop(0)
                    await self._execute_action(action)
                
                await asyncio.sleep(SLEEP_1S)
                
            except Exception as e:
                logger.error(f"行动执行循环错误: {e}")
                await asyncio.sleep(SLEEP_5S)
    
    async def _execute_action(self, action: Dict) -> bool:
        """执行行动"""
        action_type = action.get('type')
        
        try:
            if action_type == 'open_position':
                return await self._execute_open_position(action)
            elif action_type == 'close_position':
                return await self._execute_close_position(action)
            elif action_type == 'adjust_stop_loss':
                return await self._execute_adjust_stop_loss(action)
            elif action_type == 'send_notification':
                return await self._execute_send_notification(action)
            else:
                logger.warning(f"未知行动类型: {action_type}")
                return False
                
        except Exception as e:
            logger.error(f"执行行动失败: {e}")
            return False
        finally:
            cooldown_key = action.get("_cooldown_key") if isinstance(action, dict) else None
            self._last_action_time[str(cooldown_key or action_type)] = datetime.now()
    
    async def _execute_open_position(self, action: Dict) -> bool:
        """执行开仓"""
        if not self.main_controller:
            return False
        
        engine = getattr(self.main_controller, 'ai_trading_engine', None)
        if not engine:
            return False
        
        try:
            result = await engine.execute_trade(
                symbol=action.get('symbol'),
                side=action.get('side'),
                quantity=action.get('quantity'),
                stop_loss=action.get('stop_loss'),
                take_profit=action.get('take_profit'),
                reasoning=action.get('reasoning', '主动性触发')
            )
            return result is not None
        except Exception as e:
            logger.error(f"开仓执行失败: {e}")
            return False
    
    async def _execute_close_position(self, action: Dict) -> bool:
        """执行平仓（S1：ExecutionGateway，source=system）"""
        if not self.main_controller:
            return False

        gw = getattr(self.main_controller, "execution_gateway", None)
        if not gw:
            exchange = getattr(self.main_controller, "okx_exchange", None) or getattr(
                self.main_controller, "exchange", None
            )
            if not exchange:
                return False
            try:
                res = await exchange.close_position(
                    action.get("symbol"),
                    action.get("side", "long"),
                )
                return bool(res.get("success") if isinstance(res, dict) else res)
            except Exception as e:
                logger.error("平仓执行失败: %s", e)
                return False

        try:
            res = await gw.close_swap(
                action.get("symbol"),
                str(action.get("side", "long")).lower(),
                None,
                "system",
                "proactive_ai_close",
            )
            return bool(isinstance(res, dict) and res.get("success"))
        except Exception as e:
            logger.error(f"平仓执行失败: {e}")
            return False
    
    async def _execute_adjust_stop_loss(self, action: Dict) -> bool:
        """执行调整止损"""
        logger.info(f"调整止损: {action.get('symbol')} -> {action.get('new_stop_loss')}")
        return True
    
    async def _execute_send_notification(self, action: Dict) -> bool:
        """执行发送通知"""
        if not self.main_controller:
            return False

        try:
            title = action.get("title", "系统通知")
            message = action.get("message", "")
            priority = action.get("priority", "low")
            if hasattr(self.main_controller, "_send_notification_handler"):
                await self.main_controller._send_notification_handler(title, message, priority)
            else:
                telegram = getattr(self.main_controller, 'telegram_bot', None)
                if not telegram:
                    return False
                await telegram.send_message(message)
            return True
        except Exception as e:
            logger.error(f"发送通知失败: {e}")
            return False


class ProactiveAIOrchestrator:
    """主动性AI协调器 - 统一管理所有主动性模块"""
    
    def __init__(self, main_controller=None, config: Optional[Dict] = None, config_manager=None):
        self.main_controller = main_controller
        if config_manager is None and main_controller is not None:
            config_manager = getattr(main_controller, "config_manager", None)
        self.config = resolve_module_config(
            config=config,
            config_manager=config_manager,
            section="proactive_ai",
            defaults={},
        )
        
        self.market_scanner = ProactiveMarketScanner(main_controller, self.config)
        self.info_collector = ProactiveInformationCollector(main_controller, self.config)
        self.strategy_selector = ProactiveStrategySelector(main_controller, self.config)
        self.action_trigger = ProactiveActionTrigger(main_controller, self.config)
        
        self._running = False
        self._initialized = False
    
    async def initialize(self) -> bool:
        """初始化所有主动性模块"""
        logger.info("🚀 初始化主动性AI系统...")
        
        results = await asyncio.gather(
            self.market_scanner.initialize(),
            self.info_collector.initialize(),
            self.strategy_selector.initialize(),
            self.action_trigger.initialize(),
            return_exceptions=True
        )
        
        self._initialized = all(r is True for r in results if isinstance(r, bool))
        
        self._setup_internal_callbacks()
        
        logger.info(f"✅ 主动性AI系统初始化{'成功' if self._initialized else '部分失败'}")
        return self._initialized
    
    def _setup_internal_callbacks(self) -> None:
        """设置内部回调"""
        async def on_opportunity(opportunity):
            # enrich with trend context and risk/reward score
            trend = "unknown"
            trend_strength = 0.0
            try:
                insight = self.market_scanner.get_insights().get(opportunity.symbol)
                if insight:
                    trend = str(getattr(insight, "trend", "unknown"))
                    trend_strength = float(getattr(insight, "trend_strength", 0.0) or 0.0)
            except Exception:
                pass
            rr = 0.0
            try:
                entry = float(getattr(opportunity, "entry_price", 0.0) or 0.0)
                sl = float(getattr(opportunity, "stop_loss", 0.0) or 0.0)
                tp = float(getattr(opportunity, "take_profit", 0.0) or 0.0)
                if entry > 0:
                    if str(getattr(opportunity, "direction", "")).lower() == "long":
                        risk = max(entry - sl, 1e-9)
                        reward = max(tp - entry, 0.0)
                    else:
                        risk = max(sl - entry, 1e-9)
                        reward = max(entry - tp, 0.0)
                    rr = reward / risk if risk > 0 else 0.0
            except Exception:
                rr = 0.0
            self.action_trigger.queue_action({
                'type': 'send_notification',
                'kind': 'opportunity',
                'title': "机会提示",
                'priority': "low",
                'confidence': float(getattr(opportunity, "confidence", 0.0) or 0.0),
                'priority_score': int(getattr(opportunity, "priority", 0) or 0),
                'risk_reward': float(rr),
                'trend': trend,
                'trend_strength': float(trend_strength),
                'direction': str(getattr(opportunity, "direction", "")),
                'cooldown_key': f"opportunity:{opportunity.symbol}:{opportunity.direction}",
                'message': (
                    f"🎯 发现机会: {opportunity.symbol} {self.market_scanner._zh_direction(opportunity.direction)}\n"
                    f"置信度: {float(getattr(opportunity, 'confidence', 0.0) or 0.0):.0%} | "
                    f"优先级: {int(getattr(opportunity, 'priority', 0) or 0)} | "
                    f"盈亏比: {rr:.2f} | 趋势: {self.market_scanner._zh_trend(trend)}/{trend_strength:.2%}\n\n"
                    f"{opportunity.reasoning}"
                ),
            })
        
        self.market_scanner.add_alert_callback(on_opportunity)
    
    async def start(self) -> None:
        """启动所有主动性模块"""
        if self._running:
            return
        
        self._running = True
        logger.info("🚀 启动主动性AI系统...")
        
        await asyncio.gather(
            self.market_scanner.start(),
            self.info_collector.start(),
            self.strategy_selector.start(),
            self.action_trigger.start()
        )
        
        logger.info("✅ 主动性AI系统已启动")
    
    async def stop(self) -> None:
        """停止所有主动性模块"""
        self._running = False
        
        await asyncio.gather(
            self.market_scanner.stop(),
            self.info_collector.stop(),
            self.strategy_selector.stop(),
            self.action_trigger.stop()
        )
        
        logger.info("🛑 主动性AI系统已停止")
    
    def get_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        return {
            "running": self._running,
            "initialized": self._initialized,
            "market_scanner": {
                "opportunities": len(self.market_scanner.get_opportunities()),
                "insights": len(self.market_scanner.get_insights()),
                "market_state": self.market_scanner.get_market_state(),
                "stats": self.market_scanner.get_stats()
            },
            "info_collector": {
                "news_count": len(self.info_collector.get_latest_news()),
                "social_sentiment": self.info_collector.get_social_sentiment(),
                "fear_greed_index": self.info_collector.get_fear_greed_index()
            },
            "strategy_selector": {
                "best_strategy": self.strategy_selector.get_best_strategy(),
                "strategy_scores": self.strategy_selector.get_strategy_scores()
            },
            "action_trigger": {
                "queued_actions": len(self.action_trigger._action_queue)
            }
        }
