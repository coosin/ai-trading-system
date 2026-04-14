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

logger = logging.getLogger(__name__)


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
        
        logger.info(f"统一交易历史服务初始化完成，路径: {self.base_path}")
    
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
        trade = TradeRecord(
            trade_id=trade_dict.get("trade_id", f"trade_{datetime.now().timestamp()}"),
            order_id=trade_dict.get("order_id", ""),
            symbol=trade_dict.get("symbol", ""),
            side=trade_dict.get("side", "buy"),
            order_type=trade_dict.get("order_type", "market"),
            quantity=float(trade_dict.get("quantity", 0)),
            price=float(trade_dict.get("price", 0)),
            cost=float(trade_dict.get("cost", 0)),
            fee=float(trade_dict.get("fee", 0)),
            pnl=float(trade_dict.get("pnl", 0)),
            pnl_percent=float(trade_dict.get("pnl_percent", 0)),
            status=trade_dict.get("status", "filled"),
            strategy=trade_dict.get("strategy", ""),
            reasoning=trade_dict.get("reasoning", ""),
            stop_loss=trade_dict.get("stop_loss"),
            take_profit=trade_dict.get("take_profit"),
            leverage=int(trade_dict.get("leverage", 1)),
            timestamp=trade_dict.get("timestamp", datetime.now().isoformat()),
            metadata=trade_dict.get("metadata", {})
        )
        return await self.record_trade(trade)
    
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
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
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
                # 尝试从数据库加载最近的交易
                pass  # HistoricalDataStorage可能没有批量查询方法，这里预留接口
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
