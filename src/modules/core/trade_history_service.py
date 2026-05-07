"""
统一交易历史服务 - 实现交易记录的完整生命周期管理

核心功能：
1. 交易记录的持久化存储（SQLite）
2. 实时交易记忆同步
3. 历史查询和统计分析
4. 对话上下文中的交易历史读取
5. AI智能复盘分析支持
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
import aiofiles
import pandas as pd
from src.modules.core.decision_contract import normalize_strategy_field

logger = logging.getLogger(__name__)

def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default if default is not None else 0.0)
        return float(value)
    except Exception:
        return float(default if default is not None else 0.0)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


@dataclass
class TradeRecord:
    """完整交易记录"""
    trade_id: str
    order_id: str
    symbol: str
    side: str  # buy/sell
    order_type: str  # market/limit
    quantity: float
    price: float
    cost: float = 0.0
    fee: float = 0.0
    pnl: float = 0.0
    pnl_percent: float = 0.0
    status: str = "filled"  # filled/cancelled/failed
    strategy: str = ""
    reasoning: str = ""  # AI决策理由
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    leverage: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeStatistics:
    """交易统计数据"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_fees: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    sharpe_ratio: float = 0.0
    avg_holding_time_hours: float = 0.0


class TradeHistoryService:
    """
    统一交易历史服务
    
    架构设计：
    1. SQLite持久层 - 可靠存储
    2. 记忆系统层 - AI可访问
    3. 缓存层 - 快速查询
    4. 实时同步层 - 即时更新
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # 数据库存储
        self.db_storage = None
        
        # 记忆系统集成
        self.memory_manager = None
        
        # 内存缓存（最近1000条）
        self._cache: List[TradeRecord] = []
        self._cache_max_size = self.config.get("cache_max_size", 1000)
        
        # 索引加速查询
        self._symbol_index: Dict[str, List[str]] = {}  # symbol -> [trade_ids]
        self._date_index: Dict[str, List[str]] = {}     # date -> [trade_ids]
        
        # 统计缓存（5分钟过期）
        self._stats_cache: Optional[TradeStatistics] = None
        self._stats_cache_time: Optional[datetime] = None
        self._stats_cache_ttl = timedelta(minutes=5)
        
        # 锁
        self._lock = asyncio.Lock()
        self._cache_bootstrapped = False
        
        # 配置路径
        base_path = Path(self.config.get("base_path", "/app/workspace/trade_history"))
        try:
            base_path.mkdir(parents=True, exist_ok=True)
            self.base_path = base_path
        except PermissionError:
            self.base_path = Path("/tmp/trade_history")
            self.base_path.mkdir(parents=True, exist_ok=True)
        
        # JSONL备份文件
        self.backup_file = self.base_path / "trades.jsonl"
        self._reflection_index_file = self.base_path / "reflection_index.json"
        self._reflection_seen: set[str] = set()
        self._load_reflection_index()
        
        logger.info(f"统一交易历史服务初始化完成，路径: {self.base_path}")

    def _load_reflection_index(self) -> None:
        try:
            if self._reflection_index_file.is_file():
                data = json.loads(self._reflection_index_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self._reflection_seen = {str(x) for x in data if str(x).strip()}
        except Exception:
            self._reflection_seen = set()

    def _save_reflection_index(self) -> None:
        try:
            arr = sorted(self._reflection_seen)[-5000:]
            self._reflection_index_file.write_text(json.dumps(arr, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    
    async def initialize(self) -> bool:
        """初始化服务"""
        try:
            # 连接数据库存储
            from src.modules.core.historical_data_storage import get_historical_storage
            self.db_storage = await get_historical_storage()
            logger.info("✅ 数据库存储已连接")
            
            # 加载缓存
            await self._load_cache_from_db()
            logger.info(f"✅ 已加载 {len(self._cache)} 条交易记录到缓存")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            return False
    
    async def set_memory_manager(self, memory_manager):
        """设置记忆管理器"""
        self.memory_manager = memory_manager
        logger.info("✅ 记忆管理器已连接")
    
    # ==================== 核心写入操作 ====================
    
    async def record_trade(self, trade: TradeRecord) -> bool:
        """
        记录一笔交易（核心方法）
        
        自动执行：
        1. 写入SQLite数据库
        2. 更新内存缓存
        3. 同步到记忆系统
        4. 追加到JSONL备份
        5. 更新索引
        """
        try:
            async with self._lock:
                # 基础幂等保护：避免同一 order_id/trade_id 重复入账（常见于重试回放场景）。
                if trade.order_id:
                    for existing in reversed(self._cache[-200:]):
                        if existing.order_id and existing.order_id == trade.order_id:
                            logger.info("⏭️ 跳过重复交易写入（order_id 已存在）: %s", trade.order_id)
                            return True
                if trade.trade_id:
                    for existing in reversed(self._cache[-200:]):
                        if existing.trade_id == trade.trade_id:
                            logger.info("⏭️ 跳过重复交易写入（trade_id 已存在）: %s", trade.trade_id)
                            return True

                # 1. 写入数据库
                if self.db_storage:
                    await self._save_to_database(trade)
                
                # 2. 更新缓存
                await self._update_cache(trade)
                
                # 3. 更新索引
                self._update_index(trade)
                
                # 4. 同步到记忆系统
                if self.memory_manager:
                    await self._sync_to_memory(trade)
                
                # 5. 备份到JSONL
                await self._backup_to_jsonl(trade)
                
                # 6. 清除统计缓存
                self._invalidate_stats_cache()
            
            logger.info(f"💾 交易已记录: {trade.trade_id} - {trade.symbol} {trade.side} {trade.quantity}@{trade.price}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 记录交易失败: {e}", exc_info=True)
            return False
    
    async def record_trade_dict(self, trade_dict: Dict[str, Any]) -> bool:
        """从字典创建并记录交易"""
        side_raw = str(trade_dict.get("side", "buy") or "buy").strip().lower()
        side_norm = {"long": "buy", "short": "sell"}.get(side_raw, side_raw or "buy")
        meta = dict(trade_dict.get("metadata") or {})
        strat_s = normalize_strategy_field(trade_dict, metadata=meta, default="unknown")
        if strat_s:
            meta.setdefault("strategy_id", strat_s)
        strategy_field = strat_s or "unknown"
        reason_s = str(
            trade_dict.get("reasoning")
            or trade_dict.get("reason")
            or meta.get("reason")
            or ""
        ).strip()
        trade = TradeRecord(
            trade_id=trade_dict.get("trade_id", f"trade_{datetime.now().timestamp()}"),
            order_id=trade_dict.get("order_id", ""),
            symbol=trade_dict.get("symbol", ""),
            side=side_norm,
            order_type=trade_dict.get("order_type", "market"),
            quantity=_to_float(trade_dict.get("quantity"), 0.0),
            price=_to_float(trade_dict.get("price"), 0.0),
            cost=_to_float(trade_dict.get("cost"), 0.0),
            fee=_to_float(trade_dict.get("fee"), 0.0),
            pnl=_to_float(trade_dict.get("pnl"), 0.0),
            pnl_percent=_to_float(trade_dict.get("pnl_percent"), 0.0),
            status=trade_dict.get("status", "filled"),
            strategy=strategy_field,
            reasoning=reason_s,
            stop_loss=_to_float(trade_dict.get("stop_loss"), 0.0) if trade_dict.get("stop_loss") is not None else None,
            take_profit=_to_float(trade_dict.get("take_profit"), 0.0) if trade_dict.get("take_profit") is not None else None,
            leverage=_to_int(trade_dict.get("leverage"), 1),
            timestamp=trade_dict.get("timestamp", datetime.now().isoformat()),
            metadata=meta,
        )
        return await self.record_trade(trade)

    async def apply_exchange_truth(
        self,
        *,
        order_id: str,
        symbol: str,
        exchange_pnl: Optional[float] = None,
        exchange_fee: Optional[float] = None,
        exchange_price: Optional[float] = None,
        source: str = "exchange_auto_sync",
    ) -> bool:
        """
        将交易所真值回填到本地交易记录（缓存 + SQLite）。
        仅按 order_id(+symbol) 匹配，避免误改。
        """
        oid = str(order_id or "").strip()
        sym = str(symbol or "").strip().upper()
        if not oid or not sym:
            return False
        changed = False
        async with self._lock:
            for tr in self._cache:
                if str(tr.order_id or "").strip() != oid:
                    continue
                if str(tr.symbol or "").strip().upper() != sym:
                    continue
                if exchange_pnl is not None:
                    tr.pnl = _to_float(exchange_pnl, tr.pnl)
                    changed = True
                if exchange_fee is not None:
                    tr.fee = _to_float(exchange_fee, tr.fee)
                    changed = True
                if exchange_price is not None and _to_float(exchange_price, 0.0) > 0:
                    tr.price = _to_float(exchange_price, tr.price)
                    changed = True
                if changed:
                    tr.metadata = dict(tr.metadata or {})
                    tr.metadata["truth_synced"] = True
                    tr.metadata["truth_source"] = str(source or "exchange_auto_sync")
                    tr.metadata["truth_synced_at"] = datetime.now().isoformat()
                    tr.metadata["pnl_estimated"] = False
            if changed:
                self._invalidate_stats_cache()
        if self.db_storage:
            suffix = f"\n[truth_sync:{datetime.now().isoformat()}]"
            rows_updated = await self.db_storage.update_trade_truth_by_order_id(
                oid,
                symbol=sym,
                price=exchange_price,
                pnl=exchange_pnl,
                fee=exchange_fee,
                reasoning_append=suffix,
            )
        return changed
    
    # ==================== 核心查询操作 ====================
    
    async def get_trade_history(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "timestamp",
        descending: bool = True
    ) -> List[Dict[str, Any]]:
        """
        获取交易历史（主要查询接口）
        
        Args:
            start_date: 起始时间
            end_date: 结束时间
            symbol: 交易对过滤
            side: 方向过滤 (buy/sell)
            status: 状态过滤
            limit: 返回数量限制
            offset: 偏移量
            order_by: 排序字段
            descending: 是否降序
        """
        try:
            if not self._cache and self.db_storage and not self._cache_bootstrapped:
                await self._load_cache_from_db()
            results = self._cache.copy()
            
            # 应用过滤器
            if start_date:
                start_str = start_date.isoformat()
                results = [t for t in results if t.timestamp >= start_str]
            
            if end_date:
                end_str = end_date.isoformat()
                results = [t for t in results if t.timestamp <= end_str]
            
            if symbol:
                symbol_upper = symbol.upper()
                results = [t for t in results if t.symbol.upper() == symbol_upper]
            
            if side:
                results = [t for t in results if t.side.lower() == side.lower()]
            
            if status:
                results = [t for t in results if t.status.lower() == status.lower()]
            
            # 排序
            reverse_order = descending
            if order_by == "timestamp":
                results.sort(key=lambda t: t.timestamp, reverse=reverse_order)
            elif order_by == "pnl":
                results.sort(key=lambda t: t.pnl, reverse=reverse_order)
            elif order_by == "price":
                results.sort(key=lambda t: t.price, reverse=reverse_order)
            
            # 分页
            paginated_results = results[offset:offset + limit]
            
            # 转换为字典
            return [asdict(trade) for trade in paginated_results]
            
        except Exception as e:
            logger.error(f"❌ 查询交易历史失败: {e}")
            return []
    
    async def get_recent_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近的交易记录"""
        return await self.get_trade_history(limit=limit)
    
    async def get_trade_by_id(self, trade_id: str) -> Optional[Dict[str, Any]]:
        """根据ID查询单笔交易"""
        for trade in self._cache:
            if trade.trade_id == trade_id:
                return asdict(trade)
        return None
    
    async def get_trades_by_symbol(
        self, 
        symbol: str, 
        days: int = 7,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取某交易对的交易历史"""
        start_date = datetime.now() - timedelta(days=days)
        return await self.get_trade_history(
            start_date=start_date,
            symbol=symbol,
            limit=limit
        )
    
    async def get_open_positions(self) -> List[Dict[str, Any]]:
        """获取当前持仓（未平仓的交易）"""
        return await self.get_trade_history(status="open")
    
    # ==================== 统计分析 ====================
    
    async def get_statistics(self, days: int = 30, force_refresh: bool = False) -> Dict[str, Any]:
        """
        获取交易统计信息
        
        包含：
        - 基础统计（胜率、盈亏等）
        - 按币种分布
        - 按日期趋势
        - 风险指标
        """
        try:
            # 使用缓存的统计数据
            if not force_refresh and self._stats_cache and self._stats_cache_time:
                if datetime.now() - self._stats_cache_time < self._stats_cache_ttl:
                    return asdict(self._stats_cache)
            
            start_date = datetime.now() - timedelta(days=days)
            trades = await self.get_trade_history(start_date=start_date, limit=10000)
            
            if not trades:
                return {"total_trades": 0, "message": "暂无交易数据"}
            
            stats = self._calculate_statistics(trades)
            
            # 缓存结果
            self._stats_cache = TradeStatistics(**{k: v for k, v in stats.items() if k in TradeStatistics.__dataclass_fields__})
            self._stats_cache_time = datetime.now()
            
            # 添加额外分析
            result = asdict(self._stats_cache)
            result.update({
                "period_days": days,
                "symbol_distribution": self._get_symbol_distribution(trades),
                "strategy_distribution": self._get_strategy_distribution(trades),
                "daily_pnl_trend": self._get_daily_pnl_trend(trades),
                "analysis_time": datetime.now().isoformat()
            })
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 统计计算失败: {e}")
            return {"error": str(e)}
    
    def _calculate_statistics(self, trades: List[Dict]) -> Dict[str, Any]:
        """计算基础统计数据"""
        total = len(trades)
        
        if total == 0:
            return {}
        
        wins = [t for t in trades if t.get("pnl", 0) > 0]
        losses = [t for t in trades if t.get("pnl", 0) < 0]
        
        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = winning_trades / total * 100 if total > 0 else 0
        
        total_pnl = sum(t.get("pnl", 0) for t in trades)
        total_fees = sum(t.get("fee", 0) for t in trades)
        
        avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
        
        gross_profit = sum(t["pnl"] for t in wins) if wins else 0
        gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0
        # JSON 响应不接受 inf，使用可序列化上限值表示“无亏损”
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 9999.0
        
        best_trade = max((t["pnl"] for t in trades), default=0)
        worst_trade = min((t["pnl"] for t in trades), default=0)
        
        # 简化的最大回撤计算
        cumulative_pnl = 0
        peak = 0
        max_drawdown = 0
        for t in sorted(trades, key=lambda x: x.get("timestamp", "")):
            cumulative_pnl += t.get("pnl", 0)
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            drawdown = peak - cumulative_pnl
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return {
            "total_trades": total,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 4),
            "total_fees": round(total_fees, 4),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_drawdown, 4),
            "best_trade": round(best_trade, 4),
            "worst_trade": round(worst_trade, 4)
        }
    
    def _get_symbol_distribution(self, trades: List[Dict]) -> Dict[str, Dict]:
        """按币种统计分布"""
        distribution = {}
        for t in trades:
            symbol = t.get("symbol", "UNKNOWN")
            if symbol not in distribution:
                distribution[symbol] = {
                    "count": 0,
                    "total_volume": 0,
                    "total_pnl": 0,
                    "win_rate": 0,
                    "wins": 0,
                    "losses": 0
                }
            distribution[symbol]["count"] += 1
            distribution[symbol]["total_volume"] += t.get("quantity", 0) * t.get("price", 0)
            distribution[symbol]["total_pnl"] += t.get("pnl", 0)
            if t.get("pnl", 0) > 0:
                distribution[symbol]["wins"] += 1
            else:
                distribution[symbol]["losses"] += 1
        
        # 计算胜率
        for sym in distribution:
            d = distribution[sym]
            total = d["wins"] + d["losses"]
            d["win_rate"] = round(d["wins"] / total * 100, 2) if total > 0 else 0
            d["total_volume"] = round(d["total_volume"], 2)
            d["total_pnl"] = round(d["total_pnl"], 4)
        
        return dict(sorted(distribution.items(), key=lambda x: x[1]["count"], reverse=True))

    def _get_strategy_distribution(self, trades: List[Dict]) -> Dict[str, Dict]:
        """按策略统计分布，供跨重启稳定查看策略表现。"""
        distribution: Dict[str, Dict[str, Any]] = {}
        for t in trades:
            strategy = str(t.get("strategy") or "unknown").strip() or "unknown"
            if strategy not in distribution:
                distribution[strategy] = {
                    "count": 0,
                    "wins": 0,
                    "losses": 0,
                    "total_pnl": 0.0,
                }
            d = distribution[strategy]
            d["count"] += 1
            pnl = float(t.get("pnl", 0) or 0)
            d["total_pnl"] += pnl
            if pnl > 0:
                d["wins"] += 1
            elif pnl < 0:
                d["losses"] += 1

        for st, d in distribution.items():
            total = int(d["wins"]) + int(d["losses"])
            d["win_rate"] = round((d["wins"] / total * 100.0), 2) if total > 0 else 0.0
            d["total_pnl"] = round(float(d["total_pnl"]), 4)
        return dict(sorted(distribution.items(), key=lambda x: x[1]["count"], reverse=True))
    
    def _get_daily_pnl_trend(self, trades: List[Dict]) -> List[Dict]:
        """每日盈亏趋势"""
        daily = {}
        for t in trades:
            date = t.get("timestamp", "")[:10]
            if date not in daily:
                daily[date] = {"pnl": 0, "trades": 0, "fees": 0}
            daily[date]["pnl"] += t.get("pnl", 0)
            daily[date]["trades"] += 1
            daily[date]["fees"] += t.get("fee", 0)
        
        trend = [
            {
                "date": date,
                "pnl": round(d["pnl"], 4),
                "trades": d["trades"],
                "fees": round(d["fees"], 4)
            }
            for date, d in sorted(daily.items())
        ]
        
        return trend[-30:]  # 最近30天
    
    # ==================== 记忆系统集成 ====================
    
    async def _sync_to_memory(self, trade: TradeRecord):
        """同步交易到记忆系统"""
        try:
            if not self.memory_manager:
                return
            
            # 1. 保存为每日记忆
            trade_summary = (
                f"## 交易记录\n"
                f"- **ID**: {trade.trade_id}\n"
                f"- **交易对**: {trade.symbol}\n"
                f"- **方向**: {trade.side}\n"
                f"- **数量**: {trade.quantity}\n"
                f"- **价格**: {trade.price}\n"
                f"- **盈亏**: {trade.pnl} ({trade.pnl_percent}%)\n"
                f"- **策略**: {trade.strategy}\n"
                f"- **理由**: {trade.reasoning}\n"
                f"- **时间**: {trade.timestamp}\n"
            )
            
            today = datetime.now().strftime('%Y-%m-%d')
            existing_memory = await self.memory_manager.load_recent_memories(days=1)
            
            if existing_memory:
                # 追加到今日记忆
                updated_content = existing_memory[0] + "\n\n" + trade_summary if existing_memory[0] else trade_summary
                await self.memory_manager.save_daily_memory(updated_content)
            else:
                await self.memory_manager.save_daily_memory(
                    f"# {today} 交易记录\n\n" + trade_summary
                )
            
            # 2. 如果有盈亏，保存经验教训
            if abs(trade.pnl) > 0:
                if trade.pnl > 0:
                    lesson_type = "successful_patterns"
                    context = f"盈利交易: {trade.symbol} {trade.side} 盈利{trade.pnl}"
                    lesson = f"{trade.symbol} {trade.side} 在价格{trade.price}时{'买入' if trade.side == 'buy' else '卖出'}，盈利{trade.pnl}。策略：{trade.strategy}"
                else:
                    lesson_type = "trading_mistakes"
                    context = f"亏损交易: {trade.symbol} {trade.side} 亏损{abs(trade.pnl)}"
                    lesson = f"{trade.symbol} {trade.side} 在价格{trade.price}时{'买入' if trade.side == 'buy' else '卖出'}，亏损{abs(trade.pnl)}。需反思策略：{trade.strategy}"
                
                await self.memory_manager.save_lesson_learned(
                    lesson_type=lesson_type,
                    lesson=lesson,
                    context=context
                )
            
            logger.debug(f"✓ 交易已同步到记忆系统: {trade.trade_id}")
            
        except Exception as e:
            logger.warning(f"⚠️ 同步到记忆系统失败: {e}")
    
    async def get_trade_context_for_conversation(self, limit: int = 10) -> str:
        """
        为对话生成交易历史上下文
        
        用于AI对话时提供交易背景信息
        """
        try:
            recent_trades = await self.get_recent_trades(limit=limit)
            
            if not recent_trades:
                return "暂无最近交易记录。"
            
            stats = await self.get_statistics(days=7, force_refresh=False)
            
            context_parts = [
                "# 📊 最近交易概览",
                "",
                f"**近7天统计**: 总交易{stats.get('total_trades', 0)}笔 | "
                f"胜率{stats.get('win_rate', 0)}% | "
                f"总盈亏{stats.get('total_pnl', 0)}",
                "",
                "## 最近交易记录",
                ""
            ]
            
            for i, trade in enumerate(recent_trades[:limit], 1):
                pnl_str = f"+{trade['pnl']}" if trade['pnl'] > 0 else str(trade['pnl'])
                context_parts.append(
                    f"{i}. **{trade['symbol']}** {trade['side']} {trade['quantity']}@{trade['price']} | "
                    f"盈亏: {pnl_str} | "
                    f"状态: {trade['status']} | "
                    f"时间: {trade['timestamp'][:16]}"
                )
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"生成对话上下文失败: {e}")
            return "无法加载交易历史。"
    
    async def generate_trade_review(self, days: int = 7) -> str:
        """
        生成交易复盘报告
        
        用于定期自动复盘和AI分析
        """
        try:
            stats = await self.get_statistics(days=days, force_refresh=True)
            trades = await self.get_trade_history(
                start_date=datetime.now() - timedelta(days=days),
                limit=1000
            )
            
            review_parts = [
                f"# 📈 {days}天交易复盘报告",
                f"",
                f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"",
                "## 一、总体表现",
                f"",
                f"- **总交易次数**: {stats.get('total_trades', 0)} 笔",
                f"- **胜率**: {stats.get('win_rate', 0)}%",
                f"- **总盈亏**: {stats.get('total_pnl', 0)} USDT",
                f"- **总手续费**: {stats.get('total_fees', 0)} USDT",
                f"- **最佳交易**: {stats.get('best_trade', 0)} USDT",
                f"- **最差交易**: {stats.get('worst_trade', 0)} USDT",
                f"- **最大回撤**: {stats.get('max_drawdown', 0)} USDT",
                f"- **盈利因子**: {stats.get('profit_factor', 0)}",
                f"",
                "## 二、各币种表现",
                f""
            ]
            
            symbol_dist = stats.get("symbol_distribution", {})
            for symbol, data in list(symbol_dist.items())[:10]:
                review_parts.append(
                    f"- **{symbol}**: {data['count']}笔 | "
                    f"胜率{data['win_rate']}% | "
                    f"盈亏{data['total_pnl']} USDT"
                )
            
            review_parts.extend([
                "",
                "## 三、每日盈亏趋势",
                ""
            ])
            
            daily_trend = stats.get("daily_pnl_trend", [])
            for day_data in daily_trend[-7:]:
                emoji = "📈" if day_data["pnl"] >= 0 else "📉"
                review_parts.append(
                    f"- {emoji} **{day_data['date']}**: "
                    f"{day_data['pnl']} USDT ({day_data['trades']}笔)"
                )
            
            review_parts.extend([
                "",
                "## 四、近期重要交易",
                ""
            ])
            
            # 找出盈亏最大的几笔交易
            sorted_trades = sorted(trades, key=lambda t: abs(t.get("pnl", 0)), reverse=True)[:5]
            for trade in sorted_trades:
                emoji = "✅" if trade.get("pnl", 0) > 0 else "❌"
                review_parts.append(
                    f"- {emoji} **{trade['symbol']}** {trade['side']} "
                    f"{trade.get('quantity', 0)}@{trade.get('price', 0)} | "
                    f"盈亏: {trade.get('pnl', 0)} | "
                    f"原因: {trade.get('reasoning', 'N/A')[:50]}"
                )
            
            review_parts.extend([
                "",
                "## 五、改进建议",
                "",
                "*(待AI分析后补充)*",
                ""
            ])
            
            return "\n".join(review_parts)
            
        except Exception as e:
            logger.error(f"生成复盘报告失败: {e}")
            return f"生成复盘报告失败: {e}"

    async def run_outcome_reflection(self, limit: int = 120) -> Dict[str, Any]:
        """
        Resolve recently closed outcomes into lessons once (pending -> realized -> reflection).
        """
        rows = await self.get_recent_trades(limit=max(20, int(limit or 120)))
        if not rows:
            return {"processed": 0, "reflected": 0, "skipped": 0}

        reflected = 0
        skipped = 0
        for row in rows:
            if not isinstance(row, dict):
                skipped += 1
                continue
            action = str(row.get("action") or "").strip().lower()
            status = str(row.get("status") or "").strip().lower()
            if action not in {"close", "closed"} and status not in {"closed", "filled"}:
                skipped += 1
                continue

            try:
                pnl = float(row.get("pnl", 0) or 0)
                pnl_pct = float(row.get("pnl_percent", 0) or 0)
            except Exception:
                skipped += 1
                continue
            if abs(pnl) <= 1e-12 and abs(pnl_pct) <= 1e-12:
                skipped += 1
                continue

            rid = str(row.get("order_id") or row.get("trade_id") or "") or (
                f"{row.get('symbol','')}|{row.get('timestamp','')}|{pnl:.8f}"
            )
            if rid in self._reflection_seen:
                skipped += 1
                continue

            if self.memory_manager is not None:
                try:
                    symbol = str(row.get("symbol") or "")
                    side = str(row.get("side") or "")
                    strat = str(row.get("strategy") or "unknown")
                    reason = str(row.get("reasoning") or "N/A")[:220]
                    tone = "成功模式" if pnl > 0 else "失败教训"
                    lesson = (
                        f"{tone}: {symbol} {side} strategy={strat} pnl={pnl:.4f} "
                        f"pnl_pct={pnl_pct:.4%}; reason={reason}"
                    )
                    await self.memory_manager.save_lesson_learned(
                        lesson_type="successful_patterns" if pnl > 0 else "trading_mistakes",
                        lesson=lesson,
                        context=f"order={rid}",
                    )
                except Exception:
                    pass

            self._reflection_seen.add(rid)
            reflected += 1

        self._save_reflection_index()
        return {
            "processed": len(rows),
            "reflected": reflected,
            "skipped": skipped,
        }
    
    # ==================== 内部方法 ====================
    
    async def _save_to_database(self, trade: TradeRecord):
        """保存到SQLite数据库"""
        if self.db_storage:
            from src.modules.core.historical_data_storage import TradeRecord as DBTradeRecord
            db_record = DBTradeRecord(
                symbol=trade.symbol,
                side=trade.side,
                order_type=trade.order_type,
                quantity=trade.quantity,
                price=trade.price,
                timestamp=trade.timestamp,
                order_id=trade.order_id,
                pnl=trade.pnl,
                fee=trade.fee,
                reasoning=trade.reasoning
            )
            await self.db_storage.save_trade(db_record)
    
    async def _load_cache_from_db(self):
        """从数据库加载缓存"""
        try:
            if self.db_storage:
                rows = await self.db_storage.get_trades(limit=self._cache_max_size)
                self._cache_bootstrapped = True
                if not rows:
                    return

                loaded: List[TradeRecord] = []
                for idx, row in enumerate(rows):
                    if not isinstance(row, dict):
                        continue
                    symbol = str(row.get("symbol") or "").strip()
                    if not symbol:
                        continue

                    side_raw = str(row.get("side", "buy") or "buy").strip().lower()
                    side_norm = {"long": "buy", "short": "sell"}.get(side_raw, side_raw or "buy")
                    loaded.append(
                        TradeRecord(
                            trade_id=f"db_{row.get('id', idx)}",
                            order_id=str(row.get("order_id") or ""),
                            symbol=symbol,
                            side=side_norm,
                            order_type=str(row.get("order_type") or "market"),
                            quantity=_to_float(row.get("quantity"), 0.0),
                            price=_to_float(row.get("price"), 0.0),
                            fee=_to_float(row.get("fee"), 0.0),
                            pnl=_to_float(row.get("pnl"), 0.0),
                            status="filled",
                            reasoning=str(row.get("reasoning") or ""),
                            timestamp=str(row.get("timestamp") or datetime.now().isoformat()),
                            # Rows loaded from persistent DB are real history, not synthetic bootstrap.
                            metadata={"source": "historical_db", "db_id": row.get("id")},
                        )
                    )

                loaded.sort(key=lambda t: t.timestamp)
                self._cache = loaded[-self._cache_max_size :]
                self._symbol_index.clear()
                self._date_index.clear()
                for trade in self._cache:
                    self._update_index(trade)
                logger.info("✅ 从数据库回灌交易缓存 %s 条", len(self._cache))
        except Exception as e:
            logger.warning(f"加载数据库缓存失败: {e}")
    
    async def _update_cache(self, trade: TradeRecord):
        """更新内存缓存"""
        self._cache.append(trade)
        
        # 保持缓存大小
        if len(self._cache) > self._cache_max_size:
            # 移除最旧的记录
            removed = self._cache.pop(0)
            # 清理索引
            self._remove_from_index(removed)
    
    def _update_index(self, trade: TradeRecord):
        """更新索引"""
        # 符号索引
        if trade.symbol not in self._symbol_index:
            self._symbol_index[trade.symbol] = []
        self._symbol_index[trade.symbol].append(trade.trade_id)
        
        # 日期索引
        date_key = trade.timestamp[:10]
        if date_key not in self._date_index:
            self._date_index[date_key] = []
        self._date_index[date_key].append(trade.trade_id)
    
    def _remove_from_index(self, trade: TradeRecord):
        """从索引中移除"""
        if trade.symbol in self._symbol_index:
            if trade.trade_id in self._symbol_index[trade.symbol]:
                self._symbol_index[trade.symbol].remove(trade.trade_id)
        
        date_key = trade.timestamp[:10]
        if date_key in self._date_index:
            if trade.trade_id in self._date_index[date_key]:
                self._date_index[date_key].remove(trade.trade_id)
    
    async def _backup_to_jsonl(self, trade: TradeRecord):
        """备份到JSONL文件"""
        try:
            async with aiofiles.open(self.backup_file, 'a', encoding='utf-8') as f:
                line = json.dumps(asdict(trade), ensure_ascii=False)
                await f.write(line + '\n')
        except Exception as e:
            logger.warning(f"备份到JSONL失败: {e}")
    
    def _invalidate_stats_cache(self):
        """使统计缓存失效"""
        self._stats_cache = None
        self._stats_cache_time = None
    
    # ==================== 维护方法 ====================
    
    async def cleanup_old_records(self, days: int = 90):
        """清理旧记录（仅清理缓存，保留数据库）"""
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff_date.isoformat()
        
        original_count = len(self._cache)
        self._cache = [t for t in self._cache if t.timestamp >= cutoff_str]
        
        removed = original_count - len(self._cache)
        logger.info(f"🧹 清理了 {removed} 条超过 {days} 天的旧记录")
        
        # 重建索引
        self._symbol_index.clear()
        self._date_index.clear()
        for trade in self._cache:
            self._update_index(trade)
    
    async def export_to_csv(self, filepath: str, days: int = 30) -> bool:
        """导出交易历史到CSV"""
        try:
            start_date = datetime.now() - timedelta(days=days)
            trades = await self.get_trade_history(start_date=start_date, limit=10000)
            
            if not trades:
                logger.warning("没有数据可导出")
                return False
            
            df = pd.DataFrame(trades)
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            
            logger.info(f"✅ 已导出 {len(trades)} 条记录到 {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"导出CSV失败: {e}")
            return False
    
    async def get_system_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            "service": "TradeHistoryService",
            "status": "running",
            "cache_size": len(self._cache),
            "cached_symbols": len(self._symbol_index),
            "cached_dates": len(self._date_index),
            "database_connected": self.db_storage is not None,
            "memory_connected": self.memory_manager is not None,
            "backup_file": str(self.backup_file),
            "backup_file_exists": self.backup_file.exists(),
            "stats_cached": self._stats_cache is not None
        }
