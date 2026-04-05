"""
智能通知系统 - 智能化、时段感知的通知管理
"""

import logging
from datetime import datetime, time
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class NotificationPriority(Enum):

    async def initialize(self) -> bool:
        """初始化模块"""
        return True

    """通知优先级"""
    CRITICAL = "critical"      # 关键 - 立即发送，24/7
    HIGH = "high"             # 高 - 立即发送，但遵守免打扰
    MEDIUM = "medium"         # 中 - 批量发送
    LOW = "low"               # 低 - 仅在摘要中


class SmartNotificationSystem:
    """智能通知系统"""
    
    def __init__(
        self,
        send_func: Optional[Callable] = None,
        quiet_hours_start: time = time(23, 0),
        quiet_hours_end: time = time(7, 0)
    ):
        self.send_func = send_func
        self.quiet_hours_start = quiet_hours_start
        self.quiet_hours_end = quiet_hours_end
        
        self.notification_queue: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.notification_history: List[Dict[str, Any]] = []
        self.max_history = 1000
        
        self.batch_interval = 3600  # 1小时批量发送
        self.last_batch_time: Optional[datetime] = None
        
        self.rate_limits = {
            NotificationPriority.LOW: 10,      # 每小时最多10条
            NotificationPriority.MEDIUM: 20,   # 每小时最多20条
            NotificationPriority.HIGH: 50,     # 每小时最多50条
            NotificationPriority.CRITICAL: 100  # 无限制
        }
        
        self.sent_counts: Dict[str, int] = defaultdict(int)
        self.last_reset_time = datetime.now()
        
        logger.info("智能通知系统初始化完成")
    
    async def send(
        self,
        title: str,
        message: str,
        priority: str = "medium",
        category: str = "general"
    ) -> bool:
        """发送通知"""
        priority_enum = NotificationPriority(priority.lower())
        
        if not self._check_rate_limit(priority_enum):
            logger.warning(f"通知频率限制: {priority}")
            return False
        
        notification = {
            "title": title,
            "message": message,
            "priority": priority,
            "category": category,
            "timestamp": datetime.now().isoformat()
        }
        
        if priority_enum == NotificationPriority.CRITICAL:
            return await self._send_immediately(notification)
        
        elif priority_enum == NotificationPriority.HIGH:
            if self._is_quiet_hours():
                self.notification_queue[priority].append(notification)
                logger.info(f"静默时段，延迟发送: {title}")
                return True
            else:
                return await self._send_immediately(notification)
        
        else:
            self.notification_queue[priority].append(notification)
            
            if self._should_send_batch():
                await self._send_batch()
            
            return True
    
    async def _send_immediately(self, notification: Dict[str, Any]) -> bool:
        """立即发送"""
        try:
            if self.send_func:
                await self.send_func(
                    notification["title"],
                    notification["message"],
                    notification["priority"]
                )
            
            self._record_notification(notification)
            logger.info(f"✅ 发送通知: {notification['title']}")
            return True
            
        except Exception as e:
            logger.error(f"发送通知失败: {e}")
            return False
    
    async def _send_batch(self):
        """批量发送"""
        if not any(self.notification_queue.values()):
            return
        
        summary = self._create_summary()
        
        if summary:
            await self._send_immediately(summary)
        
        for priority in self.notification_queue:
            self.notification_queue[priority].clear()
        
        self.last_batch_time = datetime.now()
    
    def _create_summary(self) -> Optional[Dict[str, Any]]:
        """创建摘要"""
        total_notifications = sum(len(q) for q in self.notification_queue.values())
        
        if total_notifications == 0:
            return None
        
        categories = defaultdict(int)
        for priority_queue in self.notification_queue.values():
            for notif in priority_queue:
                categories[notif["category"]] += 1
        
        message = f"📊 过去一小时的摘要 ({total_notifications}条通知)\n\n"
        
        for category, count in categories.items():
            message += f"• {category}: {count}条\n"
        
        return {
            "title": "📊 通知摘要",
            "message": message,
            "priority": "medium",
            "category": "summary",
            "timestamp": datetime.now().isoformat()
        }
    
    def _is_quiet_hours(self) -> bool:
        """检查是否静默时段"""
        now = datetime.now().time()
        
        if self.quiet_hours_start < self.quiet_hours_end:
            return self.quiet_hours_start <= now < self.quiet_hours_end
        else:
            return now >= self.quiet_hours_start or now < self.quiet_hours_end
    
    def _should_send_batch(self) -> bool:
        """检查是否应该批量发送"""
        if not self.last_batch_time:
            return False
        
        elapsed = (datetime.now() - self.last_batch_time).total_seconds()
        return elapsed >= self.batch_interval
    
    def _check_rate_limit(self, priority: NotificationPriority) -> bool:
        """检查频率限制"""
        self._reset_counts_if_needed()
        
        limit = self.rate_limits[priority]
        current = self.sent_counts[priority.value]
        
        return current < limit
    
    def _reset_counts_if_needed(self):
        """重置计数"""
        now = datetime.now()
        if (now - self.last_reset_time).total_seconds() >= 3600:
            self.sent_counts.clear()
            self.last_reset_time = now
    
    def _record_notification(self, notification: Dict[str, Any]):
        """记录通知"""
        self.notification_history.append(notification)
        self.sent_counts[notification["priority"]] += 1
        
        if len(self.notification_history) > self.max_history:
            self.notification_history = self.notification_history[-self.max_history:]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        return {
            "total_sent": len(self.notification_history),
            "queued": sum(len(q) for q in self.notification_queue.values()),
            "rate_limits": dict(self.rate_limits),
            "current_counts": dict(self.sent_counts),
            "quiet_hours": self._is_quiet_hours(),
            "last_batch": self.last_batch_time.isoformat() if self.last_batch_time else None
        }
    
    async def flush(self):
        """清空队列"""
        await self._send_batch()


    async def cleanup(self):
        """清理资源"""
        pass
