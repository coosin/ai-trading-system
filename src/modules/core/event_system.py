"""
增强的事件系统 - 支持优先级、持久化和事件总线

功能：
1. 基于优先级的事件处理
2. 事件持久化存储
3. 事件总线支持复杂路由
4. 事件过滤和转换
5. 异步事件处理
"""

import asyncio
import json
import logging
import pickle
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union
from pathlib import Path

logger = logging.getLogger(__name__)


class EventPriority(Enum):
    """事件优先级"""
    CRITICAL = 0    # 关键事件，立即处理
    HIGH = 1        # 高优先级
    NORMAL = 2      # 正常优先级
    LOW = 3         # 低优先级
    BACKGROUND = 4  # 后台任务


class EventType(Enum):
    """事件类型"""
    # 系统事件
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    SYSTEM_ERROR = "system_error"
    
    # 模块事件
    MODULE_STARTED = "module_started"
    MODULE_STOPPED = "module_stopped"
    MODULE_ERROR = "module_error"
    MODULE_HEALTH_CHECK = "module_health_check"
    
    # 数据事件
    DATA_RECEIVED = "data_received"
    DATA_PROCESSED = "data_processed"
    DATA_ERROR = "data_error"
    
    # 交易事件
    TRADE_SIGNAL = "trade_signal"
    ORDER_CREATED = "order_created"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"
    POSITION_UPDATED = "position_updated"
    
    # 风险事件
    RISK_ALERT = "risk_alert"
    RISK_LIMIT_BREACH = "risk_limit_breach"
    
    # 配置事件
    CONFIG_CHANGED = "config_changed"
    CONFIG_RELOADED = "config_reloaded"


@dataclass
class Event:
    """事件基类"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: EventType = EventType.SYSTEM_START
    source: str = "system"
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    priority: EventPriority = EventPriority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "type": self.type.value,
            "source": self.source,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority.value,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        """从字典创建事件"""
        return cls(
            id=data["id"],
            type=EventType(data["type"]),
            source=data["source"],
            data=data["data"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            priority=EventPriority(data["priority"]),
            metadata=data.get("metadata", {})
        )


class EventFilter:
    """事件过滤器"""
    
    def __init__(self, 
                 event_types: Optional[Set[EventType]] = None,
                 sources: Optional[Set[str]] = None,
                 min_priority: Optional[EventPriority] = None,
                 custom_filter: Optional[Callable[[Event], bool]] = None):
        self.event_types = event_types
        self.sources = sources
        self.min_priority = min_priority
        self.custom_filter = custom_filter
    
    def matches(self, event: Event) -> bool:
        """检查事件是否匹配过滤器"""
        if self.event_types and event.type not in self.event_types:
            return False
        if self.sources and event.source not in self.sources:
            return False
        if self.min_priority and event.priority.value > self.min_priority.value:
            return False
        if self.custom_filter and not self.custom_filter(event):
            return False
        return True


class EventPersistence:
    """事件持久化存储"""
    
    def __init__(self, db_path: str = "events.db"):
        self.db_path = db_path
        self._initialized = False
        self._lock = asyncio.Lock()
        self._connection = None
    
    async def initialize(self):
        """初始化数据库"""
        if self._initialized:
            return
        
        async with self._lock:
            await asyncio.to_thread(self._init_db)
            self._initialized = True
            logger.info("事件持久化存储初始化完成")
    
    def _init_db(self):
        """初始化数据库（同步方法）"""
        # 对于内存数据库，需要保持连接打开
        if self.db_path == ":memory:":
            self._connection = sqlite3.connect(self.db_path)
            conn = self._connection
        else:
            conn = sqlite3.connect(self.db_path)
        
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                source TEXT NOT NULL,
                data BLOB NOT NULL,
                timestamp TEXT NOT NULL,
                priority INTEGER NOT NULL,
                metadata BLOB,
                processed BOOLEAN DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(type)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_events_priority ON events(priority)
        ''')
        
        conn.commit()
        # 对于内存数据库，不要关闭连接
        if self.db_path != ":memory:":
            conn.close()
    
    def _get_connection(self):
        """获取数据库连接"""
        if self.db_path == ":memory:":
            return self._connection
        else:
            return sqlite3.connect(self.db_path)
    
    async def save_event(self, event: Event):
        """保存事件"""
        async with self._lock:
            await asyncio.to_thread(self._save_event_sync, event)
    
    def _save_event_sync(self, event: Event):
        """同步保存事件"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO events 
            (id, type, source, data, timestamp, priority, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            event.id,
            event.type.value,
            event.source,
            pickle.dumps(event.data),
            event.timestamp.isoformat(),
            event.priority.value,
            pickle.dumps(event.metadata)
        ))
        
        conn.commit()
        # 对于内存数据库，不要关闭连接
        if self.db_path != ":memory:":
            conn.close()
    
    async def load_events(self, 
                         event_types: Optional[List[EventType]] = None,
                         start_time: Optional[datetime] = None,
                         end_time: Optional[datetime] = None,
                         limit: int = 1000) -> List[Event]:
        """加载事件"""
        async with self._lock:
            return await asyncio.to_thread(
                self._load_events_sync, event_types, start_time, end_time, limit
            )
    
    def _load_events_sync(self,
                         event_types: Optional[List[EventType]],
                         start_time: Optional[datetime],
                         end_time: Optional[datetime],
                         limit: int) -> List[Event]:
        """同步加载事件"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM events WHERE 1=1"
        params = []
        
        if event_types:
            placeholders = ','.join(['?' for _ in event_types])
            query += f" AND type IN ({placeholders})"
            params.extend([et.value for et in event_types])
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        # 对于内存数据库，不要关闭连接
        if self.db_path != ":memory:":
            conn.close()
        
        events = []
        for row in rows:
            event = Event(
                id=row[0],
                type=EventType(row[1]),
                source=row[2],
                data=pickle.loads(row[3]),
                timestamp=datetime.fromisoformat(row[4]),
                priority=EventPriority(row[5]),
                metadata=pickle.loads(row[6]) if row[6] else {}
            )
            events.append(event)
        
        return events
    
    async def mark_processed(self, event_id: str):
        """标记事件已处理"""
        async with self._lock:
            await asyncio.to_thread(self._mark_processed_sync, event_id)
    
    def _mark_processed_sync(self, event_id: str):
        """同步标记事件已处理"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE events SET processed = 1 WHERE id = ?",
            (event_id,)
        )
        conn.commit()
        # 对于内存数据库，不要关闭连接
        if self.db_path != ":memory:":
            conn.close()


class EventBus:
    """事件总线 - 支持复杂路由和过滤"""
    
    def __init__(self, persistence: Optional[EventPersistence] = None):
        self.persistence = persistence
        self.subscribers: Dict[EventType, List[Callable]] = {}
        self.filtered_subscribers: List[tuple] = []  # (filter, handler)
        self.transformers: List[Callable[[Event], Event]] = []
        self._running = False
        self._queues: Dict[EventPriority, asyncio.PriorityQueue] = {}
        self._tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
        
        # 为每个优先级创建队列
        for priority in EventPriority:
            self._queues[priority] = asyncio.PriorityQueue(maxsize=10000)
    
    async def initialize(self):
        """初始化事件总线"""
        if self.persistence:
            await self.persistence.initialize()
        
        self._running = True
        
        # 启动处理任务
        for priority in EventPriority:
            task = asyncio.create_task(
                self._process_queue(priority),
                name=f"event_processor_{priority.name}"
            )
            self._tasks.append(task)
        
        logger.info("事件总线初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        self._running = False
        
        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        logger.info("事件总线清理完成")
    
    def subscribe(self, event_type: EventType, handler: Callable[[Event], Any]):
        """订阅特定类型的事件"""
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(handler)
        logger.debug(f"订阅事件: {event_type.value} -> {handler.__name__}")
    
    def subscribe_filtered(self, filter: EventFilter, handler: Callable[[Event], Any]):
        """使用过滤器订阅事件"""
        self.filtered_subscribers.append((filter, handler))
        logger.debug(f"订阅过滤事件: {handler.__name__}")
    
    def add_transformer(self, transformer: Callable[[Event], Event]):
        """添加事件转换器"""
        self.transformers.append(transformer)
        logger.debug(f"添加事件转换器: {transformer.__name__}")
    
    async def publish(self, event: Event, persist: bool = True):
        """发布事件"""
        # 应用转换器
        for transformer in self.transformers:
            try:
                event = transformer(event)
            except Exception as e:
                logger.error(f"事件转换错误: {e}")
                return
        
        # 持久化
        if persist and self.persistence:
            await self.persistence.save_event(event)
        
        # 放入优先级队列
        queue = self._queues[event.priority]
        try:
            # 使用优先级值和时间戳作为排序键
            await queue.put((event.priority.value, event.timestamp.timestamp(), event))
            logger.debug(f"发布事件: {event.type.value} (优先级: {event.priority.name})")
        except asyncio.QueueFull:
            logger.error(f"事件队列已满，丢弃事件: {event.type.value}")
    
    async def _process_queue(self, priority: EventPriority):
        """处理特定优先级的队列"""
        queue = self._queues[priority]
        
        while self._running:
            try:
                # 获取事件
                _, _, event = await queue.get()
                
                # 处理事件
                await self._dispatch_event(event)
                
                # 标记完成
                queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"事件处理错误: {e}")
    
    async def _dispatch_event(self, event: Event):
        """分发事件到订阅者"""
        # 直接订阅者
        handlers = self.subscribers.get(event.type, [])
        
        # 过滤订阅者
        for filter, handler in self.filtered_subscribers:
            if filter.matches(event):
                handlers.append(handler)
        
        # 执行所有处理器
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"事件处理器错误 {handler.__name__}: {e}")
        
        # 标记已处理
        if self.persistence:
            await self.persistence.mark_processed(event.id)
    
    async def replay_events(self, 
                           event_types: Optional[List[EventType]] = None,
                           start_time: Optional[datetime] = None,
                           end_time: Optional[datetime] = None,
                           handler: Optional[Callable[[Event], Any]] = None):
        """重放历史事件"""
        if not self.persistence:
            logger.warning("没有配置持久化存储，无法重放事件")
            return
        
        events = await self.persistence.load_events(
            event_types, start_time, end_time
        )
        
        logger.info(f"重放 {len(events)} 个历史事件")
        
        for event in events:
            if handler:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            else:
                await self._dispatch_event(event)


class EnhancedEventSystem:
    """增强的事件系统 - 整合所有功能"""
    
    def __init__(self, db_path: str = "data/events.db"):
        self.persistence = EventPersistence(db_path)
        self.event_bus = EventBus(self.persistence)
        self._initialized = False
    
    async def initialize(self):
        """初始化事件系统"""
        if self._initialized:
            return
        
        await self.event_bus.initialize()
        self._initialized = True
        logger.info("增强事件系统初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        await self.event_bus.cleanup()
        self._initialized = False
        logger.info("增强事件系统清理完成")
    
    def subscribe(self, event_type: EventType, handler: Callable[[Event], Any]):
        """订阅事件"""
        self.event_bus.subscribe(event_type, handler)
    
    def subscribe_filtered(self, filter: EventFilter, handler: Callable[[Event], Any]):
        """使用过滤器订阅事件"""
        self.event_bus.subscribe_filtered(filter, handler)
    
    async def emit(self, 
                   event_type: EventType, 
                   source: str, 
                   data: Dict[str, Any],
                   priority: EventPriority = EventPriority.NORMAL,
                   persist: bool = True):
        """发送事件"""
        event = Event(
            type=event_type,
            source=source,
            data=data,
            priority=priority
        )
        await self.event_bus.publish(event, persist)
    
    async def replay(self, 
                    event_types: Optional[List[EventType]] = None,
                    start_time: Optional[datetime] = None,
                    end_time: Optional[datetime] = None):
        """重放历史事件"""
        await self.event_bus.replay_events(event_types, start_time, end_time)


# 使用示例
async def example_usage():
    """使用示例"""
    # 创建事件系统
    event_system = EnhancedEventSystem()
    await event_system.initialize()
    
    try:
        # 定义事件处理器
        async def handle_trade_signal(event: Event):
            logger.info(f"收到交易信号: {event.data}")
        
        async def handle_system_error(event: Event):
            logger.info(f"系统错误: {event.data}")
        
        # 订阅事件
        event_system.subscribe(EventType.TRADE_SIGNAL, handle_trade_signal)
        event_system.subscribe(EventType.SYSTEM_ERROR, handle_system_error)
        
        # 发送事件
        await event_system.emit(
            EventType.TRADE_SIGNAL,
            "strategy_module",
            {"symbol": "BTC/USDT", "signal": "BUY", "price": 50000},
            priority=EventPriority.HIGH
        )
        
        await event_system.emit(
            EventType.SYSTEM_ERROR,
            "data_module",
            {"error": "Connection timeout", "module": "exchange_api"},
            priority=EventPriority.CRITICAL
        )
        
        # 等待处理
        await asyncio.sleep(1)
        
        # 重放历史事件
        await event_system.replay(
            event_types=[EventType.TRADE_SIGNAL],
            start_time=datetime.now().replace(hour=0, minute=0, second=0)
        )
        
    finally:
        await event_system.cleanup()


if __name__ == "__main__":
    asyncio.run(example_usage())
