from __future__ import annotations

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from enum import Enum
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional, Any, Tuple

from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


class NotificationType(Enum):
    """通知类型"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    TRADING_SIGNAL = "trading_signal"


@dataclass
class Notification:
    """通知对象"""
    message: str
    notification_type: NotificationType
    timestamp: float
    metadata: Dict[str, Any]


class NotificationManager:
    """通知管理器"""

    def __init__(self, config: Dict[str, Any]):
        """初始化通知管理器

        Args:
            config: 配置信息
        """
        self.config = config
        self.telegram_bot = None
        self.telegram_chat_id = None
        self.email_config = None
        self.enabled = False
        self.queue = asyncio.Queue()
        self.worker_task = None

    async def initialize(self) -> bool:
        """初始化通知管理器

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 初始化Telegram
            telegram_config = self.config.get("telegram", {})
            if telegram_config.get("enabled", False):
                token = telegram_config.get("token")
                chat_id = telegram_config.get("chat_id")
                if token and chat_id:
                    self.telegram_bot = Bot(token=token)
                    self.telegram_chat_id = chat_id
                    logger.info("Telegram notification initialized")
                else:
                    logger.warning("Telegram enabled but missing token or chat_id")

            # 初始化邮件
            email_config = self.config.get("email", {})
            if email_config.get("enabled", False):
                required_fields = ["smtp_server", "smtp_port", "username", "password", "from_email", "to_email"]
                if all(email_config.get(field) for field in required_fields):
                    self.email_config = email_config
                    logger.info("Email notification initialized")
                else:
                    logger.warning("Email enabled but missing required configuration")

            # 启动通知处理 worker
            self.worker_task = asyncio.create_task(self._process_queue())
            self.enabled = True
            logger.info("NotificationManager initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize NotificationManager: {e}")
            return False

    async def shutdown(self) -> bool:
        """关闭通知管理器

        Returns:
            bool: 关闭是否成功
        """
        try:
            self.enabled = False
            
            # 停止worker任务
            if self.worker_task:
                self.worker_task.cancel()
                try:
                    await self.worker_task
                except asyncio.CancelledError:
                    pass
            
            logger.info("NotificationManager shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown NotificationManager: {e}")
            return False

    async def send_notification(self, message: str, notification_type: NotificationType = NotificationType.INFO, metadata: Dict[str, Any] = None) -> bool:
        """发送通知

        Args:
            message: 通知消息
            notification_type: 通知类型
            metadata: 元数据

        Returns:
            bool: 发送是否成功
        """
        if not self.enabled:
            logger.warning("NotificationManager is not enabled")
            return False

        try:
            notification = Notification(
                message=message,
                notification_type=notification_type,
                timestamp=asyncio.get_event_loop().time(),
                metadata=metadata or {}
            )
            await self.queue.put(notification)
            return True
        except Exception as e:
            logger.error(f"Failed to queue notification: {e}")
            return False

    async def _process_queue(self):
        """处理通知队列"""
        while self.enabled:
            try:
                notification = await self.queue.get()
                await self._send_notification(notification)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing notification: {e}")

    async def _send_notification(self, notification: Notification):
        """发送单个通知

        Args:
            notification: 通知对象
        """
        try:
            # 发送Telegram通知
            if self.telegram_bot and self.telegram_chat_id:
                await self._send_telegram_notification(notification)

            # 发送邮件通知
            if self.email_config:
                await self._send_email_notification(notification)
        except Exception as e:
            logger.error(f"Error sending notification: {e}")

    async def _send_telegram_notification(self, notification: Notification):
        """发送Telegram通知

        Args:
            notification: 通知对象
        """
        try:
            # 根据通知类型添加前缀
            prefix = {
                NotificationType.INFO: "ℹ️ 信息",
                NotificationType.WARNING: "⚠️ 警告",
                NotificationType.ERROR: "❌ 错误",
                NotificationType.SUCCESS: "✅ 成功",
                NotificationType.TRADING_SIGNAL: "📈 交易信号"
            }.get(notification.notification_type, "ℹ️ 信息")

            message = f"{prefix}\n\n{notification.message}"

            # 添加元数据
            if notification.metadata:
                metadata_str = "\n\n**详细信息:**"
                for key, value in notification.metadata.items():
                    metadata_str += f"\n- {key}: {value}"
                message += metadata_str

            await self.telegram_bot.send_message(
                chat_id=self.telegram_chat_id,
                text=message,
                parse_mode="Markdown"
            )
            logger.info("Telegram notification sent")
        except TelegramError as e:
            logger.error(f"Telegram notification failed: {e}")
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")

    async def _send_email_notification(self, notification: Notification):
        """发送邮件通知

        Args:
            notification: 通知对象
        """
        try:
            # 构建邮件
            msg = MIMEMultipart()
            msg['From'] = self.email_config['from_email']
            msg['To'] = self.email_config['to_email']
            
            # 根据通知类型设置主题
            subject_prefix = {
                NotificationType.INFO: "[信息]",
                NotificationType.WARNING: "[警告]",
                NotificationType.ERROR: "[错误]",
                NotificationType.SUCCESS: "[成功]",
                NotificationType.TRADING_SIGNAL: "[交易信号]"
            }.get(notification.notification_type, "[信息]")
            
            msg['Subject'] = f"{subject_prefix} 智能量化交易系统通知"

            # 构建邮件正文
            body = f"{notification.message}\n\n"
            
            # 添加元数据
            if notification.metadata:
                body += "详细信息:\n"
                for key, value in notification.metadata.items():
                    body += f"- {key}: {value}\n"

            msg.attach(MIMEText(body, 'plain'))

            # 发送邮件
            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['username'], self.email_config['password'])
                server.send_message(msg)

            logger.info("Email notification sent")
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")

    async def send_trading_signal(self, signal: Dict[str, Any]) -> bool:
        """发送交易信号通知

        Args:
            signal: 交易信号

        Returns:
            bool: 发送是否成功
        """
        try:
            # 构建交易信号消息
            message = f"**交易信号**\n\n"
            message += f"类型: {signal.get('signal_type', '未知')}\n"
            message += f"资产: {signal.get('asset', '未知')}\n"
            message += f"数量: {signal.get('amount', 0)}\n"
            message += f"价格: {signal.get('price', 0)}\n"
            message += f"置信度: {signal.get('confidence', 0):.2f}\n"
            message += f"时间: {signal.get('timestamp', '未知')}\n"
            
            if 'reason' in signal:
                message += f"\n原因: {signal['reason']}\n"

            return await self.send_notification(
                message,
                NotificationType.TRADING_SIGNAL,
                signal
            )
        except Exception as e:
            logger.error(f"Failed to send trading signal: {e}")
            return False

    def is_healthy(self) -> bool:
        """检查通知管理器健康状态

        Returns:
            bool: 健康状态
        """
        return self.enabled
