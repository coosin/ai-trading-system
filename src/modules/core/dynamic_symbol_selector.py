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
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import random

logger = logging.getLogger(__name__)

DEFAULT_OKX_WS_TICKER_INSTIDS = (
    "BTC-USDT-SWAP,ETH-USDT-SWAP,SOL-USDT-SWAP,BNB-USDT-SWAP,"
    "XRP-USDT-SWAP,DOGE-USDT-SWAP,ADA-USDT-SWAP,AVAX-USDT-SWAP,"
    "DOT-USDT-SWAP,LINK-USDT-SWAP,ATOM-USDT-SWAP"
)


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
    discovery_probe_limit: int = 32         # 每轮最多探测多少个候选
    discovery_concurrency: int = 8          # 并发探测 ticker 数
    discovery_ticker_timeout_s: float = 4.0 # 单个 ticker 探测超时
    selection_concurrency: int = 4          # 并发评估 symbol 数
    selection_eval_timeout_s: float = 8.0   # 单个 symbol 评估超时
    startup_warmup_sec: float = 8.0         # 冷启动等待交易所/WS 缓存预热
    always_include: List[str] = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    always_exclude: List[str] = field(default_factory=list)
    # symbol_universe=full_exchange：全所 USDT 永续候选；restricted 时仅保留 allowed_symbols
    restricted_universe: bool = False
    allowed_symbols: List[str] = field(default_factory=list)
    preferred_symbols_only: bool = True      # 默认仅在主流高流动候选池中选币
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
            "selection_rounds": 0,
            "empty_discovery_fallbacks": 0,
            "last_empty_discovery_at": None,
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
        
        discovered: List[str] = []
        
        try:
            markets = await self._fetch_markets_compat()
            candidates: List[str] = []
            for market in markets:
                symbol = market.get("symbol", "")

                normalized_symbol = self._normalize_candidate_symbol(symbol)
                if not normalized_symbol:
                    continue

                if normalized_symbol in self.config.always_exclude or symbol in self.config.always_exclude:
                    continue
                
                # Some exchange connectors do not reliably tag market "type".
                # Treat missing/unknown types as eligible (we still filter by liquidity/volume later).
                mtype = str(market.get("type") or "").lower()
                if mtype and mtype not in ["swap", "future"]:
                    continue

                if normalized_symbol not in candidates:
                    candidates.append(normalized_symbol)

            if self.config.restricted_universe and self.config.allowed_symbols:
                allow = {str(s).strip() for s in self.config.allowed_symbols if s}
                candidates = [s for s in candidates if s in allow]

            preferred_symbols = []
            if self.config.always_include:
                preferred_symbols.extend([s for s in self.config.always_include if s in candidates])
            preferred_symbols.extend([s for s in self._preferred_candidates_from_exchange() if s in candidates])
            preferred: List[str] = []
            for sym in preferred_symbols:
                if sym not in preferred:
                    preferred.append(sym)
            remainder = [s for s in candidates if s not in preferred]
            if preferred and self.config.preferred_symbols_only and not self.config.restricted_universe:
                candidates = list(preferred)
            else:
                candidates = preferred + remainder

            probe_limit = max(
                int(self.config.min_symbols or 1),
                int(self.config.discovery_probe_limit or 32),
            )
            candidates = candidates[:probe_limit]

            sem = asyncio.Semaphore(max(1, int(self.config.discovery_concurrency or 8)))

            async def _probe(sym: str) -> Optional[str]:
                try:
                    async with sem:
                        ticker = await asyncio.wait_for(
                            self._fetch_ticker_compat(sym),
                            timeout=float(self.config.discovery_ticker_timeout_s or 4.0),
                        )
                    volume_24h = float((ticker or {}).get("quoteVolume", 0) or 0)
                    if volume_24h >= self.config.min_24h_volume:
                        return sym
                except Exception:
                    return None
                return None

            if candidates:
                rows = await asyncio.gather(*[_probe(sym) for sym in candidates], return_exceptions=False)
                discovered = [sym for sym in rows if sym]
            
            self._stats["total_discovered"] = len(discovered)
            logger.info(f"发现 {len(discovered)} 个可交易币种")
            
        except Exception as e:
            logger.error(f"发现币种失败: {e}")
            return self.config.always_include

        # IMPORTANT: discovery may legitimately return 0 (API timeout/limited markets).
        # Never let this empty result wipe the monitoring universe.
        if not discovered:
            self._stats["empty_discovery_fallbacks"] = int(
                self._stats.get("empty_discovery_fallbacks", 0)
            ) + 1
            self._stats["last_empty_discovery_at"] = datetime.now().isoformat()
            logger.warning(
                "动态选币发现结果为空，回退到 always_include: %s",
                self.config.always_include,
            )
            return list(self.config.always_include)

        return discovered

    def _normalize_candidate_symbol(self, symbol: Any) -> str:
        s = str(symbol or "").strip()
        if not s:
            return ""
        s = s.replace("-", "/")
        up = s.upper()
        if up.endswith("/USDT/SWAP"):
            return s[: -len("/SWAP")]
        if up.endswith("/USDT"):
            return s
        return ""

    def _preferred_candidates_from_exchange(self) -> List[str]:
        raw = str(os.getenv("OPENCLAW_OKX_WS_TICKER_INSTIDS", DEFAULT_OKX_WS_TICKER_INSTIDS) or "").strip()
        if not raw:
            return []
        out: List[str] = []
        for inst_id in raw.split(","):
            s = self._normalize_candidate_symbol(inst_id.strip())
            if s and s not in out:
                out.append(s)
        return out
    
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
            ticker = await self._fetch_ticker_compat(symbol)
            ohlcv = await self._fetch_ohlcv_compat(symbol, "1h", limit=24)
            
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

    async def _fetch_markets_compat(self) -> List[Dict[str, Any]]:
        """
        兼容不同交易所接口：
        - 优先 ccxt 风格 fetch_markets
        - 回退到 get_exchange_info.supported_symbols
        """
        if not self._exchange:
            return []

        fetch_markets = getattr(self._exchange, "fetch_markets", None)
        if callable(fetch_markets):
            try:
                rows = fetch_markets()
                rows = await rows if asyncio.iscoroutine(rows) or hasattr(rows, "__await__") else rows
                if isinstance(rows, list):
                    out: List[Dict[str, Any]] = []
                    for m in rows:
                        if isinstance(m, dict):
                            sym = str(m.get("symbol", "") or "")
                            if not sym:
                                continue
                            mtype = str(m.get("type", "") or "").lower()
                            if not mtype:
                                if sym.endswith("/SWAP"):
                                    mtype = "swap"
                                elif sym.endswith("/USDT"):
                                    mtype = "spot"
                            out.append({"symbol": sym, "type": mtype})
                    if out:
                        return out
            except Exception as e:
                logger.debug(f"fetch_markets 调用失败，回退 exchange_info: {e}")

        get_exchange_info = getattr(self._exchange, "get_exchange_info", None)
        if callable(get_exchange_info):
            try:
                info = get_exchange_info()
                info = await info if asyncio.iscoroutine(info) or hasattr(info, "__await__") else info
                supported = getattr(info, "supported_symbols", None)
                if not isinstance(supported, list) and isinstance(info, dict):
                    supported = info.get("supported_symbols", [])
                out = []
                for sym in supported or []:
                    s = str(sym or "").replace("-", "/")
                    if not s:
                        continue
                    s_up = s.upper()
                    mtype = "swap" if s_up.endswith("/SWAP") else "spot"
                    out.append({"symbol": s, "type": mtype})
                return out
            except Exception as e:
                logger.debug(f"get_exchange_info 回退失败: {e}")
        return []

    async def _fetch_ticker_compat(self, symbol: str) -> Dict[str, Any]:
        """
        兼容 ccxt 与项目内 exchange 封装的 ticker 字段。
        返回统一字段: bid/ask/last/quoteVolume
        """
        if not self._exchange:
            return {}

        for name in ("fetch_ticker", "get_ticker"):
            fn = getattr(self._exchange, name, None)
            if not callable(fn):
                continue
            try:
                data = fn(symbol)
                data = await data if asyncio.iscoroutine(data) or hasattr(data, "__await__") else data
                if not isinstance(data, dict):
                    continue
                last = data.get("last") or data.get("close") or data.get("price") or 0
                bid = data.get("bid") or 0
                ask = data.get("ask") or 0
                quote_vol = (
                    data.get("quoteVolume")
                    or data.get("quote_volume")
                    or data.get("volCcy24h")
                    or data.get("baseVolume", 0) * (float(last or 0) if last else 0)
                    or data.get("volume", 0) * (float(last or 0) if last else 0)
                    or 0
                )
                if float(last or 0) <= 0 and float(quote_vol or 0) <= 0:
                    continue
                return {
                    "last": float(last or 0),
                    "bid": float(bid or 0),
                    "ask": float(ask or 0),
                    "quoteVolume": float(quote_vol or 0),
                }
            except Exception as e:
                logger.debug(f"{name}({symbol}) 失败: {e}")

        # OKX WS-only 模式冷启动时 get_ticker() 可能因缓存未热而返回空；
        # 这里直接走一次 REST ticker 兜底，避免 discovery 首轮全量判空。
        make_request = getattr(self._exchange, "_make_request", None)
        to_inst_id = getattr(self._exchange, "_to_okx_inst_id", None)
        if callable(make_request) and callable(to_inst_id):
            try:
                inst_id = to_inst_id(symbol, default_type="SWAP")
                rows = await make_request("GET", "/api/v5/market/ticker", {"instId": inst_id})
                if isinstance(rows, list) and rows:
                    row = rows[0] if isinstance(rows[0], dict) else {}
                    last = float(row.get("last", 0) or 0)
                    bid = float(row.get("bidPx", 0) or 0)
                    ask = float(row.get("askPx", 0) or 0)
                    quote_vol = float(row.get("volCcy24h", 0) or 0)
                    if quote_vol <= 0:
                        quote_vol = float(row.get("vol24h", 0) or 0) * max(last, 0.0)
                    return {
                        "last": last,
                        "bid": bid,
                        "ask": ask,
                        "quoteVolume": float(quote_vol or 0),
                    }
            except Exception as e:
                logger.debug(f"okx_rest_ticker_fallback({symbol}) 失败: {e}")
        return {}

    async def _fetch_ohlcv_compat(self, symbol: str, timeframe: str, limit: int = 24) -> List[List[float]]:
        """
        兼容 ccxt 风格 fetch_ohlcv 与项目封装 get_klines。
        返回 [[ts,o,h,l,c,v], ...]
        """
        if not self._exchange:
            return []

        fetch_ohlcv = getattr(self._exchange, "fetch_ohlcv", None)
        if callable(fetch_ohlcv):
            try:
                rows = fetch_ohlcv(symbol, timeframe, limit=limit)
                rows = await rows if asyncio.iscoroutine(rows) or hasattr(rows, "__await__") else rows
                if isinstance(rows, list):
                    return rows
            except Exception as e:
                logger.debug(f"fetch_ohlcv({symbol}) 失败: {e}")

        get_klines = getattr(self._exchange, "get_klines", None)
        if callable(get_klines):
            try:
                tf = str(timeframe).replace("h", "H")
                rows = get_klines(symbol.replace("/", "-"), tf, limit=limit)
                rows = await rows if asyncio.iscoroutine(rows) or hasattr(rows, "__await__") else rows
                if isinstance(rows, list):
                    out: List[List[float]] = []
                    for r in rows:
                        if isinstance(r, (list, tuple)) and len(r) >= 6:
                            out.append([float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])])
                        elif isinstance(r, dict):
                            ts = r.get("ts") or r.get("timestamp") or r.get("t") or 0
                            o = r.get("open", 0)
                            h = r.get("high", 0)
                            l = r.get("low", 0)
                            c = r.get("close", 0)
                            v = r.get("volume", 0)
                            out.append([float(ts), float(o), float(h), float(l), float(c), float(v)])
                    return out
            except Exception as e:
                logger.debug(f"get_klines({symbol}) 失败: {e}")
        return []
    
    async def select_best_symbols(self, candidates: List[str]) -> List[str]:
        """
        选择最佳币种
        
        Args:
            candidates: 候选币种列表
        
        Returns:
            最佳币种列表
        """
        scores = []
        sem = asyncio.Semaphore(max(1, int(self.config.selection_concurrency or 4)))

        async def _eval(symbol: str) -> Optional[SymbolScore]:
            try:
                async with sem:
                    return await asyncio.wait_for(
                        self.evaluate_symbol(symbol),
                        timeout=float(self.config.selection_eval_timeout_s or 8.0),
                    )
            except Exception:
                return None

        rows = await asyncio.gather(*[_eval(symbol) for symbol in candidates], return_exceptions=False)
        for score in rows:
            if isinstance(score, SymbolScore) and score.comprehensive_score > 0:
                scores.append(score)
                self.symbol_scores[score.symbol] = score
        
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
        candidates = list(self.candidate_symbols or [])
        if not candidates:
            candidates = await self.discover_symbols()
        self.candidate_symbols = candidates
        
        best_symbols = await self.select_best_symbols(candidates)

        # Never overwrite current_symbols with empty selection.
        if not best_symbols:
            best_symbols = list(self.current_symbols or self.config.always_include)
        
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
        first_round = True
        while self._running:
            try:
                if first_round and float(self.config.startup_warmup_sec or 0) > 0:
                    await asyncio.sleep(float(self.config.startup_warmup_sec))
                    first_round = False
                await self.update_selection()
                await asyncio.sleep(self.config.selection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"选择循环错误: {e}")
                await asyncio.sleep(60)
    
    async def _discovery_loop(self):
        """发现循环"""
        first_round = True
        while self._running:
            try:
                if first_round and float(self.config.startup_warmup_sec or 0) > 0:
                    await asyncio.sleep(float(self.config.startup_warmup_sec))
                    first_round = False
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
