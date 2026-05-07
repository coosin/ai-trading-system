"""
历史数据存储模块

提供历史K线数据、交易记录、技术指标历史的存储和查询功能
"""

import asyncio
import aiosqlite
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class KlineRecord:
    """K线记录"""
    symbol: str
    timeframe: str
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float = 0.0


@dataclass
class TradeRecord:
    """交易记录"""
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float
    timestamp: str
    order_id: str = ""
    pnl: float = 0.0
    fee: float = 0.0
    reasoning: str = ""


@dataclass
class IndicatorRecord:
    """技术指标记录"""
    symbol: str
    timestamp: str
    trend: str
    trend_strength: float
    ma5: Optional[float] = None
    ma20: Optional[float] = None
    rsi: Optional[float] = None
    macd: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_lower: Optional[float] = None
    atr: Optional[float] = None


class HistoricalDataStorage:
    """
    历史数据存储管理器
    
    功能：
    1. 存储多时间周期K线数据
    2. 存储交易记录
    3. 存储技术指标历史
    4. 支持数据查询和导出
    """
    
    def __init__(self, db_path: str = None, config_manager: Any = None):
        if db_path is None:
            data_dir = Path(
                (config_manager.get_path_sync("data_path", None) if config_manager else None)
                or "/app/data"
            )
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                data_dir = Path("/tmp/openclaw_data")
                data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "historical_data.db")
        
        self.db_path = db_path
        self._db = None
        self._lock = asyncio.Lock()
        
        logger.info(f"历史数据存储初始化: {db_path}")
    
    async def initialize(self) -> bool:
        """初始化数据库"""
        try:
            self._db = await aiosqlite.connect(self.db_path)
            
            await self._create_tables()
            
            logger.info("✅ 历史数据存储初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"历史数据存储初始化失败: {e}")
            return False
    
    async def _create_tables(self) -> None:
        """创建数据表"""
        await self._db.executescript("""
            -- K线数据表
            CREATE TABLE IF NOT EXISTS klines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                quote_volume REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, timeframe, timestamp)
            );
            
            -- 交易记录表
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                timestamp TEXT NOT NULL,
                order_id TEXT,
                pnl REAL DEFAULT 0,
                fee REAL DEFAULT 0,
                reasoning TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            -- 技术指标历史表
            CREATE TABLE IF NOT EXISTS indicators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                trend TEXT NOT NULL,
                trend_strength REAL NOT NULL,
                ma5 REAL,
                ma20 REAL,
                rsi REAL,
                macd REAL,
                bollinger_upper REAL,
                bollinger_lower REAL,
                atr REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            -- 账户快照表
            CREATE TABLE IF NOT EXISTS account_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                total_equity REAL NOT NULL,
                available_balance REAL NOT NULL,
                margin_used REAL NOT NULL,
                unrealized_pnl REAL DEFAULT 0,
                positions TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            -- 创建索引
            CREATE INDEX IF NOT EXISTS idx_klines_symbol_tf ON klines(symbol, timeframe);
            CREATE INDEX IF NOT EXISTS idx_klines_timestamp ON klines(timestamp);
            CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
            CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_order_id_unique
                ON trades(order_id)
                WHERE order_id IS NOT NULL AND order_id != '';
            CREATE INDEX IF NOT EXISTS idx_indicators_symbol ON indicators(symbol);
            CREATE INDEX IF NOT EXISTS idx_indicators_timestamp ON indicators(timestamp);
        """)
        
        await self._db.commit()
    
    async def save_klines(self, symbol: str, timeframe: str, klines: List[Dict]) -> int:
        """
        保存K线数据
        
        Args:
            symbol: 交易对
            timeframe: 时间周期
            klines: K线数据列表
            
        Returns:
            保存的记录数
        """
        if not klines:
            return 0
        
        async with self._lock:
            try:
                saved_count = 0
                
                for kline in klines:
                    try:
                        await self._db.execute("""
                            INSERT OR REPLACE INTO klines 
                            (symbol, timeframe, timestamp, open, high, low, close, volume, quote_volume)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            symbol,
                            timeframe,
                            kline.get("timestamp", 0),
                            kline.get("open", 0),
                            kline.get("high", 0),
                            kline.get("low", 0),
                            kline.get("close", 0),
                            kline.get("volume", 0),
                            kline.get("quote_volume", 0)
                        ))
                        saved_count += 1
                    except Exception as e:
                        logger.debug(f"保存单条K线失败: {e}")
                        continue
                
                await self._db.commit()
                
                logger.info(f"✅ 保存 {symbol} {timeframe} K线数据 {saved_count} 条")
                return saved_count
                
            except Exception as e:
                logger.error(f"保存K线数据失败: {e}")
                return 0
    
    async def get_klines(self, symbol: str, timeframe: str, 
                         start_time: int = None, end_time: int = None,
                         limit: int = 500) -> List[Dict]:
        """
        查询K线数据
        
        Args:
            symbol: 交易对
            timeframe: 时间周期
            start_time: 开始时间戳
            end_time: 结束时间戳
            limit: 返回数量限制
            
        Returns:
            K线数据列表
        """
        try:
            query = "SELECT * FROM klines WHERE symbol = ? AND timeframe = ?"
            params = [symbol, timeframe]
            
            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)
            
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            async with self._db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                
                klines = []
                for row in rows:
                    klines.append({
                        "timestamp": row[3],
                        "open": row[4],
                        "high": row[5],
                        "low": row[6],
                        "close": row[7],
                        "volume": row[8],
                        "quote_volume": row[9]
                    })
                
                return list(reversed(klines))
                
        except Exception as e:
            logger.error(f"查询K线数据失败: {e}")
            return []
    
    async def save_trade(self, trade: TradeRecord) -> bool:
        """保存交易记录"""
        async with self._lock:
            try:
                has_order_id = bool(str(getattr(trade, "order_id", "") or "").strip())
                if has_order_id:
                    await self._db.execute("""
                        INSERT OR IGNORE INTO trades 
                        (symbol, side, order_type, quantity, price, timestamp, order_id, pnl, fee, reasoning)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        trade.symbol,
                        trade.side,
                        trade.order_type,
                        trade.quantity,
                        trade.price,
                        trade.timestamp,
                        trade.order_id,
                        trade.pnl,
                        trade.fee,
                        trade.reasoning
                    ))
                else:
                    await self._db.execute("""
                        INSERT INTO trades 
                        (symbol, side, order_type, quantity, price, timestamp, order_id, pnl, fee, reasoning)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        trade.symbol,
                        trade.side,
                        trade.order_type,
                        trade.quantity,
                        trade.price,
                        trade.timestamp,
                        trade.order_id,
                        trade.pnl,
                        trade.fee,
                        trade.reasoning
                    ))
                
                await self._db.commit()
                logger.info(f"✅ 保存交易记录: {trade.symbol} {trade.side} {trade.quantity}@{trade.price}")
                return True
                
            except Exception as e:
                logger.error(f"保存交易记录失败: {e}")
                return False

    async def update_trade_truth_by_order_id(
        self,
        order_id: str,
        *,
        symbol: Optional[str] = None,
        price: Optional[float] = None,
        pnl: Optional[float] = None,
        fee: Optional[float] = None,
        reasoning_append: str = "",
    ) -> int:
        """按 order_id 更新交易真值字段（价格/盈亏/手续费）。返回受影响行数。"""
        oid = str(order_id or "").strip()
        if not oid:
            return 0
        async with self._lock:
            try:
                sets: List[str] = []
                params: List[Any] = []
                if price is not None:
                    sets.append("price = ?")
                    params.append(float(price))
                if pnl is not None:
                    sets.append("pnl = ?")
                    params.append(float(pnl))
                if fee is not None:
                    sets.append("fee = ?")
                    params.append(float(fee))
                if reasoning_append:
                    sets.append("reasoning = COALESCE(reasoning, '') || ?")
                    params.append(str(reasoning_append))
                if not sets:
                    return 0
                query = f"UPDATE trades SET {', '.join(sets)} WHERE order_id = ?"
                params.append(oid)
                if symbol:
                    query += " AND symbol = ?"
                    params.append(str(symbol))
                cur = await self._db.execute(query, params)
                await self._db.commit()
                return int(getattr(cur, "rowcount", 0) or 0)
            except Exception as e:
                logger.error("update_trade_truth_by_order_id 失败: %s", e)
                return 0
    
    async def get_trades(self, symbol: str = None, 
                         start_date: str = None, end_date: str = None,
                         limit: int = 100) -> List[Dict]:
        """查询交易记录"""
        try:
            query = "SELECT * FROM trades WHERE 1=1"
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)
            
            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            async with self._db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                
                return [{
                    "id": row[0],
                    "symbol": row[1],
                    "side": row[2],
                    "order_type": row[3],
                    "quantity": row[4],
                    "price": row[5],
                    "timestamp": row[6],
                    "order_id": row[7],
                    "pnl": row[8],
                    "fee": row[9],
                    "reasoning": row[10]
                } for row in rows]
                
        except Exception as e:
            logger.error(f"查询交易记录失败: {e}")
            return []
    
    async def save_indicator(self, indicator: IndicatorRecord) -> bool:
        """保存技术指标记录"""
        async with self._lock:
            try:
                await self._db.execute("""
                    INSERT INTO indicators 
                    (symbol, timestamp, trend, trend_strength, ma5, ma20, rsi, macd, 
                     bollinger_upper, bollinger_lower, atr)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    indicator.symbol,
                    indicator.timestamp,
                    indicator.trend,
                    indicator.trend_strength,
                    indicator.ma5,
                    indicator.ma20,
                    indicator.rsi,
                    indicator.macd,
                    indicator.bollinger_upper,
                    indicator.bollinger_lower,
                    indicator.atr
                ))
                
                await self._db.commit()
                return True
                
            except Exception as e:
                logger.error(f"保存技术指标记录失败: {e}")
                return False
    
    async def save_account_snapshot(self, snapshot: Dict) -> bool:
        """保存账户快照"""
        async with self._lock:
            try:
                await self._db.execute("""
                    INSERT INTO account_snapshots 
                    (timestamp, total_equity, available_balance, margin_used, unrealized_pnl, positions)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    snapshot.get("timestamp", datetime.now().isoformat()),
                    snapshot.get("total_equity", 0),
                    snapshot.get("available_balance", 0),
                    snapshot.get("margin_used", 0),
                    snapshot.get("unrealized_pnl", 0),
                    json.dumps(snapshot.get("positions", []))
                ))
                
                await self._db.commit()
                return True
                
            except Exception as e:
                logger.error(f"保存账户快照失败: {e}")
                return False
    
    async def get_account_snapshots(self, limit: int = 100) -> List[Dict]:
        """查询账户快照"""
        try:
            query = "SELECT * FROM account_snapshots ORDER BY timestamp DESC LIMIT ?"
            
            async with self._db.execute(query, [limit]) as cursor:
                rows = await cursor.fetchall()
                
                return [{
                    "id": row[0],
                    "timestamp": row[1],
                    "total_equity": row[2],
                    "available_balance": row[3],
                    "margin_used": row[4],
                    "unrealized_pnl": row[5],
                    "positions": json.loads(row[6]) if row[6] else []
                } for row in rows]
                
        except Exception as e:
            logger.error(f"查询账户快照失败: {e}")
            return []
    
    async def get_statistics(self) -> Dict:
        """获取数据统计"""
        try:
            stats = {}
            
            async with self._db.execute("SELECT COUNT(*) FROM klines") as cursor:
                stats["klines_count"] = (await cursor.fetchone())[0]
            
            async with self._db.execute("SELECT COUNT(*) FROM trades") as cursor:
                stats["trades_count"] = (await cursor.fetchone())[0]
            
            async with self._db.execute("SELECT COUNT(*) FROM indicators") as cursor:
                stats["indicators_count"] = (await cursor.fetchone())[0]
            
            async with self._db.execute(
                "SELECT symbol, COUNT(*) as cnt FROM klines GROUP BY symbol"
            ) as cursor:
                rows = await cursor.fetchall()
                stats["klines_by_symbol"] = {row[0]: row[1] for row in rows}
            
            async with self._db.execute(
                "SELECT timeframe, COUNT(*) as cnt FROM klines GROUP BY timeframe"
            ) as cursor:
                rows = await cursor.fetchall()
                stats["klines_by_timeframe"] = {row[0]: row[1] for row in rows}
            
            return stats
            
        except Exception as e:
            logger.error(f"获取数据统计失败: {e}")
            return {}
    
    async def cleanup_old_data(self, days: int = 90) -> int:
        """清理旧数据"""
        cutoff = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        cutoff_str = (datetime.now() - timedelta(days=days)).isoformat()
        
        deleted = 0
        
        try:
            async with self._lock:
                await self._db.execute(
                    "DELETE FROM klines WHERE timestamp < ?", [cutoff]
                )
                deleted += self._db.total_changes
                
                await self._db.execute(
                    "DELETE FROM indicators WHERE timestamp < ?", [cutoff_str]
                )
                deleted += self._db.total_changes
                
                await self._db.commit()
                
                logger.info(f"✅ 清理了 {days} 天前的旧数据")
                
        except Exception as e:
            logger.error(f"清理旧数据失败: {e}")
        
        return deleted
    
    async def export_data(self, table: str, output_path: str) -> bool:
        """导出数据到JSON文件"""
        try:
            if table == "klines":
                data = await self.get_klines("BTC/USDT", "1h", limit=10000)
            elif table == "trades":
                data = await self.get_trades(limit=10000)
            else:
                return False
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ 导出 {table} 数据到 {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出数据失败: {e}")
            return False
    
    async def close(self) -> None:
        """关闭数据库连接"""
        if self._db:
            await self._db.close()
            logger.info("历史数据存储已关闭")


_storage_instance: Optional[HistoricalDataStorage] = None


async def get_historical_storage() -> HistoricalDataStorage:
    """获取历史数据存储单例"""
    global _storage_instance
    
    if _storage_instance is None:
        _storage_instance = HistoricalDataStorage()
        await _storage_instance.initialize()
    
    return _storage_instance
