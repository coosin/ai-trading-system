"""
止盈止损管理系统

功能：
1. 固定止盈止损 - 设置固定的止盈止损价格
2. 移动止盈止损 - 追踪止损，锁定利润
3. 分批止盈 - 分阶段止盈
4. ATR动态止损 - 基于波动率调整止损
5. 时间止损 - 超时自动平仓
"""

import asyncio
import logging
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Tuple
from enum import Enum
from pathlib import Path
import math

logger = logging.getLogger(__name__)


class StopType(Enum):
    """止损类型"""
    FIXED = "fixed"                 # 固定止损
    TRAILING = "trailing"           # 移动止损
    ATR_BASED = "atr_based"         # ATR动态止损
    TIME_BASED = "time_based"       # 时间止损
    PERCENTAGE = "percentage"       # 百分比止损


class TakeProfitType(Enum):
    """止盈类型"""
    FIXED = "fixed"                 # 固定止盈
    TRAILING = "trailing"           # 移动止盈
    PARTIAL = "partial"             # 分批止盈
    PERCENTAGE = "percentage"       # 百分比止盈


class StopLossTakeProfitStatus(Enum):
    """止盈止损状态"""
    ACTIVE = "active"               # 激活中
    TRIGGERED = "triggered"         # 已触发
    CANCELLED = "cancelled"         # 已取消
    MODIFIED = "modified"           # 已修改


@dataclass
class StopLossConfig:
    """止损配置"""
    stop_type: StopType = StopType.PERCENTAGE
    stop_value: float = 0.03        # 止损值（百分比或固定价格）
    trailing_offset: float = 0.02   # 移动止损偏移量
    atr_multiplier: float = 2.0     # ATR倍数
    time_limit_hours: int = 0       # 时间限制（小时），0表示无限制
    enable_breakeven: bool = True   # 启用保本止损
    breakeven_trigger: float = 0.02 # 触发保本的盈利比例


@dataclass
class TakeProfitConfig:
    """止盈配置"""
    tp_type: TakeProfitType = TakeProfitType.PERCENTAGE
    tp_value: float = 0.06          # 止盈值（百分比或固定价格）
    trailing_offset: float = 0.03   # 移动止盈偏移量
    partial_levels: List[Tuple[float, float]] = field(default_factory=lambda: [
        (0.03, 0.3),   # 盈利3%时平仓30%
        (0.06, 0.4),   # 盈利6%时平仓40%
        (0.10, 0.3),   # 盈利10%时平仓30%
    ])
    enable_trailing: bool = False   # 启用移动止盈
    trailing_trigger: float = 0.04  # 触发移动止盈的盈利比例


@dataclass
class StopLossTakeProfitOrder:
    """止盈止损订单"""
    order_id: str
    symbol: str
    side: str                       # long/short
    entry_price: float
    quantity: float
    remaining_quantity: float
    
    stop_loss_price: Optional[float] = None
    stop_loss_type: StopType = StopType.PERCENTAGE
    stop_loss_value: float = 0.03
    
    take_profit_price: Optional[float] = None
    take_profit_type: TakeProfitType = TakeProfitType.PERCENTAGE
    take_profit_value: float = 0.06
    
    trailing_stop_activated: bool = False
    trailing_stop_offset: float = 0.02
    highest_price: float = 0.0      # 多单最高价
    lowest_price: float = 0.0       # 空单最低价
    
    breakeven_activated: bool = False
    breakeven_price: Optional[float] = None
    
    partial_tp_executed: List[Tuple[float, float]] = field(default_factory=list)
    
    status: StopLossTakeProfitStatus = StopLossTakeProfitStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    triggered_at: Optional[datetime] = None
    trigger_reason: Optional[str] = None
    
    time_limit: Optional[datetime] = None
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        def _safe_num(v: Any) -> Optional[float]:
            try:
                x = float(v)
            except Exception:
                return None
            if math.isfinite(x):
                return x
            return None

        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": _safe_num(self.entry_price),
            "quantity": _safe_num(self.quantity),
            "remaining_quantity": _safe_num(self.remaining_quantity),
            "stop_loss_price": _safe_num(self.stop_loss_price),
            "stop_loss_type": self.stop_loss_type.value,
            "take_profit_price": _safe_num(self.take_profit_price),
            "take_profit_type": self.take_profit_type.value,
            "trailing_stop_activated": self.trailing_stop_activated,
            "highest_price": _safe_num(self.highest_price),
            "lowest_price": _safe_num(self.lowest_price),
            "breakeven_activated": self.breakeven_activated,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "trigger_reason": self.trigger_reason,
            "metadata": self.metadata,
        }


@dataclass
class StopLossTakeProfitConfig:
    """止盈止损管理器配置"""
    default_stop_loss_percent: float = 0.03
    default_take_profit_percent: float = 0.06
    enable_trailing_stop: bool = True
    trailing_stop_offset: float = 0.02
    trailing_stop_trigger: float = 0.02
    enable_breakeven: bool = True
    breakeven_trigger: float = 0.02
    enable_partial_tp: bool = True
    check_interval: int = 5
    max_orders: int = 100
    persist_file: str = "data/stop_loss_orders.json"
    sync_exchange_positions_on_startup: bool = True
    # 触发 SL/TP/时间止损时是否调用交易所真实平仓（经 ExecutionGateway）
    execute_exchange_on_trigger: bool = True
    # 动态跟踪：根据实时盘口/波动微调止盈止损
    enable_dynamic_market_adjustment: bool = True
    dynamic_update_min_interval_sec: int = 20
    dynamic_tighten_ratio: float = 0.15
    dynamic_tp_extend_ratio: float = 0.10
    # 市场跟踪窗口与阈值：用于动态调整止盈止损和追踪偏移
    market_tracking_window: int = 20
    volatility_tighten_threshold: float = 0.02
    trend_extend_threshold: float = 0.005
    min_trailing_offset: float = 0.006
    max_trailing_offset: float = 0.03


class StopLossTakeProfitManager:
    """
    止盈止损管理器
    
    功能：
    1. 固定止盈止损
    2. 移动止盈止损（追踪止损）
    3. 分批止盈
    4. 保本止损
    5. 时间止损
    """
    
    def __init__(self, config: Optional[StopLossTakeProfitConfig] = None):
        self.config = config or StopLossTakeProfitConfig()
        
        self.orders: Dict[str, StopLossTakeProfitOrder] = {}
        self.order_index: Dict[str, str] = {}
        
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._callbacks: Dict[str, List[Callable]] = {
            "on_stop_loss": [],
            "on_take_profit": [],
            "on_trailing_update": [],
            "on_breakeven": [],
            "on_partial_tp": [],
            "on_time_stop": []
        }
        
        self._exchange = None
        self._main_controller = None
        self._audit_logger = None
        self._enhanced_monitoring = None
        
        self._stats = {
            "total_orders": 0,
            "stop_loss_triggered": 0,
            "take_profit_triggered": 0,
            "trailing_updates": 0,
            "breakeven_activated": 0,
            "partial_tp_executed": 0,
            "time_stop_triggered": 0,
            "dynamic_adjustments": 0,
        }
        
        self._persist_path = Path(self.config.persist_file)
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info("止盈止损管理器初始化完成")
    
    def set_exchange(self, exchange):
        """设置交易所实例"""
        self._exchange = exchange

    def set_main_controller(self, main_controller):
        """用于访问 ExecutionGateway 与统一 exchange。"""
        self._main_controller = main_controller

    async def _execute_exchange_close_on_trigger(
        self,
        order: StopLossTakeProfitOrder,
        reason: str,
    ) -> None:
        if not getattr(self.config, "execute_exchange_on_trigger", True):
            return
        ex = self._exchange
        mc = self._main_controller
        if not ex and mc and hasattr(mc, "get_exchange"):
            try:
                ex = mc.get_exchange()
            except Exception:
                ex = None
        if not ex:
            logger.warning("止盈止损触发但无交易所连接，跳过实盘平仓: %s", order.symbol)
            return

        gw = getattr(mc, "execution_gateway", None) if mc else None
        try:
            if gw:
                res = await gw.close_swap(
                    symbol=order.symbol,
                    side=order.side,
                    size=float(order.remaining_quantity or order.quantity or 0) or None,
                    source="stop_loss_take_profit",
                    reason=reason,
                )
            else:
                close_fn = getattr(ex, "close_swap_position", None) or getattr(ex, "close_position", None)
                if not callable(close_fn):
                    logger.error("交易所缺少 close_swap_position/close_position，无法实盘平仓")
                    return
                res = await close_fn(
                    order.symbol,
                    order.side,
                    float(order.remaining_quantity or order.quantity or 0) or None,
                )
            ok = bool(isinstance(res, dict) and res.get("success"))
            if ok:
                logger.info("✅ 止盈止损实盘平仓已提交: %s reason=%s", order.symbol, reason)
                try:
                    idx = (order.metadata or {}).get("index_key") or order.symbol
                    if idx in self.order_index:
                        del self.order_index[idx]
                    await self._save_orders()
                except Exception:
                    pass
            else:
                err = res.get("error", res) if isinstance(res, dict) else res
                logger.error("❌ 止盈止损实盘平仓失败: %s err=%s", order.symbol, err)
        except Exception as e:
            logger.exception("止盈止损实盘平仓异常: %s", e)
    
    def set_audit_logger(self, audit_logger):
        """设置审计日志记录器"""
        self._audit_logger = audit_logger
    
    def set_enhanced_monitoring(self, monitoring):
        """设置增强监控系统"""
        self._enhanced_monitoring = monitoring
    
    def register_callback(self, event: str, callback: Callable):
        """注册事件回调"""
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    async def initialize(self) -> bool:
        """初始化止盈止损管理器"""
        logger.info("止盈止损管理器初始化...")
        
        await self._load_orders()
        
        return True
    
    async def start(self) -> None:
        """启动监控"""
        if self._running:
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("✅ 止盈止损监控已启动")

    async def sync_open_positions_from_exchange(self) -> Dict[str, Any]:
        """
        将交易所当前净持仓登记到本地止盈止损跟踪（解决「仓位在交易所但本模块未建单」的问题）。
        每个持仓使用 index_key = symbol|side，与合约多空方向区分。
        """
        if not self.config.sync_exchange_positions_on_startup:
            return {"synced": 0, "skipped": 0, "disabled": True}
        if not self._exchange:
            logger.warning("sync_open_positions: 交易所未连接，跳过持仓同步")
            return {"synced": 0, "skipped": 0, "error": "no_exchange"}
        if not hasattr(self._exchange, "get_positions"):
            return {"synced": 0, "skipped": 0, "error": "no_get_positions"}

        try:
            positions = await self._exchange.get_positions()
        except Exception as e:
            logger.error(f"sync_open_positions: 拉取持仓失败: {e}")
            return {"synced": 0, "skipped": 0, "error": str(e)}

        synced = 0
        skipped = 0
        stale_cancelled = 0
        live_index_keys = set()

        for p in positions or []:
            try:
                sz = float(p.get("size", 0) or 0)
                if abs(sz) < 1e-12:
                    continue
                sym = str(p.get("symbol", "") or p.get("instId", "") or "").strip()
                if not sym:
                    continue
                side = str(p.get("side", "") or p.get("posSide", "") or "long").lower()
                if side not in ("long", "short"):
                    side = "long" if sz > 0 else "short"
                live_index_keys.add(f"{sym}|{side}")
            except Exception:
                continue

        # 清理本地已不存在于交易所的活动跟踪单，避免历史脏数据长期残留。
        for oid, order in list(self.orders.items()):
            try:
                if order.status != StopLossTakeProfitStatus.ACTIVE:
                    continue
                idx_key = (order.metadata or {}).get("index_key") or f"{order.symbol}|{order.side}"
                if idx_key not in live_index_keys:
                    order.status = StopLossTakeProfitStatus.CANCELLED
                    order.trigger_reason = "stale_not_in_exchange"
                    order.updated_at = datetime.now()
                    if self.order_index.get(idx_key) == oid:
                        del self.order_index[idx_key]
                    stale_cancelled += 1
            except Exception:
                continue

        for p in positions or []:
            try:
                sz = float(p.get("size", 0) or 0)
                if abs(sz) < 1e-12:
                    continue
                sym = str(p.get("symbol", "") or p.get("instId", "") or "").strip()
                if not sym:
                    continue
                side = str(p.get("side", "") or p.get("posSide", "") or "long").lower()
                if side not in ("long", "short"):
                    side = "long" if sz > 0 else "short"
                entry = float(p.get("entry_price", 0) or 0)
                index_key = f"{sym}|{side}"

                oid = self.order_index.get(index_key)
                if oid:
                    existing = self.orders.get(oid)
                    if existing and existing.status == StopLossTakeProfitStatus.ACTIVE:
                        skipped += 1
                        continue

                if entry <= 0:
                    try:
                        t = await self._exchange.get_ticker(sym)
                        if t and float(t.get("last", 0) or 0) > 0:
                            entry = float(t["last"])
                    except Exception:
                        pass
                if entry <= 0:
                    logger.warning(f"sync_open_positions: 跳过 {index_key}（无有效入场价）")
                    continue

                if len(self.orders) >= self.config.max_orders:
                    logger.warning("sync_open_positions: 已达 max_orders，停止同步")
                    break

                await self.create_order(
                    sym,
                    side,
                    entry,
                    abs(sz),
                    metadata={
                        "index_key": index_key,
                        "source": "exchange_sync",
                    },
                )
                synced += 1
            except Exception as e:
                logger.warning(f"sync_open_positions: 处理单条持仓失败: {e}")

        if stale_cancelled > 0:
            await self._save_orders()
        logger.info(f"📌 交易所持仓→止盈止损跟踪: 新建 {synced}，已存在跳过 {skipped}，清理陈旧 {stale_cancelled}")
        return {"synced": synced, "skipped": skipped, "stale_cancelled": stale_cancelled}
    
    async def stop(self) -> None:
        """停止监控"""
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        await self._save_orders()
        logger.info("止盈止损监控已停止")
    
    async def create_order(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        stop_loss_config: Optional[StopLossConfig] = None,
        take_profit_config: Optional[TakeProfitConfig] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> StopLossTakeProfitOrder:
        """
        创建止盈止损订单
        
        Args:
            symbol: 交易对
            side: 方向 (long/short)
            entry_price: 入场价格
            quantity: 数量
            stop_loss_config: 止损配置
            take_profit_config: 止盈配置
            metadata: 元数据
        
        Returns:
            止盈止损订单
        """
        meta = dict(metadata or {})
        index_key = meta.get("index_key") or symbol

        order_id = self._generate_order_id(index_key)
        
        sl_config = stop_loss_config or StopLossConfig()
        tp_config = take_profit_config or TakeProfitConfig()
        
        stop_loss_price = self._calculate_stop_loss_price(
            entry_price, side, sl_config
        )
        
        take_profit_price = self._calculate_take_profit_price(
            entry_price, side, tp_config
        )
        
        time_limit = None
        if sl_config.time_limit_hours > 0:
            time_limit = datetime.now() + timedelta(hours=sl_config.time_limit_hours)
        
        order = StopLossTakeProfitOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            remaining_quantity=quantity,
            stop_loss_price=stop_loss_price,
            stop_loss_type=sl_config.stop_type,
            stop_loss_value=sl_config.stop_value,
            take_profit_price=take_profit_price,
            take_profit_type=tp_config.tp_type,
            take_profit_value=tp_config.tp_value,
            trailing_stop_offset=sl_config.trailing_offset,
            highest_price=entry_price if side == "long" else 0,
            lowest_price=entry_price if side == "short" else float('inf'),
            time_limit=time_limit,
            metadata=meta
        )
        
        self.orders[order_id] = order
        self.order_index[index_key] = order_id
        self._stats["total_orders"] += 1
        
        await self._save_orders()
        
        logger.info(f"✅ 创建止盈止损订单: {symbol} {side}")
        logger.info(f"   入场价: {entry_price:.4f}")
        logger.info(f"   止损价: {stop_loss_price:.4f} ({sl_config.stop_value*100:.1f}%)")
        logger.info(f"   止盈价: {take_profit_price:.4f} ({tp_config.tp_value*100:.1f}%)")
        
        if self._audit_logger:
            from .audit_logger import AuditEventType, AuditSeverity
            await self._audit_logger.log_event(
                AuditEventType.POSITION_UPDATE,
                AuditSeverity.INFO,
                f"创建止盈止损订单: {symbol}",
                {
                    "order_id": order_id,
                    "symbol": symbol,
                    "side": side,
                    "entry_price": entry_price,
                    "stop_loss": stop_loss_price,
                    "take_profit": take_profit_price
                },
                source="stop_loss_manager"
            )
        
        return order
    
    def _calculate_stop_loss_price(
        self,
        entry_price: float,
        side: str,
        config: StopLossConfig
    ) -> float:
        """计算止损价格"""
        if config.stop_type == StopType.FIXED:
            return config.stop_value
        
        elif config.stop_type == StopType.PERCENTAGE:
            if side == "long":
                return entry_price * (1 - config.stop_value)
            else:
                return entry_price * (1 + config.stop_value)
        
        elif config.stop_type == StopType.ATR_BASED:
            return entry_price - config.atr_multiplier * config.stop_value if side == "long" \
                   else entry_price + config.atr_multiplier * config.stop_value
        
        return entry_price * 0.97 if side == "long" else entry_price * 1.03
    
    def _calculate_take_profit_price(
        self,
        entry_price: float,
        side: str,
        config: TakeProfitConfig
    ) -> float:
        """计算止盈价格"""
        if config.tp_type == TakeProfitType.FIXED:
            return config.tp_value
        
        elif config.tp_type == TakeProfitType.PERCENTAGE:
            if side == "long":
                return entry_price * (1 + config.tp_value)
            else:
                return entry_price * (1 - config.tp_value)
        
        return entry_price * 1.06 if side == "long" else entry_price * 0.94
    
    async def update_price(
        self,
        symbol: str,
        current_price: float,
        index_key: Optional[str] = None,
    ) -> Optional[StopLossTakeProfitOrder]:
        """
        更新价格并检查止盈止损
        
        Args:
            symbol: 交易对
            current_price: 当前价格
            index_key: 订单索引键（同交易对多方向时用 symbol|side），默认与 symbol 相同
        
        Returns:
            如果触发止盈止损，返回订单；否则返回None
        """
        key = index_key or symbol
        order_id = self.order_index.get(key)
        if not order_id:
            return None
        
        order = self.orders.get(order_id)
        if not order or order.status != StopLossTakeProfitStatus.ACTIVE:
            return None
        
        order.updated_at = datetime.now()

        # 先做一次基于实时盘口/价格行为的动态参数微调，再执行触发判断。
        await self._dynamic_market_adjust(order, current_price)

        # 修正边界：极端情况下（重启后加载/同步），最高/最低价可能是 0/inf，先用当前价接管初始化。
        try:
            if order.side == "long":
                if not isinstance(order.highest_price, (int, float)) or order.highest_price <= 0:
                    order.highest_price = float(current_price)
            else:
                lp = float(order.lowest_price) if order.lowest_price is not None else float("inf")
                if (not math.isfinite(lp)) or lp <= 0:
                    order.lowest_price = float(current_price)
        except Exception:
            pass
        
        if order.side == "long":
            if current_price > order.highest_price:
                order.highest_price = current_price
                await self._update_trailing_stop(order, current_price)
        else:
            if current_price < order.lowest_price:
                order.lowest_price = current_price
                await self._update_trailing_stop(order, current_price)
        
        await self._check_breakeven(order, current_price)
        
        triggered = await self._check_stop_loss_take_profit(order, current_price)
        
        await self._check_time_stop(order)
        
        return triggered

    async def _dynamic_market_adjust(self, order: StopLossTakeProfitOrder, current_price: float) -> None:
        """根据实时行情动态微调止盈止损。"""
        if not self.config.enable_dynamic_market_adjustment:
            return
        try:
            now = datetime.now()
            meta = order.metadata or {}
            last_adjust_at = meta.get("last_dynamic_adjust_at")
            if last_adjust_at:
                try:
                    last_dt = datetime.fromisoformat(str(last_adjust_at))
                    if (now - last_dt).total_seconds() < int(self.config.dynamic_update_min_interval_sec):
                        return
                except Exception:
                    pass

            spread_bps = None
            depth_imb = None
            unified_quality = None
            whale_risk = False
            ai_bias = None
            ai_confidence = None
            if self._exchange and hasattr(self._exchange, "get_order_book"):
                try:
                    ob = await self._exchange.get_order_book(order.symbol, depth=10)
                    if ob and getattr(ob, "bids", None) and getattr(ob, "asks", None):
                        best_bid = float(ob.bids[0][0])
                        best_ask = float(ob.asks[0][0])
                        bid_vol = sum(float(x[1]) for x in ob.bids[:5])
                        ask_vol = sum(float(x[1]) for x in ob.asks[:5])
                        spread_bps = ((best_ask - best_bid) / max(1e-9, best_bid)) * 10000.0
                        depth_imb = (bid_vol - ask_vol) / max(1e-9, bid_vol + ask_vol)
                except Exception:
                    pass

            # 接入统一数据源快照（链上大户/质量分），用于 SL/TP 动态微调。
            mc = self._main_controller
            hub = getattr(mc, "data_source_hub", None) if mc else None
            if hub and hasattr(hub, "get_unified_snapshot"):
                try:
                    snap = await hub.get_unified_snapshot(order.symbol)
                    q = ((snap.get("数据质量评估") or {}).get("score")) if isinstance(snap, dict) else None
                    if q is not None:
                        unified_quality = float(q)
                    ai_blk = (snap.get("AI智能分析") or {}) if isinstance(snap, dict) else {}
                    ai_bias = str(ai_blk.get("action_bias") or "").lower() or None
                    try:
                        ai_confidence = float(ai_blk.get("confidence")) if ai_blk.get("confidence") is not None else None
                    except Exception:
                        ai_confidence = None
                    whale_blk = (snap.get("大资金与大户监控") or {}) if isinstance(snap, dict) else {}
                    whale_count = int(whale_blk.get("链上大户活跃条数") or 0)
                    high_risk_positions = int(
                        ((snap.get("渠道A_交易所实时执行数据") or {}).get("liquidation_proxy") or {}).get("high_risk_positions") or 0
                    )
                    whale_risk = whale_count >= 6 or high_risk_positions >= 1
                except Exception:
                    pass

            # 维护短窗价格状态，提取趋势与波动率
            ph = meta.get("price_history", [])
            if not isinstance(ph, list):
                ph = []
            ph.append(float(current_price))
            keep = max(5, int(self.config.market_tracking_window))
            if len(ph) > keep:
                ph = ph[-keep:]
            meta["price_history"] = ph

            trend = 0.0
            volatility = 0.0
            if len(ph) >= 5:
                base = max(1e-9, float(ph[0]))
                trend = (float(ph[-1]) - float(ph[0])) / base
                mean = sum(ph) / len(ph)
                variance = sum((x - mean) ** 2 for x in ph) / max(1, len(ph) - 1)
                volatility = (variance ** 0.5) / max(1e-9, mean)

            pnl = self._calculate_pnl_percent(order, current_price)
            tighten_ratio = float(meta.get("dynamic_tighten_ratio", self.config.dynamic_tighten_ratio) or self.config.dynamic_tighten_ratio)
            tp_extend_ratio = float(meta.get("dynamic_tp_extend_ratio", self.config.dynamic_tp_extend_ratio) or self.config.dynamic_tp_extend_ratio)
            changed = False

            # 仅在浮盈阶段做主动动态调整，降低频繁噪音修改。
            if pnl > 0:
                adverse = False
                favorable = False
                if depth_imb is not None:
                    adverse = (order.side == "long" and depth_imb < -0.35) or (order.side == "short" and depth_imb > 0.35)
                    favorable = (order.side == "long" and depth_imb > 0.25) or (order.side == "short" and depth_imb < -0.25)
                spread_guard = float((meta.get("guard_profile") or {}).get("effective_max_spread_bps", 40.0) or 40.0)
                if spread_bps is not None and spread_bps > max(25.0, spread_guard):
                    adverse = True
                if volatility >= float(self.config.volatility_tighten_threshold):
                    adverse = True
                if whale_risk:
                    adverse = True
                if unified_quality is not None and unified_quality < 0.5:
                    adverse = True
                # AI 分析参与：高置信度反向倾向时优先保护；同向时适度放宽止盈空间。
                if ai_confidence is not None and ai_confidence >= 0.65 and ai_bias:
                    if order.side == "long" and ai_bias in {"sell", "short"}:
                        adverse = True
                    elif order.side == "short" and ai_bias in {"buy", "long"}:
                        adverse = True
                    elif order.side == "long" and ai_bias in {"buy", "long"}:
                        favorable = True
                    elif order.side == "short" and ai_bias in {"sell", "short"}:
                        favorable = True

                trend_thr = float(self.config.trend_extend_threshold)
                if order.side == "long" and trend >= trend_thr:
                    favorable = True
                if order.side == "short" and trend <= -trend_thr:
                    favorable = True

                sl = float(order.stop_loss_price or 0)
                tp = float(order.take_profit_price or 0)
                # 追踪偏移也动态化：高波动收紧，顺势平稳可小幅放宽
                if volatility >= float(self.config.volatility_tighten_threshold):
                    order.trailing_stop_offset = max(
                        float(self.config.min_trailing_offset),
                        float(order.trailing_stop_offset) * (1.0 - tighten_ratio * 0.5),
                    )
                elif favorable:
                    order.trailing_stop_offset = min(
                        float(self.config.max_trailing_offset),
                        float(order.trailing_stop_offset) * (1.0 + tp_extend_ratio * 0.3),
                    )
                if order.side == "long":
                    if adverse and sl > 0:
                        # 向现价上移止损，锁定部分利润
                        target_sl = sl + (current_price - sl) * tighten_ratio
                        if target_sl > sl:
                            order.stop_loss_price = target_sl
                            changed = True
                    elif favorable and tp > 0:
                        # 顺风单略微放宽止盈目标，争取趋势延续利润
                        ext = (tp - current_price) * tp_extend_ratio
                        if ext > 0:
                            order.take_profit_price = tp + ext
                            changed = True
                else:
                    if adverse and sl > 0:
                        target_sl = sl - (sl - current_price) * tighten_ratio
                        if target_sl < sl:
                            order.stop_loss_price = target_sl
                            changed = True
                    elif favorable and tp > 0:
                        ext = (current_price - tp) * tp_extend_ratio
                        if ext > 0:
                            order.take_profit_price = tp - ext
                            changed = True

            if changed:
                self._stats["dynamic_adjustments"] += 1
                order.updated_at = now
                meta["last_dynamic_adjust_at"] = now.isoformat()
                meta["last_market_spread_bps"] = float(spread_bps) if spread_bps is not None else None
                meta["last_market_depth_imbalance"] = float(depth_imb) if depth_imb is not None else None
                meta["last_market_trend"] = float(trend)
                meta["last_market_volatility"] = float(volatility)
                meta["last_unified_quality_score"] = float(unified_quality) if unified_quality is not None else None
                meta["last_whale_risk"] = bool(whale_risk)
                meta["last_ai_bias"] = ai_bias
                meta["last_ai_confidence"] = ai_confidence
                meta["last_trailing_offset"] = float(order.trailing_stop_offset)
                order.metadata = meta
                logger.info(
                    "🧭 动态调整SL/TP: %s side=%s pnl=%.2f%% sl=%.4f tp=%.4f tr_off=%.4f spread=%s imb=%s trend=%.4f vol=%.4f",
                    order.symbol,
                    order.side,
                    pnl * 100.0,
                    float(order.stop_loss_price or 0),
                    float(order.take_profit_price or 0),
                    float(order.trailing_stop_offset or 0.0),
                    f"{spread_bps:.2f}" if spread_bps is not None else "N/A",
                    f"{depth_imb:.3f}" if depth_imb is not None else "N/A",
                    float(trend),
                    float(volatility),
                )
        except Exception as e:
            logger.debug(f"动态调整止盈止损失败: {e}")
    
    async def _update_trailing_stop(self, order: StopLossTakeProfitOrder, current_price: float):
        """更新移动止损"""
        if not self.config.enable_trailing_stop:
            return
        
        pnl_percent = self._calculate_pnl_percent(order, current_price)
        
        if pnl_percent >= self.config.trailing_stop_trigger and not order.trailing_stop_activated:
            order.trailing_stop_activated = True
            logger.info(f"📊 {order.symbol} 激活移动止损 (盈利 {pnl_percent*100:.1f}%)")
            
            if self._enhanced_monitoring:
                await self._enhanced_monitoring.update_metric(
                    "trailing_stop_activated",
                    1,
                    {"symbol": order.symbol}
                )
        
        if order.trailing_stop_activated:
            if order.side == "long":
                new_stop = order.highest_price * (1 - order.trailing_stop_offset)
                if new_stop > order.stop_loss_price:
                    old_stop = order.stop_loss_price
                    order.stop_loss_price = new_stop
                    self._stats["trailing_updates"] += 1
                    logger.info(f"📈 {order.symbol} 移动止损更新: {old_stop:.4f} -> {new_stop:.4f}")
                    
                    await self._notify_callbacks("on_trailing_update", order, old_stop, new_stop)
            else:
                new_stop = order.lowest_price * (1 + order.trailing_stop_offset)
                if new_stop < order.stop_loss_price or order.stop_loss_price == 0:
                    old_stop = order.stop_loss_price
                    order.stop_loss_price = new_stop
                    self._stats["trailing_updates"] += 1
                    logger.info(f"📉 {order.symbol} 移动止损更新: {old_stop:.4f} -> {new_stop:.4f}")
                    
                    await self._notify_callbacks("on_trailing_update", order, old_stop, new_stop)
    
    async def _check_breakeven(self, order: StopLossTakeProfitOrder, current_price: float):
        """检查保本止损"""
        if not self.config.enable_breakeven or order.breakeven_activated:
            return
        
        pnl_percent = self._calculate_pnl_percent(order, current_price)
        
        if pnl_percent >= self.config.breakeven_trigger:
            order.breakeven_activated = True
            order.breakeven_price = order.entry_price
            order.stop_loss_price = order.entry_price
            self._stats["breakeven_activated"] += 1
            
            logger.info(f"🛡️ {order.symbol} 激活保本止损 (盈利 {pnl_percent*100:.1f}%)")
            
            await self._notify_callbacks("on_breakeven", order)
    
    async def _check_stop_loss_take_profit(
        self,
        order: StopLossTakeProfitOrder,
        current_price: float
    ) -> Optional[StopLossTakeProfitOrder]:
        """检查止盈止损触发"""
        if order.status != StopLossTakeProfitStatus.ACTIVE:
            return None
        
        stop_loss_triggered = False
        take_profit_triggered = False
        
        if order.side == "long":
            if order.stop_loss_price and current_price <= order.stop_loss_price:
                stop_loss_triggered = True
            if order.take_profit_price and current_price >= order.take_profit_price:
                take_profit_triggered = True
        else:
            if order.stop_loss_price and current_price >= order.stop_loss_price:
                stop_loss_triggered = True
            if order.take_profit_price and current_price <= order.take_profit_price:
                take_profit_triggered = True
        
        if stop_loss_triggered:
            return await self._trigger_stop_loss(order, current_price)
        
        if take_profit_triggered:
            return await self._trigger_take_profit(order, current_price)
        
        return None
    
    async def _trigger_stop_loss(
        self,
        order: StopLossTakeProfitOrder,
        current_price: float
    ) -> StopLossTakeProfitOrder:
        """触发止损"""
        order.status = StopLossTakeProfitStatus.TRIGGERED
        order.triggered_at = datetime.now()
        order.trigger_reason = "stop_loss"
        self._stats["stop_loss_triggered"] += 1
        
        pnl_percent = self._calculate_pnl_percent(order, current_price)
        
        logger.warning(f"🚨 {order.symbol} 触发止损!")
        logger.warning(f"   入场价: {order.entry_price:.4f}")
        logger.warning(f"   止损价: {order.stop_loss_price:.4f}")
        logger.warning(f"   当前价: {current_price:.4f}")
        logger.warning(f"   亏损: {pnl_percent*100:.2f}%")
        
        if self._audit_logger:
            from .audit_logger import AuditEventType, AuditSeverity
            await self._audit_logger.log_trade(
                action="stop_loss_trigger",
                symbol=order.symbol,
                side="sell" if order.side == "long" else "buy",
                quantity=order.remaining_quantity,
                price=current_price,
                result="stop_loss"
            )
        
        if self._enhanced_monitoring:
            await self._enhanced_monitoring.update_metric(
                "stop_loss_triggered",
                1,
                {"symbol": order.symbol, "pnl_percent": pnl_percent}
            )
        
        await self._notify_callbacks("on_stop_loss", order, current_price)

        await self._execute_exchange_close_on_trigger(order, "stop_loss")
        
        await self._save_orders()
        
        return order
    
    async def _trigger_take_profit(
        self,
        order: StopLossTakeProfitOrder,
        current_price: float
    ) -> StopLossTakeProfitOrder:
        """触发止盈"""
        pnl_percent = self._calculate_pnl_percent(order, current_price)
        
        if self.config.enable_partial_tp and order.take_profit_type == TakeProfitType.PARTIAL:
            partial_executed = False
            for level_percent, level_ratio in order.metadata.get("partial_levels", []):
                if pnl_percent >= level_percent and not any(
                    p[0] == level_percent for p in order.partial_tp_executed
                ):
                    partial_quantity = order.quantity * level_ratio
                    order.remaining_quantity -= partial_quantity
                    order.partial_tp_executed.append((level_percent, partial_quantity))
                    self._stats["partial_tp_executed"] += 1
                    partial_executed = True
                    
                    logger.info(f"🎯 {order.symbol} 分批止盈: {level_percent*100:.1f}% 平仓 {level_ratio*100:.0f}%")
                    
                    await self._notify_callbacks("on_partial_tp", order, level_percent, partial_quantity)
            
            if partial_executed and order.remaining_quantity > 0:
                await self._save_orders()
                return order
        
        order.status = StopLossTakeProfitStatus.TRIGGERED
        order.triggered_at = datetime.now()
        order.trigger_reason = "take_profit"
        self._stats["take_profit_triggered"] += 1
        
        logger.info(f"🎯 {order.symbol} 触发止盈!")
        logger.info(f"   入场价: {order.entry_price:.4f}")
        logger.info(f"   止盈价: {order.take_profit_price:.4f}")
        logger.info(f"   当前价: {current_price:.4f}")
        logger.info(f"   盈利: {pnl_percent*100:.2f}%")
        
        if self._audit_logger:
            from .audit_logger import AuditEventType, AuditSeverity
            await self._audit_logger.log_trade(
                action="take_profit_trigger",
                symbol=order.symbol,
                side="sell" if order.side == "long" else "buy",
                quantity=order.remaining_quantity,
                price=current_price,
                result="take_profit"
            )
        
        if self._enhanced_monitoring:
            await self._enhanced_monitoring.update_metric(
                "take_profit_triggered",
                1,
                {"symbol": order.symbol, "pnl_percent": pnl_percent}
            )
        
        await self._notify_callbacks("on_take_profit", order, current_price)

        await self._execute_exchange_close_on_trigger(order, "take_profit")
        
        await self._save_orders()
        
        return order
    
    async def _check_time_stop(self, order: StopLossTakeProfitOrder):
        """检查时间止损"""
        if not order.time_limit:
            return
        
        if datetime.now() >= order.time_limit:
            order.status = StopLossTakeProfitStatus.TRIGGERED
            order.triggered_at = datetime.now()
            order.trigger_reason = "time_stop"
            self._stats["time_stop_triggered"] += 1
            
            logger.info(f"⏰ {order.symbol} 触发时间止损 (持仓超时)")
            
            await self._notify_callbacks("on_time_stop", order)

            await self._execute_exchange_close_on_trigger(order, "time_stop")
            
            await self._save_orders()
    
    def _calculate_pnl_percent(self, order: StopLossTakeProfitOrder, current_price: float) -> float:
        """计算盈亏百分比"""
        if order.side == "long":
            return (current_price - order.entry_price) / order.entry_price
        else:
            return (order.entry_price - current_price) / order.entry_price
    
    async def modify_order(
        self,
        symbol: str,
        new_stop_loss: Optional[float] = None,
        new_take_profit: Optional[float] = None
    ) -> Optional[StopLossTakeProfitOrder]:
        """修改止盈止损订单"""
        order_id = self.order_index.get(symbol)
        if not order_id:
            return None
        
        order = self.orders.get(order_id)
        if not order or order.status != StopLossTakeProfitStatus.ACTIVE:
            return None
        
        if new_stop_loss is not None:
            old_sl = order.stop_loss_price
            order.stop_loss_price = new_stop_loss
            logger.info(f"📝 {symbol} 修改止损: {old_sl:.4f} -> {new_stop_loss:.4f}")
        
        if new_take_profit is not None:
            old_tp = order.take_profit_price
            order.take_profit_price = new_take_profit
            logger.info(f"📝 {symbol} 修改止盈: {old_tp:.4f} -> {new_take_profit:.4f}")
        
        order.status = StopLossTakeProfitStatus.MODIFIED
        order.updated_at = datetime.now()
        
        await self._save_orders()
        
        return order
    
    async def cancel_order(self, symbol: str) -> bool:
        """取消止盈止损订单"""
        order_id = self.order_index.get(symbol)
        if not order_id:
            return False
        
        order = self.orders.get(order_id)
        if not order:
            return False
        
        order.status = StopLossTakeProfitStatus.CANCELLED
        order.updated_at = datetime.now()
        
        logger.info(f"❌ 取消止盈止损订单: {symbol}")
        
        await self._save_orders()
        
        return True
    
    async def get_order(self, symbol: str) -> Optional[StopLossTakeProfitOrder]:
        """获取止盈止损订单"""
        order_id = self.order_index.get(symbol)
        if not order_id:
            return None
        return self.orders.get(order_id)
    
    async def get_all_active_orders(self) -> List[StopLossTakeProfitOrder]:
        """获取所有活动订单"""
        return [
            order for order in self.orders.values()
            if order.status == StopLossTakeProfitStatus.ACTIVE
        ]
    
    async def get_triggered_orders(self, limit: int = 50) -> List[StopLossTakeProfitOrder]:
        """获取已触发的订单"""
        return [
            order for order in self.orders.values()
            if order.status == StopLossTakeProfitStatus.TRIGGERED
        ][-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "active_orders": len([o for o in self.orders.values() if o.status == StopLossTakeProfitStatus.ACTIVE]),
            "total_orders_tracked": len(self.orders)
        }
    
    async def _monitor_loop(self) -> None:
        """监控循环"""
        logger.info("止盈止损监控循环启动")
        
        while self._running:
            try:
                if not self._exchange:
                    await asyncio.sleep(self.config.check_interval)
                    continue
                
                active_orders = await self.get_all_active_orders()
                
                for order in active_orders:
                    try:
                        ticker = await self._exchange.get_ticker(order.symbol)
                        if ticker:
                            current_price = ticker.get("last", 0)
                            if current_price > 0:
                                idx = (order.metadata or {}).get("index_key") or order.symbol
                                await self.update_price(order.symbol, current_price, index_key=idx)
                    except Exception as e:
                        logger.error(f"更新 {order.symbol} 价格失败: {e}")
                
                await asyncio.sleep(self.config.check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"止盈止损监控循环错误: {e}")
                await asyncio.sleep(5)
        
        logger.info("止盈止损监控循环停止")
    
    async def _notify_callbacks(self, event: str, *args):
        """通知回调"""
        for callback in self._callbacks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(*args)
                else:
                    callback(*args)
            except Exception as e:
                logger.error(f"回调执行失败 {event}: {e}")
    
    def _generate_order_id(self, symbol: str) -> str:
        """生成订单ID"""
        import hashlib
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        hash_part = hashlib.md5(f"{symbol}_{timestamp}".encode()).hexdigest()[:8]
        return f"sltp_{symbol.replace('/', '')}_{timestamp}_{hash_part}"
    
    async def _save_orders(self):
        """保存订单到文件"""
        try:
            data = {
                "orders": {oid: order.to_dict() for oid, order in self.orders.items()},
                "stats": self._stats,
                "saved_at": datetime.now().isoformat()
            }
            
            with open(self._persist_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存止盈止损订单失败: {e}")
    
    async def _load_orders(self):
        """从文件加载订单"""
        try:
            if not self._persist_path.exists():
                return
            
            with open(self._persist_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for oid, order_data in data.get("orders", {}).items():
                order = StopLossTakeProfitOrder(
                    order_id=order_data["order_id"],
                    symbol=order_data["symbol"],
                    side=order_data["side"],
                    entry_price=order_data["entry_price"],
                    quantity=order_data["quantity"],
                    remaining_quantity=order_data["remaining_quantity"],
                    stop_loss_price=order_data.get("stop_loss_price"),
                    stop_loss_type=StopType(order_data.get("stop_loss_type", "percentage")),
                    stop_loss_value=order_data.get("stop_loss_value", 0.03),
                    take_profit_price=order_data.get("take_profit_price"),
                    take_profit_type=TakeProfitType(order_data.get("take_profit_type", "percentage")),
                    take_profit_value=order_data.get("take_profit_value", 0.06),
                    trailing_stop_activated=order_data.get("trailing_stop_activated", False),
                    highest_price=order_data.get("highest_price", 0),
                    lowest_price=order_data.get("lowest_price", float('inf')),
                    status=StopLossTakeProfitStatus(order_data.get("status", "active")),
                    created_at=datetime.fromisoformat(order_data["created_at"]) if order_data.get("created_at") else datetime.now(),
                    triggered_at=datetime.fromisoformat(order_data["triggered_at"]) if order_data.get("triggered_at") else None,
                    trigger_reason=order_data.get("trigger_reason"),
                    metadata=order_data.get("metadata") or {},
                )
                
                self.orders[oid] = order
                idx_key = (order.metadata or {}).get("index_key") or order.symbol
                self.order_index[idx_key] = oid
            
            self._stats.update(data.get("stats", {}))
            
            logger.info(f"加载 {len(self.orders)} 个止盈止损订单")
            
        except Exception as e:
            logger.error(f"加载止盈止损订单失败: {e}")
    
    async def cleanup(self):
        """清理资源"""
        await self.stop()
        logger.info("止盈止损管理器清理完成")
