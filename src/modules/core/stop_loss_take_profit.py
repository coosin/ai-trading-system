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
import time
import uuid
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Tuple
from enum import Enum
from pathlib import Path
import math

logger = logging.getLogger(__name__)

from src.modules.memory.memory_schema import base_metadata, kind_tag, symbol_tag, tags


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
    NONE = "none"                   # 不使用固定止盈（仅移动止损/追踪出场）


class StopLossTakeProfitStatus(Enum):
    """止盈止损状态"""
    ACTIVE = "active"               # 激活中
    PENDING_CLOSE = "pending_close" # 已触发，等待/重试真实平仓确认
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
            "take_profit_value": _safe_num(self.take_profit_value),
            "stop_loss_value": _safe_num(self.stop_loss_value),
            "trailing_stop_activated": self.trailing_stop_activated,
            "trailing_stop_offset": _safe_num(self.trailing_stop_offset),
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
    """止盈止损管理器配置 - 移动止损模式"""
    default_stop_loss_percent: float = 0.10  # 固定止损10%（兜底）
    default_take_profit_percent: float = 0.0  # 不设固定止盈
    enable_trailing_stop: bool = True
    trailing_stop_offset: float = 0.10
    trailing_stop_trigger: float = 0.06  # 3.5%触发二档
    # --- 移动止盈止损模式：开仓即2.3%追踪；浮盈达2.3%后收紧到1.3%；不设固定止盈 ---
    trailing_only_mode: bool = True
    """为 True 时：新建单使用 TRAILING 止损 + 无固定止盈价，仅依赖移动止损出场。"""
    trailing_only_coerce_inputs: bool = True
    """为 True 且 trailing_only_mode 时：忽略外部传入的固定/百分比 SLTP，强制移动止损 + 无止盈价。"""
    trailing_active_on_open: bool = True
    """开仓即启用移动止损逻辑（不等浮盈达到 trailing_stop_trigger）。"""
    initial_trailing_offset: float = 0.10  # 10% 初始移动止损
    """初始移动止损相对峰值/入场的回撤比例（2.3%）。"""
    profit_tier2_pnl_threshold: float = 0.06
    """二档：相对入场的浮盈比例达到2.3%后，将移动带宽收紧为 tier2_trailing_offset。"""
    tier2_trailing_offset: float = 0.04  # 2.5%二档移动带宽
    """二档移动带宽（1.3%），浮盈2.3%后启用，更严格锁利。"""
    # 动能微调：趋势+短周期变化在「中性带」内则不改变 trailing_offset；转弱收紧，顺势略放宽
    trailing_momentum_adjust_enable: bool = True
    trailing_momentum_trend_neutral_abs: float = 0.002
    trailing_momentum_short_neutral_abs: float = 0.0015
    trailing_momentum_tighten_factor: float = 0.92
    trailing_momentum_loosen_factor: float = 1.05
    enable_breakeven: bool = True  # 启用保本止损
    breakeven_trigger: float = 0.02
    # 分层固定止盈（锁仓）
    # 1) 浮盈>=30% 平30%
    # 2) 浮盈>=50% 再平20%
    # 剩余50%继续持有
    enable_partial_tp: bool = True
    layered_partial_tp_enable: bool = True
    layered_partial_tp_levels: List[Tuple[float, float]] = field(
        default_factory=lambda: [(0.30, 0.30), (0.50, 0.20)]
    )
    # 分层移动止盈（按峰值回撤触发）：
    # 峰值浮盈>=30% -> 回撤5%
    # 峰值浮盈>=50% -> 回撤10%
    # 峰值浮盈>=60% -> 回撤15%
    layered_trailing_tp_enable: bool = True
    layered_trailing_tp_drawdown_levels: List[Tuple[float, float]] = field(
        default_factory=lambda: [(0.30, 0.05), (0.50, 0.10), (0.60, 0.15)]
    )
    check_interval: int = 5
    # 仅限制「活跃跟踪」数量；已触发/已取消的历史单不计入（否则会误伤 sync_open_positions）
    max_orders: int = 100
    persist_file: str = "data/stop_loss_orders.json"
    sync_exchange_positions_on_startup: bool = True
    # 运行中周期性把交易所持仓再登记到 SLTP（防止仅启动时同步一次后漂移）
    exchange_resync_interval_sec: int = 45
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
    min_trailing_offset: float = 0.005
    max_trailing_offset: float = 0.20
    # SLTP trigger close confirmation / retry
    pending_close_max_retries: int = 6
    pending_close_backoff_base_sec: float = 2.0
    pending_close_backoff_cap_sec: float = 120.0


def _coerce_stop_loss_take_profit_field(name: str, raw: Any, template: StopLossTakeProfitConfig) -> Any:
    """Coerce a single config value to the dataclass field type."""
    if raw is None:
        return getattr(template, name)
    fmap = {f.name: f for f in dataclasses.fields(StopLossTakeProfitConfig)}
    f = fmap.get(name)
    if not f:
        return raw
    ann = f.type
    if ann is bool:
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if ann is int:
        return int(float(raw))
    if ann is float:
        return float(raw)
    if ann is str:
        return str(raw)
    return raw


def stop_loss_take_profit_config_from_mapping(
    data: Optional[Dict[str, Any]] = None,
    *,
    strategy_section: Optional[Dict[str, Any]] = None,
) -> StopLossTakeProfitConfig:
    """
    Build StopLossTakeProfitConfig from ConfigManager / YAML dict.

    Unknown keys are ignored. Optional legacy ``strategy.risk_management`` is applied
    only for ``default_stop_loss_percent`` / ``default_take_profit_percent`` when those
    keys are absent from ``data`` (so old docs that only set strategy.* still work).
    """
    template = StopLossTakeProfitConfig()
    raw = dict(data or {})
    raw_keys = set(raw.keys())
    cfg = StopLossTakeProfitConfig()
    field_names = {f.name for f in dataclasses.fields(StopLossTakeProfitConfig)}
    for key, val in raw.items():
        if key not in field_names:
            logger.debug("Unknown stop_loss_take_profit config key (ignored): %s", key)
            continue
        setattr(cfg, key, _coerce_stop_loss_take_profit_field(key, val, template))

    strat = strategy_section if isinstance(strategy_section, dict) else {}
    rm = strat.get("risk_management") if isinstance(strat.get("risk_management"), dict) else {}
    if "default_stop_loss_percent" not in raw_keys and rm.get("stop_loss") is not None:
        try:
            cfg.default_stop_loss_percent = float(rm["stop_loss"])
        except (TypeError, ValueError):
            logger.warning("Invalid strategy.risk_management.stop_loss: %r", rm.get("stop_loss"))
    if "default_take_profit_percent" not in raw_keys and rm.get("take_profit") is not None:
        try:
            cfg.default_take_profit_percent = float(rm["take_profit"])
        except (TypeError, ValueError):
            logger.warning("Invalid strategy.risk_management.take_profit: %r", rm.get("take_profit"))
    return cfg


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
        self._last_exchange_sync_ts: float = 0.0
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

    _POSKEY_PREFIX = "pos:"

    @classmethod
    def _build_pos_key(cls, inst_id: str, pos_side: str) -> str:
        inst = str(inst_id or "").strip().upper()
        sd = str(pos_side or "").strip().lower()
        if sd not in ("long", "short"):
            sd = "long"
        return f"{cls._POSKEY_PREFIX}{inst}|{sd}"

    @classmethod
    def _is_pos_key(cls, key: str) -> bool:
        return str(key or "").strip().lower().startswith(cls._POSKEY_PREFIX)

    @classmethod
    def _normalize_any_key(cls, key: str) -> str:
        """
        Normalize both:
        - legacy `symbol|side`
        - canonical `pos:<instId>|<posSide>`
        """
        k = str(key or "").strip()
        if not k:
            return k
        if cls._is_pos_key(k):
            raw = k[len(cls._POSKEY_PREFIX) :]
            if "|" not in raw:
                return f"{cls._POSKEY_PREFIX}{raw.strip().upper()}|long"
            inst, sd = raw.rsplit("|", 1)
            inst = inst.strip().upper()
            sd = sd.strip().lower()
            if sd not in ("long", "short"):
                sd = "long"
            return f"{cls._POSKEY_PREFIX}{inst}|{sd}"
        return cls._normalize_index_key(k)

    async def _resolve_pos_key_from_exchange(self, symbol: str, side: str) -> Optional[str]:
        if not self._exchange or not hasattr(self._exchange, "get_positions"):
            return None
        sym = str(symbol or "").strip()
        sd = str(side or "").strip().lower()
        if not sym or sd not in ("long", "short"):
            return None
        try:
            positions = await self._exchange.get_positions()
        except Exception:
            return None
        base = self._normalize_index_key(f"{sym}|{sd}").split("|", 1)[0]
        for p in positions or []:
            if not isinstance(p, dict):
                continue
            try:
                sz = float(p.get("size", 0) or 0)
            except Exception:
                continue
            if abs(sz) < 1e-12:
                continue
            if self._resolved_side_from_position(p) != sd:
                continue
            psym = self._canonical_symbol_from_position(p)
            if not psym:
                continue
            if self._normalize_index_key(f"{psym}|{sd}").split("|", 1)[0] != base:
                continue
            inst_id = str(p.get("instId") or "").strip()
            if inst_id:
                return self._build_pos_key(inst_id, sd)
        return None

    def _key_variants_for(self, *, symbol: str, side: str, pos_key: Optional[str] = None) -> List[str]:
        keys: List[str] = []
        if pos_key:
            keys.append(self._normalize_any_key(pos_key))
        for k in self._index_key_lookup_variants(symbol, side):
            keys.append(self._normalize_any_key(k))
        return list(dict.fromkeys([k for k in keys if k]))

    async def _resolve_canonical_and_variants(
        self, *, symbol: str, side: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, List[str], Dict[str, Any]]:
        meta = dict(metadata or {})
        sd = str(side or "").strip().lower()
        if sd not in ("long", "short"):
            sd = "long"

        pos_key: Optional[str] = None
        pk = meta.get("position_key") or meta.get("pos_key") or meta.get("posKey")
        if pk and self._is_pos_key(str(pk)):
            pos_key = self._normalize_any_key(str(pk))

        if not pos_key:
            inst_id = meta.get("instId") or meta.get("inst_id") or meta.get("instrument_id")
            if inst_id:
                pos_key = self._build_pos_key(str(inst_id), meta.get("posSide") or meta.get("pos_side") or sd)

        idx = meta.get("index_key")
        if not pos_key and idx and self._is_pos_key(str(idx)):
            pos_key = self._normalize_any_key(str(idx))

        if not pos_key:
            pos_key = await self._resolve_pos_key_from_exchange(symbol, sd)

        canonical = self._normalize_any_key(pos_key) if pos_key else self._normalize_any_key(f"{symbol}|{sd}")
        variants = self._key_variants_for(symbol=symbol, side=sd, pos_key=pos_key)

        meta["index_key"] = canonical
        if pos_key:
            meta["position_key"] = self._normalize_any_key(pos_key)
        meta.setdefault("legacy_symbol_key", self._normalize_index_key(f"{symbol}|{sd}"))
        return canonical, variants, meta

    async def _cancel_active_orders_for_index_key(self, index_key: str) -> None:
        """同一 canonical key（优先 pos:<instId>|<posSide>）仅保留一条 ACTIVE：新建前取消旧单，避免重复平仓。"""
        nk = self._normalize_any_key(index_key)
        candidates = [nk]
        # legacy fallback: if given a symbol|side key, include its dash/slash variants
        if not self._is_pos_key(nk) and "|" in nk:
            sp, sd = nk.rsplit("|", 1)
            candidates.extend(self._index_key_lookup_variants(sp.strip(), sd.strip()))
        oid: Optional[str] = None
        for c in dict.fromkeys(candidates):
            oid = self.order_index.get(self._normalize_any_key(c))
            if oid:
                break
        if not oid:
            return
        order = self.orders.get(oid)
        if not order or order.status != StopLossTakeProfitStatus.ACTIVE:
            return
        order.status = StopLossTakeProfitStatus.CANCELLED
        order.updated_at = datetime.now()
        order.trigger_reason = "replaced_by_new_sltp"
        for k in list(self.order_index.keys()):
            if self.order_index.get(k) == oid:
                del self.order_index[k]
        logger.info("SLTP: 已取消同 index 旧 ACTIVE 单以便重建 order_id=%s key=%s", oid, nk)
        await self._save_orders()

    async def _fetch_live_position_size(self, symbol: str, side: str) -> Optional[float]:
        """平仓前从交易所拉取当前张数，减少 residual。"""
        ex = self._exchange
        mc = self._main_controller
        if not ex and mc and hasattr(mc, "get_exchange"):
            try:
                ex = mc.get_exchange()
            except Exception:
                ex = None
        if not ex or not hasattr(ex, "get_positions"):
            return None
        try:
            rows = await ex.get_positions()
        except Exception:
            return None
        want = str(side or "").lower()
        base = str(symbol or "").split("/")[0].strip().upper()
        for p in rows or []:
            if not isinstance(p, dict):
                continue
            if str(p.get("side", "")).lower() != want:
                continue
            iid = str(p.get("instId", "")).upper()
            sym = str(p.get("symbol", "")).upper().replace("-", "/")
            if base and (base in iid or (base + "/") in sym or sym.startswith(base + "/")):
                sz = abs(float(p.get("size", 0) or 0))
                if sz > 1e-12:
                    return sz
        return None

    async def _execute_exchange_close_on_trigger(
        self,
        order: StopLossTakeProfitOrder,
        reason: str,
        close_size: Optional[float] = None,
    ) -> bool:
        if not getattr(self.config, "execute_exchange_on_trigger", True):
            return True
        ex = self._exchange
        mc = self._main_controller
        if not ex and mc and hasattr(mc, "get_exchange"):
            try:
                ex = mc.get_exchange()
            except Exception:
                ex = None
        if not ex:
            logger.warning("止盈止损触发但无交易所连接，跳过实盘平仓: %s", order.symbol)
            return False

        gw = getattr(mc, "execution_gateway", None) if mc else None
        close_sz: Optional[float] = close_size
        if close_sz is None or close_sz <= 0:
            try:
                close_sz = await self._fetch_live_position_size(order.symbol, order.side)
            except Exception:
                close_sz = None
        if close_sz is None or close_sz <= 0:
            close_sz = float(order.remaining_quantity or order.quantity or 0) or None
        try:
            if gw:
                res = await gw.close_swap(
                    symbol=order.symbol,
                    side=order.side,
                    size=close_sz,
                    source="stop_loss_take_profit",
                    reason=reason,
                    context={
                        "trace_id": (order.metadata or {}).get("trace_id") or (order.metadata or {}).get("traceId"),
                        "index_key": (order.metadata or {}).get("index_key"),
                        "position_key": (order.metadata or {}).get("position_key"),
                        "sltp_reason": reason,
                        "sltp_order_id": getattr(order, "order_id", None),
                    },
                )
            else:
                close_fn = getattr(ex, "close_swap_position", None) or getattr(ex, "close_position", None)
                if not callable(close_fn):
                    logger.error("交易所缺少 close_swap_position/close_position，无法实盘平仓")
                    return False
                res = await close_fn(
                    order.symbol,
                    order.side,
                    close_sz,
                )
            ok = bool(isinstance(res, dict) and res.get("success"))
            if ok:
                logger.info("✅ 止盈止损实盘平仓已提交: %s reason=%s", order.symbol, reason)
                # 仅当全平时清理索引；部分平仓保持 ACTIVE 跟踪。
                try:
                    rem = float(order.remaining_quantity or 0)
                    csz = float(close_sz or 0)
                    full_close = csz >= max(rem, 1e-12) - 1e-12
                    if full_close:
                        for k in self._order_index_keys_to_clear(order):
                            if self.order_index.get(k) == order.order_id:
                                del self.order_index[k]
                    await self._save_orders()
                except Exception:
                    pass
                return True
            else:
                err = res.get("error", res) if isinstance(res, dict) else res
                logger.error("❌ 止盈止损实盘平仓失败: %s err=%s", order.symbol, err)
                return False
        except Exception as e:
            logger.exception("止盈止损实盘平仓异常: %s", e)
            return False
    
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
        self._last_exchange_sync_ts = time.time()
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("✅ 止盈止损监控已启动")

    @staticmethod
    def _canonical_symbol_from_position(p: Dict[str, Any]) -> str:
        """统一用 instId 转 slash 形式，避免 BTC-USDT-SWAP 与 BTC/USDT/SWAP 混用导致 index 对不上。"""
        iid = str(p.get("instId") or "").strip()
        if iid:
            return iid.replace("-", "/")
        return str(p.get("symbol") or "").strip()

    @staticmethod
    def _resolved_side_from_position(p: Dict[str, Any]) -> str:
        """方向以适配器解析后的 side 为准；禁止直接用 posSide=net。缺失时用 raw_pos 符号。"""
        s = str(p.get("side") or "").strip().lower()
        if s in ("long", "short"):
            return s
        try:
            rp = float(p.get("raw_pos", 0) or 0)
        except (TypeError, ValueError):
            rp = 0.0
        if rp > 0:
            return "long"
        if rp < 0:
            return "short"
        return "long"

    @staticmethod
    def _normalize_index_key(idx_key: str) -> str:
        """统一 symbol|side：把 BTC-USDT-SWAP|long 与 BTC/USDT/SWAP|long 视为同一键。"""
        k = (idx_key or "").strip()
        if "|" not in k:
            return k
        sym_part, side_part = k.rsplit("|", 1)
        sp = sym_part.strip()
        if sp and "-" in sp and "/" not in sp:
            sp = sp.replace("-", "/")
        return f"{sp}|{side_part.strip().lower()}"

    def _index_key_lookup_variants(self, sym: str, side: str) -> List[str]:
        """order_index 可能存旧 dash 键或新 slash 键，查找时都要试。"""
        side_l = str(side or "").strip().lower()
        sym = (sym or "").strip()
        keys: List[str] = []
        nk = self._normalize_index_key(f"{sym}|{side_l}")
        keys.append(nk)
        if "/" in sym:
            keys.append(f"{sym.replace('/', '-')}|{side_l}")
        keys = list(dict.fromkeys(keys))
        return keys

    def _order_index_keys_to_clear(self, order: "StopLossTakeProfitOrder") -> List[str]:
        meta = order.metadata or {}
        keys: List[str] = []
        for k in (
            meta.get("index_key"),
            meta.get("position_key"),
            meta.get("legacy_symbol_key"),
            f"{order.symbol}|{order.side}",
        ):
            if k:
                keys.append(self._normalize_any_key(str(k)))
        for k in self._index_key_lookup_variants(order.symbol, order.side):
            keys.append(self._normalize_any_key(k))
        return list(dict.fromkeys([k for k in keys if k]))

    def _count_active_orders(self) -> int:
        return sum(1 for o in self.orders.values() if o.status == StopLossTakeProfitStatus.ACTIVE)

    def _reprice_sl_tp_from_order(self, order: StopLossTakeProfitOrder) -> None:
        """入场价变化后按订单内保存的 SL/TP 类型与比例重算价格。"""
        slc = StopLossConfig(
            stop_type=order.stop_loss_type,
            stop_value=float(order.stop_loss_value or 0.03),
            trailing_offset=float(order.trailing_stop_offset or 0.02),
        )
        tpc = TakeProfitConfig(
            tp_type=order.take_profit_type,
            tp_value=float(order.take_profit_value or 0.06),
        )
        order.stop_loss_price = self._calculate_stop_loss_price(order.entry_price, order.side, slc)
        if order.take_profit_type == TakeProfitType.NONE:
            order.take_profit_price = None
        else:
            order.take_profit_price = self._calculate_take_profit_price(order.entry_price, order.side, tpc)

    def _refresh_active_order_from_exchange_position(
        self,
        order: StopLossTakeProfitOrder,
        p: Dict[str, Any],
        sym: str,
        side: str,
    ) -> bool:
        """
        交易所侧持仓与本地 ACTIVE 跟踪对齐：数量、均价变化时更新，并维持 SL/TP 与跟踪边界合理。
        这样在周期性 sync 时不仅「不重复建单」，还能持续「接管」真实仓位。
        """
        changed = False
        new_sz = abs(float(p.get("size", 0) or 0))
        if new_sz > 1e-12:
            if abs(float(order.quantity or 0) - new_sz) > 1e-12 or abs(float(order.remaining_quantity or 0) - new_sz) > 1e-12:
                order.quantity = new_sz
                order.remaining_quantity = new_sz
                changed = True

        # 优先使用 avgPx（平均开仓价），其次 entry_price，最后用 mark_px（标记价格）
        entry = float(p.get("avgPx", 0) or p.get("entry_price", 0) or 0)
        if entry <= 0:
            entry = float(p.get("mark_px", 0) or 0)
        if entry > 0:
            rel = abs(order.entry_price - entry) / max(abs(entry), 1e-12)
            if rel > 1e-7:
                order.entry_price = entry
                self._reprice_sl_tp_from_order(order)
                changed = True
                try:
                    if order.side == "long":
                        hp = float(order.highest_price or 0)
                        order.highest_price = max(hp, entry) if hp > 0 else entry
                    else:
                        lp = float(order.lowest_price) if order.lowest_price is not None else float("inf")
                        if not math.isfinite(lp) or lp <= 0:
                            order.lowest_price = entry
                        else:
                            order.lowest_price = min(lp, entry)
                except Exception:
                    pass

        if changed:
            order.updated_at = datetime.now()
            meta = dict(order.metadata or {})
            meta["last_exchange_sync"] = datetime.now().isoformat()
            meta["exchange_sync_symbol"] = sym
            order.metadata = meta

        return changed

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
        refreshed = 0
        stale_cancelled = 0
        live_index_keys = set()
        raw_row_count = len(positions or [])

        for p in positions or []:
            try:
                if not isinstance(p, dict):
                    continue
                sz = float(p.get("size", 0) or 0)
                if abs(sz) < 1e-12:
                    continue
                sym = self._canonical_symbol_from_position(p)
                if not sym:
                    continue
                side = self._resolved_side_from_position(p)
                inst_id = str(p.get("instId") or "").strip()
                if inst_id:
                    live_index_keys.add(self._build_pos_key(inst_id, side))
                else:
                    live_index_keys.add(self._normalize_any_key(f"{sym}|{side}"))
            except Exception:
                continue

        live_norm = {self._normalize_any_key(k) for k in live_index_keys}

        # 清理本地已不存在于交易所的活动跟踪单，避免历史脏数据长期残留。
        for oid, order in list(self.orders.items()):
            try:
                if order.status != StopLossTakeProfitStatus.ACTIVE:
                    continue
                idx_key = (order.metadata or {}).get("index_key") or f"{order.symbol}|{order.side}"
                idx_key = self._normalize_any_key(idx_key)
                if idx_key not in live_norm:
                    order.status = StopLossTakeProfitStatus.CANCELLED
                    order.trigger_reason = "stale_not_in_exchange"
                    order.updated_at = datetime.now()
                    for vk in self._order_index_keys_to_clear(order):
                        if self.order_index.get(vk) == oid:
                            del self.order_index[vk]
                    stale_cancelled += 1
            except Exception:
                continue

        for p in positions or []:
            try:
                if not isinstance(p, dict):
                    continue
                sz = float(p.get("size", 0) or 0)
                if abs(sz) < 1e-12:
                    continue
                sym = self._canonical_symbol_from_position(p)
                if not sym:
                    continue
                side = self._resolved_side_from_position(p)
                # 优先使用 avgPx（平均开仓价），其次 entry_price，最后用 mark_px（标记价格）
                entry = float(p.get("avgPx", 0) or p.get("entry_price", 0) or 0)
                if entry <= 0:
                    entry = float(p.get("mark_px", 0) or 0)
                inst_id = str(p.get("instId") or "").strip()
                canonical, variants, meta = await self._resolve_canonical_and_variants(
                    symbol=sym,
                    side=side,
                    metadata={"source": "exchange_sync", "instId": inst_id, "posSide": side},
                )

                oid = None
                for cand in variants + [canonical]:
                    oid = self.order_index.get(self._normalize_any_key(cand))
                    if oid:
                        break
                if oid:
                    existing = self.orders.get(oid)
                    if existing and existing.status == StopLossTakeProfitStatus.ACTIVE:
                        try:
                            if self._refresh_active_order_from_exchange_position(existing, p, sym, side):
                                refreshed += 1
                        except Exception as e:
                            logger.debug("sync_open_positions: 刷新本地跟踪失败 %s: %s", canonical, e)
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
                    logger.warning(f"sync_open_positions: 跳过 {canonical}（无有效入场价/标记价）")
                    continue

                # max_orders 表示「活跃 SLTP 跟踪」上限；历史 triggered/cancelled 仍留在 self.orders 供统计，
                # 若用 len(self.orders) 会误报已满并拒绝为当前持仓登记跟踪。
                active_n = self._count_active_orders()
                if active_n >= self.config.max_orders:
                    logger.warning(
                        "sync_open_positions: 已达 max_orders（仅统计 ACTIVE=%s，总记录=%s），停止新建同步",
                        active_n,
                        len(self.orders),
                    )
                    break

                await self.create_order(
                    sym,
                    side,
                    entry,
                    abs(sz),
                    metadata=meta,
                )
                synced += 1
            except Exception as e:
                logger.warning(f"sync_open_positions: 处理单条持仓失败: {e}")

        if stale_cancelled > 0 or refreshed > 0:
            await self._save_orders()
        logger.info(
            f"📌 交易所持仓→止盈止损跟踪: 新建 {synced}，已存在跳过 {skipped}（其中已对齐刷新 {refreshed}），"
            f"清理陈旧 {stale_cancelled}，live_keys={len(live_index_keys)} raw_rows={raw_row_count}"
        )
        return {
            "synced": synced,
            "skipped": skipped,
            "refreshed": refreshed,
            "stale_cancelled": stale_cancelled,
            "live_index_keys": sorted(live_index_keys),
            "raw_row_count": raw_row_count,
        }
    
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
        canonical, variants, meta = await self._resolve_canonical_and_variants(
            symbol=symbol,
            side=side,
            metadata=metadata,
        )

        await self._cancel_active_orders_for_index_key(canonical)

        order_id = self._generate_order_id(canonical)
        
        sl_config = stop_loss_config or StopLossConfig()
        tp_config = take_profit_config or TakeProfitConfig()

        if self.config.trailing_only_mode and getattr(
            self.config, "trailing_only_coerce_inputs", True
        ):
            off0 = float(self.config.initial_trailing_offset)
            sl_config = StopLossConfig(
                stop_type=StopType.TRAILING,
                stop_value=off0,
                trailing_offset=off0,
            )
            tp_config = TakeProfitConfig(tp_type=TakeProfitType.NONE, tp_value=0.0)
        elif (
            self.config.trailing_only_mode
            and stop_loss_config is None
            and take_profit_config is None
        ):
            off0 = float(self.config.initial_trailing_offset)
            sl_config = StopLossConfig(
                stop_type=StopType.TRAILING,
                stop_value=off0,
                trailing_offset=off0,
            )
            tp_config = TakeProfitConfig(tp_type=TakeProfitType.NONE, tp_value=0.0)
        
        stop_loss_price = self._calculate_stop_loss_price(
            entry_price, side, sl_config
        )
        
        take_profit_price = self._calculate_take_profit_price(
            entry_price, side, tp_config
        )

        stop_loss_price, take_profit_price = self._sanitize_sl_tp_vs_entry(
            entry_price, side, stop_loss_price, take_profit_price, sl_config, tp_config
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
            trailing_stop_offset=float(
                getattr(sl_config, "trailing_offset", None)
                or sl_config.stop_value
                or self.config.initial_trailing_offset
            ),
            highest_price=entry_price if side == "long" else 0,
            lowest_price=entry_price if side == "short" else float('inf'),
            time_limit=time_limit,
            metadata=meta
        )
        if self.config.trailing_active_on_open and self.config.enable_trailing_stop:
            order.trailing_stop_activated = True
            order.trailing_stop_offset = float(self.config.initial_trailing_offset)
        
        self.orders[order_id] = order
        for k in variants + [canonical]:
            self.order_index[self._normalize_any_key(k)] = order_id
        self._stats["total_orders"] += 1
        
        await self._save_orders()

        # Trade domain event (best-effort): reserve for frontend/TG fanout
        try:
            mc = getattr(self, "_main_controller", None) or getattr(self, "main_controller", None)
            hub = getattr(mc, "trade_event_hub", None) if mc else None
            if hub and hasattr(hub, "publish_position_update"):
                trace_id = (meta.get("trace_id") or meta.get("traceId") or None) or str(uuid.uuid4())
                await hub.publish_position_update(
                    trace_id=str(trace_id),
                    source="stop_loss_take_profit",
                    symbol=str(symbol),
                    side=str(side),
                    kind="sltp.create",
                    data={
                        "index_key": meta.get("index_key") or canonical,
                        "order_id": order_id,
                        "entry_price": float(entry_price),
                        "stop_loss_price": float(stop_loss_price),
                        "take_profit_price": float(take_profit_price) if take_profit_price is not None else None,
                        "stop_loss_type": getattr(sl_config.stop_type, "value", str(sl_config.stop_type)),
                        "take_profit_type": getattr(tp_config.tp_type, "value", str(tp_config.tp_type)),
                        "quantity": float(quantity),
                        "metadata": dict(meta),
                    },
                    tg_message=(
                        f"🧷 SLTP 建立\n{symbol} {side}\nsl={stop_loss_price:.4g} tp="
                        f"{(take_profit_price if take_profit_price is not None else 'trailing-only')}\ntrace_id={trace_id}"
                    ),
                )
        except Exception:
            pass
        
        logger.info(f"✅ 创建止盈止损订单: {symbol} {side}")
        logger.info(f"   入场价: {entry_price:.4f}")
        if sl_config.stop_type == StopType.PERCENTAGE:
            logger.info(f"   止损价: {stop_loss_price:.4f} ({sl_config.stop_value*100:.1f}%)")
        else:
            logger.info(f"   止损价: {stop_loss_price:.4f} ({sl_config.stop_type.value})")
        if take_profit_price is None or tp_config.tp_type == TakeProfitType.NONE:
            logger.info("   止盈价: (无固定止盈，移动止损/追踪出场)")
        elif tp_config.tp_type == TakeProfitType.PERCENTAGE:
            logger.info(f"   止盈价: {take_profit_price:.4f} ({tp_config.tp_value*100:.1f}%)")
        else:
            logger.info(f"   止盈价: {take_profit_price:.4f} ({tp_config.tp_type.value})")
        
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

    def _sanitize_sl_tp_vs_entry(
        self,
        entry_price: float,
        side: str,
        stop_loss_price: float,
        take_profit_price: Optional[float],
        sl_config: StopLossConfig,
        tp_config: TakeProfitConfig,
    ) -> Tuple[float, Optional[float]]:
        """
        强制止损/止盈相对入场方向正确：
        - 多：止损 < 入场 < 止盈
        - 空：止盈 < 入场 < 止损
        外部若传入 FIXED 绝对价错误（常见于突破策略误用），按默认百分比回退。
        """
        ep = float(entry_price or 0)
        side_l = str(side or "").lower()
        if ep <= 0 or not math.isfinite(ep):
            return stop_loss_price, take_profit_price
        sl = float(stop_loss_price)
        tp = float(take_profit_price) if take_profit_price is not None else None
        eps = max(ep * 1e-7, 1e-9)
        # FIXED 时 stop_value/tp_value 为绝对价，不能当百分比用
        if sl_config.stop_type == StopType.PERCENTAGE:
            sl_pct = min(0.25, max(0.003, float(sl_config.stop_value or 0.03)))
        else:
            sl_pct = 0.03
        if tp_config.tp_type == TakeProfitType.PERCENTAGE:
            tp_pct = min(0.35, max(0.005, float(tp_config.tp_value or 0.06)))
        else:
            tp_pct = 0.06
        fixed = False
        if tp_config.tp_type == TakeProfitType.NONE:
            tp = None
        if side_l == "long":
            if (not math.isfinite(sl)) or sl >= ep - eps:
                sl = ep * (1 - sl_pct)
                fixed = True
            if tp is not None:
                if (not math.isfinite(tp)) or tp <= ep + eps:
                    tp = ep * (1 + tp_pct)
                    fixed = True
        elif side_l == "short":
            if (not math.isfinite(sl)) or sl <= ep + eps:
                sl = ep * (1 + sl_pct)
                fixed = True
            if tp is not None:
                if (not math.isfinite(tp)) or tp >= ep - eps:
                    tp = ep * (1 - tp_pct)
                    fixed = True
        if fixed:
            logger.warning(
                "SLTP: 止损/止盈与方向不一致已按百分比修正 side=%s entry=%.8g sl->%.8g tp->%s",
                side_l,
                ep,
                sl,
                f"{tp:.8g}" if tp is not None else "None",
            )
        return sl, tp
    
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

        elif config.stop_type == StopType.TRAILING:
            off = float(getattr(config, "trailing_offset", None) or config.stop_value or 0.023)
            # 限制偏移量在合理范围内：0.5%到25%
            off = min(0.25, max(0.005, off))
            if side == "long":
                return entry_price * (1.0 - off)
            return entry_price * (1.0 + off)
        
        return entry_price * 0.97 if side == "long" else entry_price * 1.03
    
    def _calculate_take_profit_price(
        self,
        entry_price: float,
        side: str,
        config: TakeProfitConfig
    ) -> Optional[float]:
        """计算止盈价格；NONE 表示不设固定止盈。"""
        if config.tp_type == TakeProfitType.NONE:
            return None

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
        key = self._normalize_any_key(index_key or symbol)
        order_id = self.order_index.get(key)
        if not order_id and key and (not self._is_pos_key(key)) and "|" not in key:
            # legacy fallback: symbol only
            for sd in ("long", "short"):
                for cand in self._index_key_lookup_variants(key, sd):
                    order_id = self.order_index.get(self._normalize_any_key(cand))
                    if order_id:
                        break
                if order_id:
                    break
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
        else:
            if current_price < order.lowest_price:
                order.lowest_price = current_price

        await self._apply_layered_trailing_take_profit(order, current_price)
        await self._check_layered_partial_take_profit(order, current_price)

        await self._apply_profit_tier2_trailing(order, current_price)
        await self._update_trailing_stop(order, current_price)
        
        await self._check_breakeven(order, current_price)
        
        triggered = await self._check_stop_loss_take_profit(order, current_price)
        
        await self._check_time_stop(order)
        
        return triggered

    async def _apply_layered_trailing_take_profit(self, order: StopLossTakeProfitOrder, current_price: float) -> None:
        """按峰值浮盈分层调整回撤带宽（移动止盈层）。"""
        if not bool(getattr(self.config, "layered_trailing_tp_enable", True)):
            return
        levels = list(getattr(self.config, "layered_trailing_tp_drawdown_levels", []) or [])
        if not levels:
            return
        try:
            levels = sorted(
                [(float(p), float(dd)) for p, dd in levels if float(p) > 0 and float(dd) > 0],
                key=lambda x: x[0],
            )
        except Exception:
            return
        if not levels:
            return

        # 峰值浮盈（相对入场）
        if order.side == "long":
            peak_pnl = (float(order.highest_price or current_price) - float(order.entry_price)) / max(1e-12, float(order.entry_price))
        else:
            peak_pnl = (float(order.entry_price) - float(order.lowest_price or current_price)) / max(1e-12, float(order.entry_price))

        target_dd = None
        for pnl_thr, dd in levels:
            if peak_pnl >= pnl_thr:
                target_dd = dd
        if target_dd is None:
            return
        old_off = float(order.trailing_stop_offset or self.config.initial_trailing_offset)
        new_off = min(max(float(target_dd), float(self.config.min_trailing_offset)), float(self.config.max_trailing_offset))
        if abs(new_off - old_off) < 1e-9:
            return

        order.trailing_stop_offset = new_off
        meta = dict(order.metadata or {})
        meta["layered_trailing_peak_pnl"] = float(peak_pnl)
        meta["layered_trailing_offset"] = float(new_off)
        meta["layered_trailing_last_at"] = datetime.now().isoformat()
        order.metadata = meta
        logger.info(
            "📐 分层移动止盈调整: %s peak_pnl=%.2f%% trailing_off %.4f -> %.4f",
            order.symbol,
            peak_pnl * 100.0,
            old_off,
            new_off,
        )

    async def _check_layered_partial_take_profit(self, order: StopLossTakeProfitOrder, current_price: float) -> None:
        """分层固定止盈（部分平仓锁利）。"""
        if not bool(getattr(self.config, "enable_partial_tp", False)):
            return
        if not bool(getattr(self.config, "layered_partial_tp_enable", True)):
            return
        if float(order.remaining_quantity or 0) <= 1e-12:
            return
        levels = list(getattr(self.config, "layered_partial_tp_levels", []) or [])
        if not levels:
            return
        try:
            levels = sorted(
                [(float(p), float(r)) for p, r in levels if float(p) > 0 and float(r) > 0],
                key=lambda x: x[0],
            )
        except Exception:
            return
        if not levels:
            return

        pnl_percent = self._calculate_pnl_percent(order, current_price)
        if pnl_percent <= 0:
            return
        meta = dict(order.metadata or {})
        done = set(float(x) for x in (meta.get("layered_partial_done_levels") or []))

        for level_percent, level_ratio in levels:
            if level_percent in done:
                continue
            if pnl_percent < level_percent:
                continue
            base_qty = float(order.quantity or 0)
            close_qty = min(base_qty * level_ratio, float(order.remaining_quantity or 0))
            if close_qty <= 1e-12:
                done.add(level_percent)
                continue

            # 实盘部分平仓：通过 ExecutionGateway/Exchange 真正减仓，避免仅本地变更造成漂移。
            ok = await self._execute_exchange_close_on_trigger(
                order,
                reason=f"partial_take_profit_{int(level_percent * 100)}",
                close_size=close_qty,
            )
            if not ok:
                logger.warning(
                    "⚠️ 分层止盈执行失败，保留仓位不标记已完成: %s level=%.2f%% qty=%.6f",
                    order.symbol,
                    level_percent * 100.0,
                    close_qty,
                )
                continue

            order.remaining_quantity = max(0.0, float(order.remaining_quantity or 0) - close_qty)
            order.partial_tp_executed.append((level_percent, close_qty))
            self._stats["partial_tp_executed"] += 1
            done.add(level_percent)
            meta["layered_partial_done_levels"] = sorted(list(done))
            meta["layered_partial_last_at"] = datetime.now().isoformat()
            order.metadata = meta
            logger.info(
                "🎯 分层止盈执行: %s level=%.2f%% close=%.2f%% qty=%.6f remain=%.6f",
                order.symbol,
                level_percent * 100.0,
                level_ratio * 100.0,
                close_qty,
                float(order.remaining_quantity or 0),
            )
            await self._notify_callbacks("on_partial_tp", order, level_percent, close_qty)

            if float(order.remaining_quantity or 0) <= 1e-12:
                order.status = StopLossTakeProfitStatus.TRIGGERED
                order.triggered_at = datetime.now()
                order.trigger_reason = "partial_take_profit_final"
                break

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
                    whale_blk = (snap.get("大资金与大户监控") or {}) if isinstance(snap, dict) else {}
                    whale_count = int(whale_blk.get("链上大户活跃条数") or 0)
                    high_risk_positions = int(
                        ((snap.get("渠道A_交易所实时执行数据") or {}).get("liquidation_proxy") or {}).get("high_risk_positions") or 0
                    )
                    whale_risk = whale_count >= 6 or high_risk_positions >= 1
                except Exception:
                    pass

            # Prefer MarketIntelligenceEngine for bias/confidence (analysis is NOT owned by data hub).
            try:
                if mc and getattr(mc, "market_intelligence", None) and hasattr(mc.market_intelligence, "get_symbol_view"):
                    view = await mc.market_intelligence.get_symbol_view(order.symbol, include_snapshot=False)
                    ai_bias = str(getattr(view, "action_bias", "") or "").lower() or None
                    ai_confidence = getattr(view, "confidence", None)
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

            mom_short = 0.0
            if len(ph) >= 3:
                base_m = max(1e-9, abs(float(ph[-3])))
                mom_short = (float(ph[-1]) - float(ph[-3])) / base_m
            neutral_momentum = False
            if bool(getattr(self.config, "trailing_momentum_adjust_enable", True)):
                nt_n = float(getattr(self.config, "trailing_momentum_trend_neutral_abs", 0.002) or 0.002)
                ns_n = float(getattr(self.config, "trailing_momentum_short_neutral_abs", 0.0015) or 0.0015)
                neutral_momentum = abs(float(trend)) < nt_n and abs(float(mom_short)) < ns_n

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
                tp = float(order.take_profit_price) if order.take_profit_price is not None else None
                vol_thr = float(self.config.volatility_tighten_threshold)
                risk_tighten_trail = bool(whale_risk) or (
                    unified_quality is not None and unified_quality < 0.5
                ) or (spread_bps is not None and spread_bps > max(25.0, spread_guard))
                # 追踪偏移：风险类始终可收紧；波动/顺势放宽仅在「非中性动能」时调整，中性则保持带宽
                off0 = float(order.trailing_stop_offset or self.config.initial_trailing_offset)
                if risk_tighten_trail or (ai_confidence is not None and ai_confidence >= 0.65 and ai_bias and (
                    (order.side == "long" and ai_bias in {"sell", "short"})
                    or (order.side == "short" and ai_bias in {"buy", "long"})
                )):
                    order.trailing_stop_offset = max(
                        float(self.config.min_trailing_offset),
                        off0 * float(getattr(self.config, "trailing_momentum_tighten_factor", 0.92) or 0.92),
                    )
                elif volatility >= vol_thr and (not neutral_momentum):
                    order.trailing_stop_offset = max(
                        float(self.config.min_trailing_offset),
                        off0 * (1.0 - tighten_ratio * 0.5),
                    )
                elif favorable and (not neutral_momentum):
                    order.trailing_stop_offset = min(
                        float(self.config.max_trailing_offset),
                        off0 * (1.0 + tp_extend_ratio * 0.3),
                    )
                elif not neutral_momentum:
                    nt_n = float(getattr(self.config, "trailing_momentum_trend_neutral_abs", 0.002) or 0.002)
                    ns_n = float(getattr(self.config, "trailing_momentum_short_neutral_abs", 0.0015) or 0.0015)
                    weak = (order.side == "long" and (float(trend) < -nt_n or float(mom_short) < -ns_n)) or (
                        order.side == "short" and (float(trend) > nt_n or float(mom_short) > ns_n)
                    )
                    if weak:
                        order.trailing_stop_offset = max(
                            float(self.config.min_trailing_offset),
                            off0 * float(getattr(self.config, "trailing_momentum_tighten_factor", 0.92) or 0.92),
                        )
                    elif (
                        (order.side == "long" and float(trend) >= float(self.config.trend_extend_threshold) and float(mom_short) > ns_n)
                        or (order.side == "short" and float(trend) <= -float(self.config.trend_extend_threshold) and float(mom_short) < -ns_n)
                    ):
                        order.trailing_stop_offset = min(
                            float(self.config.max_trailing_offset),
                            off0 * float(getattr(self.config, "trailing_momentum_loosen_factor", 1.05) or 1.05),
                        )
                if order.side == "long":
                    if adverse and sl > 0:
                        # 逆风时向下移动止损保护本金（不能向上移动到现价！）
                        target_sl = sl - (sl - current_price) * tighten_ratio
                        if target_sl > 0 and target_sl < sl:
                            order.stop_loss_price = target_sl
                            changed = True
                    elif favorable and tp is not None and tp > 0:
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
                    elif favorable and tp is not None and tp > 0:
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
                    float(order.take_profit_price or 0) if order.take_profit_price is not None else -1.0,
                    float(order.trailing_stop_offset or 0.0),
                    f"{spread_bps:.2f}" if spread_bps is not None else "N/A",
                    f"{depth_imb:.3f}" if depth_imb is not None else "N/A",
                    float(trend),
                    float(volatility),
                )
        except Exception as e:
            logger.debug(f"动态调整止盈止损失败: {e}")

    async def _apply_profit_tier2_trailing(self, order: StopLossTakeProfitOrder, current_price: float) -> None:
        """浮盈达到二档阈值后，将移动带宽收紧为 tier2（默认 +50% 浮盈 → 0.5% 带宽）。"""
        thr = float(self.config.profit_tier2_pnl_threshold or 0.0)
        if thr <= 0:
            return
        pnl = self._calculate_pnl_percent(order, current_price)
        if pnl < thr:
            return
        meta = dict(order.metadata or {})
        if meta.get("tier2_trailing_applied"):
            return
        t2 = float(self.config.tier2_trailing_offset)
        t2 = min(max(t2, float(self.config.min_trailing_offset)), float(self.config.max_trailing_offset))
        old_off = float(order.trailing_stop_offset or t2)
        order.trailing_stop_offset = t2
        meta["tier2_trailing_applied"] = True
        meta["tier2_trailing_offset"] = t2
        order.metadata = meta
        logger.info(
            "📐 %s 二档移动止损: 浮盈=%.2f%% >= %.2f%%，带宽 %.4f -> %.4f",
            order.symbol,
            pnl * 100.0,
            thr * 100.0,
            old_off,
            t2,
        )

    async def _update_trailing_stop(self, order: StopLossTakeProfitOrder, current_price: float):
        """更新移动止损（每 tick 根据峰值/谷值与当前带宽重算止损价）。"""
        if not self.config.enable_trailing_stop:
            return

        pnl_percent = self._calculate_pnl_percent(order, current_price)

        if not order.trailing_stop_activated:
            if self.config.trailing_active_on_open:
                order.trailing_stop_activated = True
            elif pnl_percent >= float(self.config.trailing_stop_trigger or 0):
                order.trailing_stop_activated = True
                logger.info(f"📊 {order.symbol} 激活移动止损 (盈利 {pnl_percent*100:.1f}%)")
                if self._enhanced_monitoring:
                    await self._enhanced_monitoring.update_metric(
                        "trailing_stop_activated",
                        1,
                        {"symbol": order.symbol},
                    )

        if not order.trailing_stop_activated:
            return

        off = float(order.trailing_stop_offset or self.config.initial_trailing_offset)
        off = min(max(off, float(self.config.min_trailing_offset)), float(self.config.max_trailing_offset))

        if order.side == "long":
            hp = float(order.highest_price or 0)
            if hp <= 0:
                hp = float(order.entry_price or current_price)
            new_stop = hp * (1.0 - off)
            cur_sl = float(order.stop_loss_price or 0)
            if new_stop > cur_sl or cur_sl <= 0 or not math.isfinite(cur_sl):
                old_stop = order.stop_loss_price
                order.stop_loss_price = new_stop
                self._stats["trailing_updates"] += 1
                logger.info(f"📈 {order.symbol} 移动止损更新: {old_stop} -> {new_stop:.4f}")
                await self._notify_callbacks("on_trailing_update", order, old_stop, new_stop)
        else:
            lp = float(order.lowest_price) if order.lowest_price is not None else float("inf")
            if (not math.isfinite(lp)) or lp <= 0:
                lp = float(order.entry_price or current_price)
            new_stop = lp * (1.0 + off)
            cur_sl = float(order.stop_loss_price or 0)
            if (new_stop < cur_sl) or cur_sl <= 0 or not math.isfinite(cur_sl):
                old_stop = order.stop_loss_price
                order.stop_loss_price = new_stop
                self._stats["trailing_updates"] += 1
                logger.info(f"📉 {order.symbol} 移动止损更新: {old_stop} -> {new_stop:.4f}")
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

    def _pending_close_due(self, order: StopLossTakeProfitOrder) -> bool:
        if order.status != StopLossTakeProfitStatus.PENDING_CLOSE:
            return False
        meta = order.metadata or {}
        ts = meta.get("pending_close_next_ts")
        try:
            tsf = float(ts) if ts is not None else 0.0
        except Exception:
            tsf = 0.0
        return time.time() >= tsf

    def _schedule_pending_close_retry(self, order: StopLossTakeProfitOrder, *, error: str = "") -> None:
        meta = dict(order.metadata or {})
        attempts = int(meta.get("pending_close_attempts", 0) or 0) + 1
        meta["pending_close_attempts"] = attempts
        base = float(getattr(self.config, "pending_close_backoff_base_sec", 2.0) or 2.0)
        cap = float(getattr(self.config, "pending_close_backoff_cap_sec", 120.0) or 120.0)
        delay = min(cap, base * (2 ** max(0, attempts - 1)))
        meta["pending_close_next_ts"] = time.time() + float(delay)
        if error:
            meta["pending_close_last_error"] = str(error)[:500]
        order.metadata = meta
        order.updated_at = datetime.now()

    async def _attempt_pending_close(self, order: StopLossTakeProfitOrder, reason: str) -> bool:
        ok = await self._execute_exchange_close_on_trigger(order, reason)
        if ok:
            order.status = StopLossTakeProfitStatus.TRIGGERED
            order.updated_at = datetime.now()
            meta = dict(order.metadata or {})
            meta["pending_close_done"] = True
            meta.pop("pending_close_next_ts", None)
            order.metadata = meta
            return True
        self._schedule_pending_close_retry(order, error="close_failed")
        return False
    
    async def _trigger_stop_loss(
        self,
        order: StopLossTakeProfitOrder,
        current_price: float
    ) -> StopLossTakeProfitOrder:
        """触发止损"""
        order.status = StopLossTakeProfitStatus.PENDING_CLOSE
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

        # Trade domain event (best-effort)
        try:
            mc = getattr(self, "_main_controller", None) or getattr(self, "main_controller", None)
            hub = getattr(mc, "trade_event_hub", None) if mc else None
            if hub and hasattr(hub, "publish_position_update"):
                trace_id = ((order.metadata or {}).get("trace_id") or (order.metadata or {}).get("traceId")) or str(uuid.uuid4())
                await hub.publish_position_update(
                    trace_id=str(trace_id),
                    source="stop_loss_take_profit",
                    symbol=str(order.symbol),
                    side=str(order.side),
                    kind="sltp.trigger",
                    data={
                        "trigger_reason": "stop_loss",
                        "entry_price": float(order.entry_price or 0),
                        "stop_loss_price": float(order.stop_loss_price or 0),
                        "take_profit_price": float(order.take_profit_price or 0),
                        "current_price": float(current_price or 0),
                        "pnl_percent": float(pnl_percent or 0),
                        "order_id": getattr(order, "order_id", None),
                        "index_key": (order.metadata or {}).get("index_key"),
                    },
                    tg_message=f"🧯 止损触发\n{order.symbol} {order.side}\npx={current_price:.4g} pnl={pnl_percent*100:.2f}%\ntrace_id={trace_id}",
                )
        except Exception:
            pass

        # Persist a structured risk_event memory (single source: MemoryGateway)
        try:
            mc = getattr(self, "main_controller", None)
            mg = getattr(mc, "memory_gateway", None) if mc else None
            if mg:
                await mg.add_memory(
                    memory_type="risk_event",
                    content=f"SL触发: {order.symbol} side={order.side} entry={order.entry_price} sl={order.stop_loss_price} px={current_price} pnl%={pnl_percent*100:.2f}",
                    summary=f"🧯 止损触发 {order.symbol} {order.side}",
                    metadata=base_metadata(
                        source_module="stop_loss_take_profit",
                        kind="sltp_stop_loss_triggered",
                        symbol=order.symbol,
                        extra={
                            "side": order.side,
                            "entry_price": order.entry_price,
                            "stop_loss_price": order.stop_loss_price,
                            "current_price": current_price,
                            "pnl_percent": pnl_percent,
                            "trigger_reason": order.trigger_reason,
                            "triggered_at": order.triggered_at.isoformat() if order.triggered_at else None,
                            "idempotency_key": (
                                f"sltp:{order.symbol}:stop_loss:"
                                f"{order.triggered_at.isoformat() if order.triggered_at else ''}"
                            ),
                            "order": order.to_dict() if hasattr(order, "to_dict") else {},
                        },
                    ),
                    importance=0.95,
                    source_module="stop_loss_take_profit",
                    tags=tags(kind_tag("sltp"), kind_tag("stop_loss"), symbol_tag(order.symbol)),
                )
        except Exception as e:
            logger.debug(f"写入止损触发记忆失败: {e}")

        await self._attempt_pending_close(order, "stop_loss")
        
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
            # Real partial TP requires a real partial close on exchange (via S1). The legacy behavior only
            # mutates local remaining_quantity and can drift from real positions, so we disable it in live.
            if getattr(self.config, "execute_exchange_on_trigger", True):
                logger.warning(
                    "⚠️ %s PARTIAL TP is disabled in live mode (execute_exchange_on_trigger=true); falling back to full TP close to avoid drift",
                    order.symbol,
                )
            else:
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
            # if execute_exchange_on_trigger=false and partials depleted the position, continue to full close below.
        
        order.status = StopLossTakeProfitStatus.PENDING_CLOSE
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

        # Trade domain event (best-effort)
        try:
            mc = getattr(self, "_main_controller", None) or getattr(self, "main_controller", None)
            hub = getattr(mc, "trade_event_hub", None) if mc else None
            if hub and hasattr(hub, "publish_position_update"):
                trace_id = ((order.metadata or {}).get("trace_id") or (order.metadata or {}).get("traceId")) or str(uuid.uuid4())
                await hub.publish_position_update(
                    trace_id=str(trace_id),
                    source="stop_loss_take_profit",
                    symbol=str(order.symbol),
                    side=str(order.side),
                    kind="sltp.trigger",
                    data={
                        "trigger_reason": "take_profit",
                        "entry_price": float(order.entry_price or 0),
                        "stop_loss_price": float(order.stop_loss_price or 0),
                        "take_profit_price": float(order.take_profit_price or 0),
                        "current_price": float(current_price or 0),
                        "pnl_percent": float(pnl_percent or 0),
                        "order_id": getattr(order, "order_id", None),
                        "index_key": (order.metadata or {}).get("index_key"),
                    },
                    tg_message=f"🎯 止盈触发\n{order.symbol} {order.side}\npx={current_price:.4g} pnl={pnl_percent*100:.2f}%\ntrace_id={trace_id}",
                )
        except Exception:
            pass

        # Persist a structured risk_event memory (single source: MemoryGateway)
        try:
            mc = getattr(self, "main_controller", None)
            mg = getattr(mc, "memory_gateway", None) if mc else None
            if mg:
                await mg.add_memory(
                    memory_type="risk_event",
                    content=f"TP触发: {order.symbol} side={order.side} entry={order.entry_price} tp={order.take_profit_price} px={current_price} pnl%={pnl_percent*100:.2f}",
                    summary=f"🎯 止盈触发 {order.symbol} {order.side}",
                    metadata=base_metadata(
                        source_module="stop_loss_take_profit",
                        kind="sltp_take_profit_triggered",
                        symbol=order.symbol,
                        extra={
                            "side": order.side,
                            "entry_price": order.entry_price,
                            "take_profit_price": order.take_profit_price,
                            "current_price": current_price,
                            "pnl_percent": pnl_percent,
                            "trigger_reason": order.trigger_reason,
                            "triggered_at": order.triggered_at.isoformat() if order.triggered_at else None,
                            "idempotency_key": (
                                f"sltp:{order.symbol}:take_profit:"
                                f"{order.triggered_at.isoformat() if order.triggered_at else ''}"
                            ),
                            "order": order.to_dict() if hasattr(order, "to_dict") else {},
                        },
                    ),
                    importance=0.9,
                    source_module="stop_loss_take_profit",
                    tags=tags(kind_tag("sltp"), kind_tag("take_profit"), symbol_tag(order.symbol)),
                )
        except Exception as e:
            logger.debug(f"写入止盈触发记忆失败: {e}")

        await self._attempt_pending_close(order, "take_profit")
        
        await self._save_orders()
        
        return order
    
    async def _check_time_stop(self, order: StopLossTakeProfitOrder):
        """检查时间止损"""
        if not order.time_limit:
            return
        
        if datetime.now() >= order.time_limit:
            order.status = StopLossTakeProfitStatus.PENDING_CLOSE
            order.triggered_at = datetime.now()
            order.trigger_reason = "time_stop"
            self._stats["time_stop_triggered"] += 1
            
            logger.info(f"⏰ {order.symbol} 触发时间止损 (持仓超时)")
            
            await self._notify_callbacks("on_time_stop", order)

            await self._attempt_pending_close(order, "time_stop")
            
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
        order_id = None
        key = str(symbol or "").strip()
        if self._is_pos_key(key) or "|" in key:
            order_id = self.order_index.get(self._normalize_any_key(key))
        if not order_id and key:
            for sd in ("long", "short"):
                for cand in self._index_key_lookup_variants(key, sd):
                    order_id = self.order_index.get(self._normalize_any_key(cand))
                    if order_id:
                        break
                if order_id:
                    break
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
        order_id = None
        key = str(symbol or "").strip()
        if self._is_pos_key(key) or "|" in key:
            order_id = self.order_index.get(self._normalize_any_key(key))
        if not order_id and key:
            for sd in ("long", "short"):
                for cand in self._index_key_lookup_variants(key, sd):
                    order_id = self.order_index.get(self._normalize_any_key(cand))
                    if order_id:
                        break
                if order_id:
                    break
        if not order_id:
            return False
        
        order = self.orders.get(order_id)
        if not order:
            return False
        
        order.status = StopLossTakeProfitStatus.CANCELLED
        order.updated_at = datetime.now()
        
        logger.info(f"❌ 取消止盈止损订单: {symbol}")

        for k in self._order_index_keys_to_clear(order):
            if self.order_index.get(k) == order_id:
                del self.order_index[k]
        
        await self._save_orders()
        
        return True
    
    async def get_order(self, symbol: str) -> Optional[StopLossTakeProfitOrder]:
        """获取止盈止损订单"""
        order_id = None
        key = str(symbol or "").strip()
        if self._is_pos_key(key) or "|" in key:
            order_id = self.order_index.get(self._normalize_any_key(key))
        if not order_id and key:
            for sd in ("long", "short"):
                for cand in self._index_key_lookup_variants(key, sd):
                    order_id = self.order_index.get(self._normalize_any_key(cand))
                    if order_id:
                        break
                if order_id:
                    break
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
            "total_orders_tracked": len(self.orders),
            "single_active_per_index": True,
        }
    
    async def _monitor_loop(self) -> None:
        """监控循环"""
        logger.info("止盈止损监控循环启动")
        
        while self._running:
            try:
                if not self._exchange:
                    await asyncio.sleep(self.config.check_interval)
                    continue

                # 周期性再同步交易所持仓 → SLTP，避免「仅启动同步一次」或重启后 drift
                if self.config.sync_exchange_positions_on_startup:
                    try:
                        now = time.time()
                        interval = float(getattr(self.config, "exchange_resync_interval_sec", 45) or 45)
                        if now - self._last_exchange_sync_ts >= interval:
                            await self.sync_open_positions_from_exchange()
                            self._last_exchange_sync_ts = now
                    except Exception as e:
                        logger.warning(f"周期持仓再同步失败: {e}")

                active_orders = await self.get_all_active_orders()

                # Retry pending-close orders (close-confirmation state machine)
                pending = [
                    o for o in self.orders.values()
                    if o.status == StopLossTakeProfitStatus.PENDING_CLOSE
                ]
                for order in pending:
                    try:
                        if not self._pending_close_due(order):
                            continue
                        attempts = int((order.metadata or {}).get("pending_close_attempts", 0) or 0)
                        max_r = int(getattr(self.config, "pending_close_max_retries", 6) or 6)
                        if attempts >= max_r:
                            logger.error(
                                "🚨 SLTP pending close exceeded max retries: %s %s order_id=%s attempts=%s",
                                order.symbol,
                                order.side,
                                getattr(order, "order_id", None),
                                attempts,
                            )
                            # keep scheduling with a long backoff to avoid tight loops
                            self._schedule_pending_close_retry(order, error="max_retries_exceeded")
                            await self._save_orders()
                            continue
                        await self._attempt_pending_close(order, str(order.trigger_reason or "pending_close"))
                        await self._save_orders()
                    except Exception as e:
                        logger.warning("SLTP pending close retry failed: %s", e)
                
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
                tp_type_raw = order_data.get("take_profit_type", "percentage")
                try:
                    tp_type_e = TakeProfitType(tp_type_raw)
                except Exception:
                    tp_type_e = TakeProfitType.PERCENTAGE
                sl_type_raw = order_data.get("stop_loss_type", "percentage")
                try:
                    sl_type_e = StopType(sl_type_raw)
                except Exception:
                    sl_type_e = StopType.PERCENTAGE
                order = StopLossTakeProfitOrder(
                    order_id=order_data["order_id"],
                    symbol=order_data["symbol"],
                    side=order_data["side"],
                    entry_price=order_data["entry_price"],
                    quantity=order_data["quantity"],
                    remaining_quantity=order_data["remaining_quantity"],
                    stop_loss_price=order_data.get("stop_loss_price"),
                    stop_loss_type=sl_type_e,
                    stop_loss_value=order_data.get("stop_loss_value", 0.03),
                    take_profit_price=order_data.get("take_profit_price"),
                    take_profit_type=tp_type_e,
                    take_profit_value=order_data.get("take_profit_value", 0.06),
                    trailing_stop_activated=order_data.get("trailing_stop_activated", False),
                    trailing_stop_offset=float(order_data.get("trailing_stop_offset") or 0.02),
                    highest_price=order_data.get("highest_price", 0),
                    lowest_price=order_data.get("lowest_price", float('inf')),
                    status=StopLossTakeProfitStatus(order_data.get("status", "active")),
                    created_at=datetime.fromisoformat(order_data["created_at"]) if order_data.get("created_at") else datetime.now(),
                    triggered_at=datetime.fromisoformat(order_data["triggered_at"]) if order_data.get("triggered_at") else None,
                    trigger_reason=order_data.get("trigger_reason"),
                    metadata=order_data.get("metadata") or {},
                )
                
                self.orders[oid] = order
                try:
                    meta = dict(order.metadata or {})
                    canonical = self._normalize_any_key(
                        meta.get("index_key")
                        or meta.get("position_key")
                        or f"{order.symbol}|{order.side}"
                    )
                    meta["index_key"] = canonical
                    meta.setdefault("legacy_symbol_key", self._normalize_index_key(f"{order.symbol}|{order.side}"))
                    order.metadata = meta
                    for k in self._order_index_keys_to_clear(order):
                        self.order_index[self._normalize_any_key(k)] = oid
                except Exception:
                    idx_key = self._normalize_any_key((order.metadata or {}).get("index_key") or f"{order.symbol}|{order.side}")
                    self.order_index[idx_key] = oid
            
            self._stats.update(data.get("stats", {}))
            
            logger.info(f"加载 {len(self.orders)} 个止盈止损订单")
            
        except Exception as e:
            logger.error(f"加载止盈止损订单失败: {e}")
    
    async def cleanup(self):
        """清理资源"""
        await self.stop()
        logger.info("止盈止损管理器清理完成")
