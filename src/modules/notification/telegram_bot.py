"""
Telegram机器人模块 - 提供智能交互和通知功能

功能：
1. 接收用户消息和命令
2. 发送交易通知和警报
3. 支持自然语言交互
4. 命令处理和响应
5. 消息队列管理
"""

import asyncio
import logging
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable

import aiohttp

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """命令类型"""
    START = "start"
    HELP = "help"
    STATUS = "status"
    BALANCE = "balance"
    POSITIONS = "positions"
    SIGNALS = "signals"
    ALERTS = "alerts"
    SETTINGS = "settings"
    TRADE = "trade"
    ANALYSIS = "analysis"
    STOP = "stop"


@dataclass
class TelegramMessage:
    """Telegram消息"""
    chat_id: int
    message_id: int
    from_user: Optional[str]
    text: str
    timestamp: datetime = field(default_factory=datetime.now)
    is_command: bool = False
    command: Optional[CommandType] = None
    command_args: List[str] = field(default_factory=list)


@dataclass
class TelegramResponse:
    """Telegram响应"""
    chat_id: int
    text: str
    parse_mode: str = "Markdown"
    reply_to_message_id: Optional[int] = None
    disable_web_page_preview: bool = True


class TelegramBot:
    """Telegram机器人"""

    def __init__(self, config: Dict[str, Any], nli=None, llm_integration=None, main_controller=None):
        """
        初始化Telegram机器人

        Args:
            config: 配置信息
            nli: 自然语言接口实例
            llm_integration: 大模型集成实例
            main_controller: 主控制器实例（用于访问交易系统）
        """
        self.config = config
        self.enabled = config.get("enabled", False)
        self.bot_token = config.get("bot_token", "")
        self.chat_ids = config.get("chat_ids", [])
        self.allowed_users = config.get("allowed_users", [])
        
        self.nli = nli
        self.llm_integration = llm_integration
        self.main_controller = main_controller
        
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.session = None
        self._running = False
        self._polling_task = None
        self._last_update_id = 0
        
        self.command_handlers: Dict[CommandType, Callable] = {}
        self.message_handlers: List[Callable] = []
        
        self._init_command_handlers()
        logger.info("Telegram机器人初始化完成")

    def _init_command_handlers(self):
        """初始化命令处理器"""
        self.command_handlers = {
            CommandType.START: self._handle_start,
            CommandType.HELP: self._handle_help,
            CommandType.STATUS: self._handle_status,
            CommandType.BALANCE: self._handle_balance,
            CommandType.POSITIONS: self._handle_positions,
            CommandType.SIGNALS: self._handle_signals,
            CommandType.ALERTS: self._handle_alerts,
            CommandType.SETTINGS: self._handle_settings,
            CommandType.ANALYSIS: self._handle_analysis,
            CommandType.STOP: self._handle_stop,
        }

    async def initialize(self) -> bool:
        """
        初始化Telegram机器人

        Returns:
            bool: 初始化是否成功
        """
        try:
            if not self.enabled:
                logger.info("Telegram机器人未启用")
                return True
            
            if not self.bot_token:
                logger.error("Telegram bot token未配置")
                return False
            
            # 配置代理
            proxy = self.config.get("proxy")
            connector = None
            
            if proxy:
                connector = aiohttp.TCPConnector(
                    ssl=False
                )
                logger.info(f"Telegram机器人配置代理: {proxy}")
            
            self.session = aiohttp.ClientSession(connector=connector)
            self._proxy = proxy
            
            # 测试连接
            if not await self._test_connection():
                logger.error("Telegram机器人连接测试失败")
                return False
            
            logger.info("Telegram机器人初始化成功")
            return True
        except Exception as e:
            logger.error(f"Telegram机器人初始化失败: {e}")
            return False

    async def shutdown(self) -> bool:
        """
        关闭Telegram机器人

        Returns:
            bool: 关闭是否成功
        """
        try:
            self._running = False
            
            if self._polling_task:
                self._polling_task.cancel()
                try:
                    await self._polling_task
                except asyncio.CancelledError:
                    pass
            
            if self.session:
                await self.session.close()
            
            logger.info("Telegram机器人已关闭")
            return True
        except Exception as e:
            logger.error(f"Telegram机器人关闭失败: {e}")
            return False

    async def start_polling(self):
        """开始轮询消息"""
        if not self.enabled:
            return
        
        self._running = True
        self._polling_task = asyncio.create_task(self._polling_loop())
        logger.info("Telegram机器人开始轮询")

    async def _polling_loop(self):
        """轮询循环"""
        while self._running:
            try:
                updates = await self._get_updates()
                for update in updates:
                    await self._process_update(update)
                
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"轮询错误: {e}")
                await asyncio.sleep(5)

    async def _test_connection(self) -> bool:
        """测试连接"""
        try:
            url = f"{self.base_url}/getMe"
            kwargs = {"proxy": self._proxy} if hasattr(self, '_proxy') and self._proxy else {}
            async with self.session.get(url, **kwargs) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and data.get("ok"):
                        logger.info(f"Telegram机器人连接成功: {data['result'].get('username', 'unknown')}")
                        return True
                return False
        except Exception as e:
            logger.error(f"Telegram连接测试失败: {e}")
            return False

    async def _get_updates(self) -> List[Dict]:
        """获取更新"""
        try:
            url = f"{self.base_url}/getUpdates"
            params = {
                "offset": self._last_update_id + 1,
                "limit": 100,
                "timeout": 30
            }
            kwargs = {"proxy": self._proxy} if hasattr(self, '_proxy') and self._proxy else {}
            async with self.session.get(url, params=params, **kwargs) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and data.get("ok"):
                        for update in data.get("result", []):
                            self._last_update_id = max(self._last_update_id, update["update_id"])
                        return data.get("result", [])
                return []
        except Exception as e:
            logger.error(f"获取更新失败: {e}")
            return []

    async def _process_update(self, update: Dict):
        """处理更新"""
        try:
            if "message" in update:
                message = update["message"]
                await self._process_message(message)
            elif "edited_message" in update:
                message = update["edited_message"]
                await self._process_message(message)
            elif "callback_query" in update:
                callback = update["callback_query"]
                await self._process_callback(callback)
        except Exception as e:
            logger.error(f"处理更新失败: {e}")

    async def _process_message(self, message: Dict):
        """处理消息"""
        try:
            chat_id = message["chat"]["id"]
            from_user = message.get("from", {}).get("username", str(chat_id))
            text = message.get("text", "")
            message_id = message.get("message_id", 0)
            
            # 检查用户权限
            if self.allowed_users and from_user not in self.allowed_users:
                logger.warning(f"拒绝未授权用户: {from_user}")
                await self._send_message(TelegramResponse(
                    chat_id=chat_id,
                    text="❌ 您没有权限使用此机器人",
                    reply_to_message_id=message_id
                ))
                return
            
            # 解析消息
            telegram_message = TelegramMessage(
                chat_id=chat_id,
                message_id=message_id,
                from_user=from_user,
                text=text,
                timestamp=datetime.now()
            )
            
            # 检查是否是命令
            if text.startswith("/"):
                await self._process_command(telegram_message)
            else:
                await self._process_natural_language(telegram_message)
            
            # 调用消息处理器
            for handler in self.message_handlers:
                try:
                    await handler(telegram_message)
                except Exception as e:
                    logger.error(f"消息处理器错误: {e}")
                    
        except Exception as e:
            logger.error(f"处理消息失败: {e}")

    async def _process_command(self, message: TelegramMessage):
        """处理命令"""
        try:
            # 解析命令
            command_match = re.match(r'/(\w+)(?:@\w+)?(?:\s+(.*))?', message.text)
            if not command_match:
                return
            
            command_str = command_match.group(1).lower()
            args_str = command_match.group(2) or ""
            args = args_str.split() if args_str else []
            
            # 转换为命令类型
            try:
                command = CommandType(command_str)
                message.is_command = True
                message.command = command
                message.command_args = args
            except ValueError:
                # 未知命令
                await self._send_message(TelegramResponse(
                    chat_id=message.chat_id,
                    text=f"❌ 未知命令: /{command_str}\n使用 /help 查看可用命令",
                    reply_to_message_id=message.message_id
                ))
                return
            
            # 调用命令处理器
            if command in self.command_handlers:
                await self.command_handlers[command](message)
            else:
                await self._send_message(TelegramResponse(
                    chat_id=message.chat_id,
                    text=f"⚠️ 命令 /{command_str} 尚未实现",
                    reply_to_message_id=message.message_id
                ))
                
        except Exception as e:
            logger.error(f"处理命令失败: {e}")

    async def _process_natural_language(self, message: TelegramMessage):
        """处理自然语言消息 - 使用AICommandExecutor获取系统感知能力"""
        try:
            logger.info(f"处理自然语言消息: {message.text[:50]}...")
            
            ai_executor = getattr(self.main_controller, 'ai_command_executor', None) if self.main_controller else None
            
            if ai_executor:
                logger.info("使用AICommandExecutor处理自然语言消息")
                result = await ai_executor.process_input(message.text)
                
                if result.get("success"):
                    response_text = result.get("response", "处理完成")
                    
                    memory_info = result.get("memory_recorded")
                    if memory_info:
                        response_text += f"\n\n📝 {memory_info}"
                    
                    await self._send_message(TelegramResponse(
                        chat_id=message.chat_id,
                        text=response_text,
                        reply_to_message_id=message.message_id
                    ))
                else:
                    await self._send_message(TelegramResponse(
                        chat_id=message.chat_id,
                        text=f"⚠️ {result.get('response', '处理失败')}",
                        reply_to_message_id=message.message_id
                    ))
            elif self.llm_integration:
                # 回退：直接使用大模型（无系统感知）
                prompt = f"""你是一个专业的量化交易助手。请用简洁、友好的语言回应用户的问题。

用户问题：{message.text}

请提供：
1. 直接回答用户的问题
2. 如果是交易相关问题，提供专业建议
3. 使用Markdown格式美化回复
"""
                response = await self.llm_integration.generate(prompt)
                if response and hasattr(response, 'content') and response.content:
                    await self._send_message(TelegramResponse(
                        chat_id=message.chat_id,
                        text=response.content,
                        reply_to_message_id=message.message_id
                    ))
                else:
                    await self._send_message(TelegramResponse(
                        chat_id=message.chat_id,
                        text="🤖 我正在思考中，请稍后再试...",
                        reply_to_message_id=message.message_id
                    ))
            elif self.nli:
                # 使用自然语言接口处理
                response = await self.nli.process_message(message.text)
                await self._send_message(TelegramResponse(
                    chat_id=message.chat_id,
                    text=response,
                    reply_to_message_id=message.message_id
                ))
            else:
                await self._send_message(TelegramResponse(
                    chat_id=message.chat_id,
                    text="🤖 我可以理解自然语言！请告诉我您想了解什么？\n\n例如：\n- 当前市场行情如何？\n- 帮我分析一下BTC\n- 查看我的持仓\n- 有什么交易建议？",
                    reply_to_message_id=message.message_id
                ))
        except Exception as e:
            logger.error(f"处理自然语言失败: {e}")
            import traceback
            traceback.print_exc()
            await self._send_message(TelegramResponse(
                chat_id=message.chat_id,
                text="❌ 处理消息时出错，请稍后重试",
                reply_to_message_id=message.message_id
            ))

    async def _process_callback(self, callback: Dict):
        """处理回调查询"""
        # 实现按钮回调处理
        pass

    async def _send_message(self, response: TelegramResponse) -> bool:
        """发送消息"""
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": response.chat_id,
                "text": response.text,
                "parse_mode": response.parse_mode,
                "disable_web_page_preview": response.disable_web_page_preview
            }
            
            if response.reply_to_message_id:
                data["reply_to_message_id"] = response.reply_to_message_id
            
            kwargs = {"proxy": self._proxy} if hasattr(self, '_proxy') and self._proxy else {}
            async with self.session.post(url, json=data, **kwargs) as resp:
                if resp.status == 200:
                    return True
                else:
                    logger.error(f"发送消息失败: {await resp.text()}")
                    return False
        except Exception as e:
            logger.error(f"发送消息错误: {e}")
            return False

    async def send_notification(self, chat_id: int, text: str, **kwargs) -> bool:
        """
        发送通知

        Args:
            chat_id: 聊天ID
            text: 通知文本
            **kwargs: 其他参数

        Returns:
            bool: 是否成功
        """
        if not self.enabled:
            return False
        
        response = TelegramResponse(
            chat_id=chat_id,
            text=text,
            **kwargs
        )
        return await self._send_message(response)

    async def send_trade_signal(self, signal: Dict[str, Any]) -> bool:
        """
        发送交易信号通知

        Args:
            signal: 交易信号

        Returns:
            bool: 是否成功
        """
        if not self.enabled or not self.chat_ids:
            return False
        
        try:
            direction = signal.get("direction", "unknown")
            symbol = signal.get("symbol", "unknown")
            entry_price = signal.get("entry_price", 0)
            stop_loss = signal.get("stop_loss", 0)
            take_profit = signal.get("take_profit", 0)
            confidence = signal.get("confidence", 0)
            
            emoji = "🟢" if direction.lower() == "buy" else "🔴" if direction.lower() == "sell" else "⚪"
            
            text = f"""{emoji} *交易信号*

*品种*: {symbol}
*方向*: {direction.upper()}
*入场价*: {entry_price}
*止损*: {stop_loss}
*止盈*: {take_profit}
*置信度*: {confidence:.2%}

*时间*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            for chat_id in self.chat_ids:
                await self.send_notification(chat_id, text)
            
            return True
        except Exception as e:
            logger.error(f"发送交易信号失败: {e}")
            return False

    async def send_alert(self, alert: Dict[str, Any]) -> bool:
        """
        发送警报通知

        Args:
            alert: 警报信息

        Returns:
            bool: 是否成功
        """
        if not self.enabled or not self.chat_ids:
            return False
        
        try:
            level = alert.get("level", "info")
            title = alert.get("title", "警报")
            message = alert.get("message", "")
            
            level_emoji = {
                "critical": "🚨",
                "warning": "⚠️",
                "info": "ℹ️",
                "success": "✅"
            }.get(level, "ℹ️")
            
            text = f"""{level_emoji} *{title}*

{message}

*时间*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            for chat_id in self.chat_ids:
                await self.send_notification(chat_id, text)
            
            return True
        except Exception as e:
            logger.error(f"发送警报失败: {e}")
            return False

    async def _handle_start(self, message: TelegramMessage):
        """处理 /start 命令"""
        text = f"""👋 欢迎使用量化交易机器人！

我可以帮助您：
- 📊 查看市场分析
- 📈 接收交易信号
- 🔔 接收风险警报
- 💬 自然语言交互

使用 /help 查看所有可用命令
"""
        await self._send_message(TelegramResponse(
            chat_id=message.chat_id,
            text=text,
            reply_to_message_id=message.message_id
        ))

    async def _handle_help(self, message: TelegramMessage):
        """处理 /help 命令"""
        text = """📋 *可用命令*

*基础命令*:
/start - 开始使用机器人
/help - 显示帮助信息

*交易命令*:
/status - 查看系统状态
/balance - 查看账户余额
/positions - 查看当前持仓
/signals - 查看最新信号
/alerts - 查看活跃警报
/analysis - 获取市场分析

*设置命令*:
/settings - 查看和修改设置
/stop - 停止机器人

您也可以直接用自然语言提问！
"""
        await self._send_message(TelegramResponse(
            chat_id=message.chat_id,
            text=text,
            reply_to_message_id=message.message_id
        ))

    async def _handle_status(self, message: TelegramMessage):
        """处理 /status 命令"""
        try:
            status_data = {"status": "运行中", "modules": {}}
            
            if self.main_controller:
                mc = self.main_controller
                status_data["modules"] = {
                    "数据采集": "🟢 运行中" if mc.trading_monitor else "🔴 未初始化",
                    "策略分析": "🟢 运行中" if mc.strategy_manager else "🔴 未初始化",
                    "AI交易引擎": "🟢 运行中" if mc.ai_trading_engine else "🔴 未初始化",
                    "风险监控": "🟢 运行中" if mc.risk_monitor else "🔴 未初始化",
                    "OKX交易所": "🟢 已连接" if mc.okx_exchange else "🔴 未连接",
                }
            
            text = f"""🟢 *系统状态*

*状态*: {status_data['status']}
*时间*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*模块状态*:
""" + "\n".join([f"- {k}: {v}" for k, v in status_data["modules"].items()]) + """

使用 /balance 查看账户余额
"""
        except Exception as e:
            text = f"❌ 获取状态失败: {e}"
            
        await self._send_message(TelegramResponse(
            chat_id=message.chat_id,
            text=text,
            reply_to_message_id=message.message_id
        ))

    async def _handle_balance(self, message: TelegramMessage):
        """处理 /balance 命令"""
        try:
            balance_data = {"total": 0, "available": 0, "currencies": {}}
            
            if self.main_controller and self.main_controller.okx_exchange:
                okx = self.main_controller.okx_exchange
                balance = await okx.get_account_balance()
                if balance:
                    balance_data = balance
            
            if balance_data.get("currencies"):
                text = "💰 *账户余额*\n\n"
                for currency, amount in balance_data.get("currencies", {}).items():
                    text += f"*{currency}*: {amount:,.4f}\n"
                text += f"\n*总权益*: ${balance_data.get('total', 0):,.2f}\n"
                text += f"*可用保证金*: ${balance_data.get('available', 0):,.2f}\n"
            else:
                text = """💰 *账户余额*

⚠️ 无法获取实时余额数据

可能原因:
- OKX API 未连接
- API 密钥配置错误
- 网络连接问题

请检查系统配置
"""
        except Exception as e:
            text = f"❌ 获取余额失败: {e}"
            
        await self._send_message(TelegramResponse(
            chat_id=message.chat_id,
            text=text,
            reply_to_message_id=message.message_id
        ))

    async def _handle_positions(self, message: TelegramMessage):
        """处理 /positions 命令"""
        try:
            positions = []
            
            if self.main_controller and self.main_controller.okx_exchange:
                okx = self.main_controller.okx_exchange
                positions = await okx.get_positions() or []
            
            if positions:
                text = "📊 *当前持仓*\n\n"
                total_pnl = 0
                for i, pos in enumerate(positions, 1):
                    side_emoji = "🟢" if pos.get("side") == "long" else "🔴"
                    pnl = pos.get("unrealized_pnl", 0)
                    pnl_percent = pos.get("unrealized_pnl_percent", 0)
                    total_pnl += pnl
                    
                    text += f"""{i}. *{pos.get('symbol', 'Unknown')}*
   - 方向: {side_emoji} {pos.get('side', 'N/A').upper()}
   - 数量: {pos.get('quantity', 0):.4f}
   - 入场价: ${pos.get('entry_price', 0):,.2f}
   - 当前价: ${pos.get('current_price', 0):,.2f}
   - 盈亏: ${pnl:+,.2f} ({pnl_percent:+.2f}%)

"""
                text += f"*总盈亏*: ${total_pnl:+,.2f}\n"
            else:
                text = """📊 *当前持仓*

📭 当前没有任何持仓

使用 /signals 查看交易信号
"""
        except Exception as e:
            text = f"❌ 获取持仓失败: {e}"
            
        await self._send_message(TelegramResponse(
            chat_id=message.chat_id,
            text=text,
            reply_to_message_id=message.message_id
        ))

    async def _handle_signals(self, message: TelegramMessage):
        """处理 /signals 命令"""
        try:
            signals = []
            
            if self.main_controller and self.main_controller.ai_trading_engine:
                engine = self.main_controller.ai_trading_engine
                signals = getattr(engine, 'recent_signals', [])[:5]
            
            if signals:
                text = "📈 *最新交易信号*\n\n"
                for i, signal in enumerate(signals, 1):
                    action_emoji = {"buy": "🟢", "sell": "🔴", "hold": "🟡"}.get(signal.get("action", "hold").lower(), "⚪")
                    text += f"""{i}. *{signal.get('symbol', 'Unknown')}* - {action_emoji} {signal.get('action', 'N/A').upper()}
   - 入场: ${signal.get('entry_price', 0):,.2f}
   - 止损: ${signal.get('stop_loss', 0):,.2f}
   - 止盈: ${signal.get('take_profit', 0):,.2f}
   - 置信度: {signal.get('confidence', 0):.0%}

"""
            else:
                text = """📈 *最新交易信号*

📭 暂无交易信号

系统正在分析市场，请稍后再查看
"""
        except Exception as e:
            text = f"❌ 获取信号失败: {e}"
            
        await self._send_message(TelegramResponse(
            chat_id=message.chat_id,
            text=text,
            reply_to_message_id=message.message_id
        ))

    async def _handle_alerts(self, message: TelegramMessage):
        """处理 /alerts 命令"""
        try:
            alerts = []
            
            if self.main_controller and self.main_controller.risk_monitor:
                monitor = self.main_controller.risk_monitor
                alerts = getattr(monitor, 'recent_alerts', [])[:5]
            
            if alerts:
                text = "🔔 *活跃警报*\n\n"
                for i, alert in enumerate(alerts, 1):
                    level_emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(alert.get("level", "info"), "ℹ️")
                    text += f"""{i}. {level_emoji} *{alert.get('title', 'Unknown')}*
   - 时间: {alert.get('time', 'N/A')}
   - 详情: {alert.get('message', 'N/A')}

"""
            else:
                text = """🔔 *活跃警报*

✅ 当前没有活跃警报

系统运行正常
"""
        except Exception as e:
            text = f"❌ 获取警报失败: {e}"
            
        await self._send_message(TelegramResponse(
            chat_id=message.chat_id,
            text=text,
            reply_to_message_id=message.message_id
        ))

    async def _handle_settings(self, message: TelegramMessage):
        """处理 /settings 命令"""
        try:
            settings = {}
            
            if self.main_controller and self.main_controller.config_manager:
                settings = await self.main_controller.config_manager.get_config("trading", {})
            
            text = f"""⚙️ *系统设置*

*通知设置*:
- 交易信号: {'🔔 开启' if self.config.get('notifications', {}).get('trade_signals', True) else '🔕 关闭'}
- 风险警报: {'🔔 开启' if self.config.get('notifications', {}).get('risk_alerts', True) else '🔕 关闭'}
- 每日报告: {'🔔 开启' if self.config.get('notifications', {}).get('daily_summary', False) else '🔕 关闭'}

*交易设置*:
- 交易模式: {settings.get('mode', 'simulation')}
- 最大仓位: {settings.get('max_position', 10)}%
- 止损比例: {settings.get('stop_loss', 2)}%
- 止盈比例: {settings.get('take_profit', 5)}%
- 自动交易: {'✅ 开启' if settings.get('auto_trade', False) else '❌ 关闭'}

*模型设置*:
- 默认模型: {getattr(self.main_controller.enhanced_llm_manager, 'default_model', 'N/A') if self.main_controller else 'N/A'}
"""
        except Exception as e:
            text = f"❌ 获取设置失败: {e}"
            
        await self._send_message(TelegramResponse(
            chat_id=message.chat_id,
            text=text,
            reply_to_message_id=message.message_id
        ))

    async def _handle_analysis(self, message: TelegramMessage):
        """处理 /analysis 命令"""
        try:
            analysis_data = {}
            
            if self.main_controller and self.main_controller.ai_trading_engine:
                engine = self.main_controller.ai_trading_engine
                analysis_data = getattr(engine, 'latest_analysis', {})
            
            if analysis_data:
                text = "📊 *市场分析*\n\n"
                text += f"*整体市场情绪*: {analysis_data.get('sentiment', 'N/A')}\n\n"
                
                for symbol, data in analysis_data.get('symbols', {}).items():
                    text += f"""*{symbol}*:
- 趋势: {data.get('trend', 'N/A')}
- 支撑位: ${data.get('support', 0):,.2f}
- 阻力位: ${data.get('resistance', 0):,.2f}
- RSI: {data.get('rsi', 0):.1f}
- 建议: {data.get('suggestion', 'N/A')}

"""
            else:
                text = """📊 *市场分析*

⏳ 正在分析市场数据...

请稍后再查看，或使用 /signals 查看交易信号
"""
        except Exception as e:
            text = f"❌ 获取分析失败: {e}"
            
        await self._send_message(TelegramResponse(
            chat_id=message.chat_id,
            text=text,
            reply_to_message_id=message.message_id
        ))

    async def _handle_stop(self, message: TelegramMessage):
        """处理 /stop 命令"""
        text = """⏹️ *机器人已停止*

感谢您的使用！

如需重新启动，请使用 /start 命令
"""
        await self._send_message(TelegramResponse(
            chat_id=message.chat_id,
            text=text,
            reply_to_message_id=message.message_id
        ))

    def register_message_handler(self, handler: Callable[[TelegramMessage], Awaitable[None]]):
        """
        注册消息处理器

        Args:
            handler: 消息处理器函数
        """
        self.message_handlers.append(handler)

    def is_healthy(self) -> bool:
        """
        检查健康状态

        Returns:
            bool: 健康状态
        """
        return self.enabled and self.session is not None


# 使用示例
async def example_usage():
    """使用示例"""
    config = {
        "enabled": True,
        "bot_token": "your-bot-token",
        "chat_ids": [123456789],
        "allowed_users": ["your_username"]
    }
    
    bot = TelegramBot(config)
    await bot.initialize()
    
    try:
        await bot.start_polling()
        # 保持运行
        while True:
            await asyncio.sleep(1)
    finally:
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(example_usage())
